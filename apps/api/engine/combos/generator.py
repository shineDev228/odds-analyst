"""Génération déterministe de combinaisons de sélections.

Le module est pur : aucune dépendance à la base de données, à FastAPI ou au
réseau. Il reçoit des groupes de candidats (un groupe par rencontre) et cherche
les combinaisons dont le produit des cotes tombe dans une fourchette.

Une combinaison contient au plus une sélection par groupe. La recherche est
bornée pour rester utilisable même avec de nombreuses rencontres.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from heapq import heappush, heapreplace
from math import prod

MIN_SELECTIONS = 2
MAX_SELECTIONS = 15
DEFAULT_LIMIT = 20
DEFAULT_POOL_LIMIT = 5_000
DEFAULT_MAX_NODES = 200_000


@dataclass(frozen=True)
class CombinationCandidate:
    """Sélection utilisable dans une combinaison."""

    key: str
    match_id: str
    match_label: str
    competition_name: str
    kickoff_at: datetime
    market_name: str
    selection_label: str
    decimal_odds: float
    probability: float
    low: float
    high: float
    market_id: str = ""
    selection_id: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("Une sélection doit avoir une clé.")
        if self.decimal_odds <= 1:
            raise ValueError("Une cote décimale doit être strictement supérieure à 1.")
        if not 0.0 <= self.low <= self.probability <= self.high <= 1.0:
            raise ValueError("La probabilité et sa fourchette sont incohérentes.")


@dataclass(frozen=True)
class Combination:
    """Combinaison valide, avec ses estimations."""

    selections: tuple[CombinationCandidate, ...]
    total_odds: float
    probability: float
    low: float
    high: float
    expected_value: float


@dataclass(frozen=True)
class CombinationSearch:
    """Résultat borné de la recherche."""

    combinations: tuple[Combination, ...]
    explored_nodes: int
    truncated: bool


def _validate_inputs(
    groups: Sequence[Sequence[CombinationCandidate]],
    *,
    selections_count: int,
    min_odds: float,
    max_odds: float,
    limit: int,
    pool_limit: int,
    max_nodes: int,
) -> None:
    if not MIN_SELECTIONS <= selections_count <= MAX_SELECTIONS:
        raise ValueError(
            f"Le nombre de sélections doit être compris entre {MIN_SELECTIONS} et {MAX_SELECTIONS}."
        )
    if min_odds <= 1:
        raise ValueError("La cote minimale doit être strictement supérieure à 1.")
    if max_odds <= min_odds:
        raise ValueError("La cote maximale doit être supérieure à la cote minimale.")
    if limit < 1:
        raise ValueError("La limite de résultats doit être positive.")
    if pool_limit < limit:
        raise ValueError("La réserve de résultats doit être au moins égale à la limite.")
    if max_nodes < 1:
        raise ValueError("Le nombre maximal de nœuds doit être positif.")


def _prepare_groups(
    groups: Sequence[Sequence[CombinationCandidate]],
) -> tuple[tuple[CombinationCandidate, ...], ...]:
    prepared: list[tuple[CombinationCandidate, ...]] = []
    seen_matches: set[str] = set()
    for group in groups:
        if not group:
            continue
        match_ids = {candidate.match_id for candidate in group}
        if len(match_ids) != 1:
            raise ValueError("Un groupe doit concerner une seule rencontre.")
        match_id = next(iter(match_ids))
        if match_id in seen_matches:
            raise ValueError("Une rencontre ne peut apparaître qu'une fois.")
        seen_matches.add(match_id)
        prepared.append(
            tuple(
                sorted(
                    group,
                    key=lambda item: (
                        -item.probability,
                        item.decimal_odds,
                        item.key,
                    ),
                )
            )
        )
    return tuple(prepared)


def _score(probability: float, total_odds: float, midpoint: float) -> tuple[float, float, float]:
    """Classement : espérance, puis probabilité, puis proximité du milieu."""
    return (
        probability * total_odds - 1.0,
        probability,
        -abs(total_odds - midpoint),
    )


def generate_combinations(
    groups: Sequence[Sequence[CombinationCandidate]],
    *,
    selections_count: int,
    min_odds: float,
    max_odds: float,
    limit: int = DEFAULT_LIMIT,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> CombinationSearch:
    """Cherche les meilleures combinaisons respectant les contraintes.

    `groups` contient un groupe par rencontre. Une combinaison choisit
    exactement une sélection dans `selections_count` groupes distincts.
    """
    _validate_inputs(
        groups,
        selections_count=selections_count,
        min_odds=min_odds,
        max_odds=max_odds,
        limit=limit,
        pool_limit=pool_limit,
        max_nodes=max_nodes,
    )
    prepared = _prepare_groups(groups)
    if len(prepared) < selections_count:
        return CombinationSearch(combinations=(), explored_nodes=0, truncated=False)

    sizes = len(prepared)
    group_min = [min(item.decimal_odds for item in group) for group in prepared]
    group_max = [max(item.decimal_odds for item in group) for group in prepared]
    suffix_min = [sorted(group_min[index:]) for index in range(sizes)]
    suffix_max = [sorted(group_max[index:], reverse=True) for index in range(sizes)]
    midpoint = (min_odds + max_odds) / 2.0

    heap: list[tuple[tuple[float, float, float], int, Combination]] = []
    counter = 0
    explored = 0
    truncated = False

    def record(
        chosen: Sequence[CombinationCandidate],
        total_odds: float,
        probability: float,
        low: float,
        high: float,
    ) -> None:
        nonlocal counter
        combination = Combination(
            selections=tuple(chosen),
            total_odds=total_odds,
            probability=probability,
            low=min(1.0, max(0.0, low)),
            high=min(1.0, max(0.0, high)),
            expected_value=probability * total_odds - 1.0,
        )
        key = _score(probability, total_odds, midpoint)
        item = (key, counter, combination)
        counter += 1
        if len(heap) < pool_limit:
            heappush(heap, item)
        elif key > heap[0][0]:
            heapreplace(heap, item)

    def search(
        index: int,
        chosen: list[CombinationCandidate],
        total_odds: float,
        probability: float,
        low: float,
        high: float,
    ) -> None:
        nonlocal explored, truncated
        if explored >= max_nodes:
            truncated = True
            return
        explored += 1

        remaining = selections_count - len(chosen)
        if remaining == 0:
            if min_odds <= total_odds <= max_odds:
                record(chosen, total_odds, probability, low, high)
            return

        if sizes - index < remaining or total_odds > max_odds:
            return

        upper_values = suffix_max[index][:remaining]
        if len(upper_values) < remaining or total_odds * prod(upper_values) < min_odds:
            return
        lower_values = suffix_min[index][:remaining]
        if len(lower_values) < remaining or total_odds * prod(lower_values) > max_odds:
            return

        for candidate in prepared[index]:
            new_odds = total_odds * candidate.decimal_odds
            if new_odds > max_odds:
                continue
            chosen.append(candidate)
            search(
                index + 1,
                chosen,
                new_odds,
                probability * candidate.probability,
                low * candidate.low,
                high * candidate.high,
            )
            chosen.pop()
            if explored >= max_nodes:
                truncated = True
                return

        if sizes - index - 1 >= remaining:
            search(index + 1, chosen, total_odds, probability, low, high)

    search(0, [], 1.0, 1.0, 1.0, 1.0)

    ordered = sorted(
        heap,
        key=lambda item: (item[0], -item[1]),
        reverse=True,
    )
    return CombinationSearch(
        combinations=tuple(item[2] for item in ordered[:limit]),
        explored_nodes=explored,
        truncated=truncated,
    )
