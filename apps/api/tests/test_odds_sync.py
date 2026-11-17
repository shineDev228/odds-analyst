"""Tests de l'import des cotes 1xBet (The Odds API, phase 15 étape 4).

Deux niveaux sont couverts :

* le **matcher** est pur : noms réels mesurés le 15/11, tolérance de coup
  d'envoi, refus des identités distinctes, ambiguïté et repli de report ;
* le **service** reçoit un client factice : aucun appel réseau n'est effectué
  et aucun crédit réel n'est consommé.

Les décisions attendues reprennent les cas mesurés sur les 122 événements
réels : `Rennes` / `Stade Rennais`, `Athletic Bilbao` / `Athletic Club`,
`CA Osasuna` / `Osasuna`, refus de `Manchester City` / `Manchester United`.
La fixture `fixtures/odds/preview-2026-11-17.json` rejoue, elle, les décisions
réellement observées le 17/11 (118 rattachements sur 122, 4 exonymes non
devinés) sur les noms et les rencontres de la base.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from app.connectors.base import MissingKeyError
from app.connectors.odds_matching import (
    EventRef,
    MatchCandidate,
    decide_event,
    pair_confidence,
    team_confidence,
)
from app.connectors.quota import consume, snapshot
from app.core.config import settings
from app.models.connector import ProviderUsage, SyncRun
from app.models.link import OddsEventLink
from app.models.market import Market, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Team
from app.services import odds_sync
from app.services.markets import build_signature, resolve_template
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MOMENT = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)
CAPTURED = datetime(2026, 11, 17, 7, 30, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "odds"


# ---------------------------------------------------------------------------
# Matcher pur
# ---------------------------------------------------------------------------


def test_known_renames_are_recognised() -> None:
    """Les trois renommages mesurés dépassent le seuil de 0,60."""
    assert team_confidence("Rennes", "Stade Rennais") >= 0.60
    assert team_confidence("Athletic Bilbao", "Athletic Club") >= 0.60
    assert team_confidence("CA Osasuna", "Osasuna") >= 0.60
    # L'égalité stricte reste le score maximal.
    assert team_confidence("Lille", "Lille") == 1.0


def test_distinct_identities_are_capped() -> None:
    """Deux clubs différents ne doivent jamais franchir le seuil."""
    assert team_confidence("Manchester City", "Manchester United") <= 0.55
    assert team_confidence("Manchester United", "Manchester City") <= 0.55


def test_pair_confidence_requires_both_sides() -> None:
    """Le maillon faible impose le sens domicile/extérieur."""
    event = EventRef("evt", "Rennes", "Lille", MOMENT + timedelta(hours=2))
    right = MatchCandidate(
        match_id=_uuid(1), home_name="Stade Rennais", away_name="Lille", kickoff_at=MOMENT
    )
    reversed_sides = MatchCandidate(
        match_id=_uuid(2), home_name="Lille", away_name="Stade Rennais", kickoff_at=MOMENT
    )
    assert pair_confidence(event, right) >= 0.60
    assert pair_confidence(event, reversed_sides) < 0.60


def test_kickoff_tolerance_is_fifteen_minutes() -> None:
    """± 15 minutes pour la clé composite ; au-delà, repli de report visible."""
    candidate = MatchCandidate(
        match_id=_uuid(1), home_name="Rennes", away_name="Lille", kickoff_at=MOMENT
    )
    inside = EventRef("evt", "Rennes", "Lille", MOMENT + timedelta(minutes=14))
    shifted = EventRef("evt", "Rennes", "Lille", MOMENT + timedelta(minutes=16))

    decision = decide_event(inside, [candidate])
    assert decision.matched
    assert decision.method == "kickoff"
    assert decision.confidence == 1.0

    # Un décalage léger reste rattaché, mais par le nom : la méthode est
    # enregistrée, donc l'écart n'est jamais silencieux.
    fallback = decide_event(shifted, [candidate])
    assert fallback.matched
    assert fallback.method == "name_fallback"


def test_ambiguous_event_is_not_linked() -> None:
    """Deux candidats à égalité : aucune décision, rien ne sera écrit."""
    first = MatchCandidate(
        match_id=_uuid(1), home_name="Stade Rennais", away_name="Lille", kickoff_at=MOMENT
    )
    second = MatchCandidate(
        match_id=_uuid(2),
        home_name="Stade Rennais",
        away_name="Lille OSC",
        kickoff_at=MOMENT,
    )
    event = EventRef("evt", "Rennes", "Lille", MOMENT)
    decision = decide_event(event, [first, second])
    assert not decision.matched
    assert decision.reason == "ambiguous"


def test_postponed_match_uses_name_fallback() -> None:
    """Un report de trois jours reste rattaché, mais la méthode est visible."""
    candidate = MatchCandidate(
        match_id=_uuid(1), home_name="Rennes", away_name="Lille", kickoff_at=MOMENT
    )
    event = EventRef("evt", "Rennes", "Lille", MOMENT + timedelta(days=3))
    decision = decide_event(event, [candidate])
    assert decision.matched
    assert decision.method == "name_fallback"


def test_fallback_refuses_distant_or_different_teams() -> None:
    """Au-delà de sept jours, ou avec d'autres équipes, aucun lien."""
    candidate = MatchCandidate(
        match_id=_uuid(1), home_name="Rennes", away_name="Lille", kickoff_at=MOMENT
    )
    too_late = EventRef("evt", "Rennes", "Lille", MOMENT + timedelta(days=8))
    other_team = EventRef("evt", "Rennes", "Brest", MOMENT + timedelta(days=3))
    assert not decide_event(too_late, [candidate]).matched
    assert not decide_event(other_team, [candidate]).matched


def test_ampersand_and_connector_are_the_same_name() -> None:
    """`Brighton & Hove Albion` et `Brighton and Hove Albion` : même club."""
    from app.connectors.matching import normalize_name

    assert normalize_name("Brighton & Hove Albion") == normalize_name(
        "Brighton and Hove Albion"
    )
    assert team_confidence("Brighton and Hove Albion", "Brighton & Hove Albion") == 1.0
    event = EventRef(
        "evt", "Brighton and Hove Albion", "Newcastle United", MOMENT
    )
    candidate = MatchCandidate(
        match_id=_uuid(1),
        home_name="Brighton & Hove Albion",
        away_name="Newcastle United",
        kickoff_at=MOMENT,
    )
    assert decide_event(event, [candidate]).matched


def test_real_preview_fixture_replays_observed_decisions() -> None:
    """Rejoue les décisions réelles du 17/11 : mêmes noms, mêmes issues.

    Aucune décision n'est recalculée à la main : la fixture contient
    l'observation (méthode, score, marge, rencontre) et les rencontres
    candidates telles qu'elles existent dans la base.
    """
    donnees = json.loads(
        (FIXTURES / "preview-2026-11-17.json").read_text(encoding="utf-8")
    )
    assert set(donnees["leagues"]) == {
        "ligue1",
        "laliga",
        "epl",
        "seriea",
        "bundesliga",
        "ucl",
        "mls",
    }

    issues: dict[str, int] = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    for code, bloc in donnees["leagues"].items():
        candidats = [
            MatchCandidate(
                match_id=UUID(row["match_id"]),
                home_name=row["home_name"],
                away_name=row["away_name"],
                kickoff_at=datetime.fromisoformat(row["kickoff_at"]),
            )
            for row in bloc["candidates"]
        ]
        for item in bloc["events"]:
            event = EventRef(
                event_id=item["event_id"],
                home_name=item["home_name"],
                away_name=item["away_name"],
                commence_at=datetime.fromisoformat(item["commence_at"]),
            )
            decision = decide_event(event, candidats)
            attendu = item["expected"]
            libelle = f"{code} {event.home_name} - {event.away_name}"
            assert ("matched" if decision.matched else decision.reason) == attendu[
                "reason"
            ], libelle
            assert decision.method == attendu["method"], libelle
            assert decision.confidence == attendu["confidence"], libelle
            assert decision.margin == attendu["margin"], libelle
            assert (
                str(decision.match_id) if decision.match_id else None
            ) == attendu["match_id"], libelle
            issues[attendu["reason"]] += 1

    # 16 cas figés : les 12 rattachements réels et les 4 refus réels
    # (trois exonymes non devinés et une absence de candidat).
    assert issues == {"matched": 12, "unmatched": 4, "ambiguous": 0}


def test_real_preview_fixture_keeps_exonyms_unmatched() -> None:
    """`1. FC Köln` / `FC Cologne` et `Sporting Lisbon` ne sont pas devinés."""
    donnees = json.loads(
        (FIXTURES / "preview-2026-11-17.json").read_text(encoding="utf-8")
    )
    non_rattaches = {
        (item["home_name"], item["away_name"])
        for bloc in donnees["leagues"].values()
        for item in bloc["events"]
        if item["expected"]["reason"] == "unmatched"
    }
    assert ("Bayern Munich", "1. FC Köln") in non_rattaches
    assert ("1. FC Köln", "Elversberg") in non_rattaches
    assert ("Sporting Lisbon", "Manchester United") in non_rattaches

    # Les deux rencontres Brighton, corrigées par la normalisation `&`,
    # sont bien rattachées dans la même fixture.
    brighton = [
        item
        for bloc in donnees["leagues"].values()
        for item in bloc["events"]
        if "Brighton and Hove Albion" in (item["home_name"], item["away_name"])
    ]
    assert len(brighton) == 2
    assert all(item["expected"]["reason"] == "matched" for item in brighton)


# ---------------------------------------------------------------------------
# Service : monde de test et client factice
# ---------------------------------------------------------------------------


def _uuid(value: int) -> Any:
    from uuid import UUID

    return UUID(int=value)


def _team(db: Session, sport_id: Any, name: str) -> Team:
    team = Team(sport_id=sport_id, name=name)
    db.add(team)
    db.flush()
    return team


def _match(
    db: Session,
    season_id: Any,
    home: Team,
    away: Team,
    kickoff: datetime,
    external_id: str,
) -> Match:
    match = Match(
        season_id=season_id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=kickoff,
        status=MatchStatus.PROGRAMME,
        external_id=external_id,
        data_source="bigballsdata",
    )
    db.add(match)
    db.flush()
    return match


def _world(db: Session, offsets: tuple[int, ...] = (6, 80)) -> dict[str, Any]:
    """Compétition `ligue1`, deux rencontres et leurs équipes."""
    from app.models.reference import Sport

    football = db.scalar(select(Sport).where(Sport.code == "football"))
    assert football is not None
    competition = Competition(
        sport_id=football.id, name="Ligue 1", code="ligue1", country="France", tier=1
    )
    db.add(competition)
    db.flush()
    season = Season(competition_id=competition.id, label="2026-2027")
    db.add(season)
    db.flush()

    rennes = _team(db, football.id, "Stade Rennais")
    lille = _team(db, football.id, "Lille")
    nantes = _team(db, football.id, "Nantes")
    brest = _team(db, football.id, "Brest")

    matches = {
        "rennes": _match(
            db, season.id, rennes, lille, MOMENT + timedelta(hours=offsets[0]), "m-rennes"
        ),
        "nantes": _match(
            db, season.id, nantes, brest, MOMENT + timedelta(hours=offsets[1]), "m-nantes"
        ),
    }
    # Identifiants seuls : la session est fermée au retour de la fixture.
    ids = {
        "competition_id": competition.id,
        "season_id": season.id,
        "matches": {name: match.id for name, match in matches.items()},
    }
    db.commit()
    return ids


def _event(
    event_id: str,
    home: str,
    away: str,
    commence: datetime,
    *,
    bookmaker: str = "onexbet",
    extended: bool = False,
    captured: datetime = CAPTURED,
) -> dict[str, Any]:
    """Événement brut conforme à ce que renvoie The Odds API."""
    markets = [
        {
            "key": "h2h",
            "outcomes": [
                {"name": home, "price": 2.10},
                {"name": "Draw", "price": 3.40},
                {"name": away, "price": 3.20},
            ],
        },
        {
            "key": "totals",
            "outcomes": [
                {"name": "Over", "price": 1.90, "point": 2.5},
                {"name": "Under", "price": 1.90, "point": 2.5},
            ],
        },
    ]
    if extended:
        markets.extend(
            [
                {
                    "key": "double_chance",
                    "outcomes": [
                        {"name": f"{home} or Draw", "price": 1.35},
                        {"name": f"{home} or {away}", "price": 1.32},
                        {"name": f"Draw or {away}", "price": 1.79},
                    ],
                },
                {
                    "key": "btts",
                    "outcomes": [
                        {"name": "Yes", "price": 1.66},
                        {"name": "No", "price": 2.12},
                    ],
                },
            ]
        )
    return {
        "id": event_id,
        "sport_key": "soccer_france_ligue_one",
        "commence_time": commence.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "home_team": home,
        "away_team": away,
        "bookmakers": (
            [
                {
                    "key": bookmaker,
                    "last_update": captured.isoformat().replace("+00:00", "Z"),
                    "markets": markets,
                }
            ]
            if bookmaker
            else []
        ),
    }


def _listing(event: dict[str, Any]) -> dict[str, Any]:
    """Vue `/events` : sans cotes ni bookmakers."""
    return {
        "id": event["id"],
        "sport_key": event["sport_key"],
        "commence_time": event["commence_time"],
        "home_team": event["home_team"],
        "away_team": event["away_team"],
    }


class FakeOddsClient:
    """Client The Odds API simulé : compte les appels et les crédits."""

    provider = "the_odds_api"

    def __init__(
        self,
        *,
        listings: dict[str, list[dict[str, Any]]] | None = None,
        competition: dict[str, list[dict[str, Any]]] | None = None,
        per_event: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.listings = listings or {}
        self.competition = competition or {}
        self.per_event = per_event or {}
        self.calls: list[tuple[str, ...]] = []
        self.spent = 0
        self.last_headers: dict[str, str] = {}
        self.last_quota = None

    def _bill(self, credits: int) -> None:
        self.spent += credits
        self.last_headers = {"x-requests-remaining": str(max(400 - self.spent, 0))}

    def list_events(self, sport_key: str) -> list[dict[str, Any]]:
        self.calls.append(("events", sport_key))
        return self.listings.get(sport_key, [])

    def competition_odds(self, sport_key: str, *, markets: str) -> list[dict[str, Any]]:
        self.calls.append(("competition", sport_key, markets))
        self._bill(2)
        return self.competition.get(sport_key, [])

    def event_odds(self, sport_key: str, event_id: str, *, markets: str) -> dict[str, Any]:
        self.calls.append(("event", event_id, markets))
        self._bill(2)
        return self.per_event.get(event_id, {})

    def close(self) -> None:  # pragma: no cover - le service ne ferme pas un client fourni
        raise AssertionError("Le client fourni ne doit pas être fermé.")

    @property
    def paid_calls(self) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[0] in {"competition", "event"}]


@pytest.fixture()
def world(engine, seeded: None) -> dict[str, Any]:
    with Session(engine) as db:
        return _world(db)


def _standard_client() -> FakeOddsClient:
    rennes = _event(
        "evt-rennes", "Rennes", "Lille", MOMENT + timedelta(hours=6, minutes=10)
    )
    nantes = _event("evt-nantes", "Nantes", "Brest", MOMENT + timedelta(hours=80))
    extended = _event(
        "evt-rennes",
        "Rennes",
        "Lille",
        MOMENT + timedelta(hours=6, minutes=10),
        extended=True,
    )
    return FakeOddsClient(
        listings={
            "soccer_france_ligue_one": [
                _listing(rennes),
                _listing(nantes),
            ]
        },
        competition={"soccer_france_ligue_one": [rennes, nantes]},
        per_event={"evt-rennes": extended},
    )


def _preview(db: Session, client: Any, **options: Any) -> Any:
    return odds_sync.preview(db, leagues=["ligue1"], now=MOMENT, client=client, **options)


def _run(db: Session, client: Any, **options: Any) -> Any:
    return odds_sync.run(db, leagues=["ligue1"], now=MOMENT, client=client, **options)


def _markets(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Market)) or 0


def _odds(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(OddsSnapshot)) or 0


def _links(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(OddsEventLink)) or 0


# ---------------------------------------------------------------------------
# Aperçu gratuit
# ---------------------------------------------------------------------------


def test_preview_writes_nothing_and_costs_nothing(world, engine) -> None:
    client = _standard_client()
    with Session(engine) as db:
        report = _preview(db, client)
        db.commit()

        assert report.status == "preview"
        assert report.credits_estimated == 4  # 2 + un événement étendu
        assert report.quota_remaining == 400
        league = report.leagues[0]
        assert (league.events, league.matched, league.ambiguous, league.unmatched) == (
            2,
            2,
            0,
            0,
        )
        assert _markets(db) == 0
        assert _odds(db) == 0
        assert _links(db) == 0
        assert client.paid_calls == []
        assert db.scalar(select(func.count()).select_from(ProviderUsage)) == 1


def test_preview_reports_unmatched_event(world, engine) -> None:
    unknown = _event("evt-inconnu", "Bayern", "Dortmund", MOMENT + timedelta(hours=5))
    client = FakeOddsClient(
        listings={"soccer_france_ligue_one": [_listing(unknown)]},
        competition={"soccer_france_ligue_one": [unknown]},
    )
    with Session(engine) as db:
        report = _preview(db, client)
        league = report.leagues[0]
        assert league.unmatched == 1
        assert league.credits == 2  # l'appel compétition reste nécessaire
        assert league.items[0].match_id is None
        assert _links(db) == 0


def test_preview_without_events_is_empty(world, engine) -> None:
    with Session(engine) as db:
        report = _preview(db, FakeOddsClient())
        assert report.status == "empty"
        assert report.credits_estimated == 0
        assert report.leagues[0].status == "empty"


# ---------------------------------------------------------------------------
# Passe payante
# ---------------------------------------------------------------------------


def test_run_writes_markets_links_and_snapshots(world, engine) -> None:
    client = _standard_client()
    with Session(engine) as db:
        report = _run(db, client)
        db.commit()

        assert report.status == "applied"
        assert report.credits_used == 4
        assert report.requests == 3  # 1 liste + 1 appel compétition + 1 étendu
        assert client.spent == 4
        assert _links(db) == 2
        assert _markets(db) == 6  # 2 marchés par événement + 2 étendus
        assert _odds(db) == 15  # 5 relevés par événement, plus 5 étendus

        rennes = world["matches"]["rennes"]
        familles = {
            market.family
            for market in db.scalars(
                select(Market).where(Market.match_id == rennes)
            ).all()
        }
        assert familles == {"resultat", "totaux", "double_chance", "btts"}

        snapshots = db.scalars(
            select(OddsSnapshot).join(Selection).join(Market).where(
                Market.match_id == rennes
            )
        ).all()
        assert {row.bookmaker for row in snapshots} == {"1xBet"}
        assert {row.source for row in snapshots} == {"the_odds_api"}
        assert {row.decimal_odds for row in snapshots} == {
            2.1,
            3.4,
            3.2,
            1.9,
            1.35,
            1.32,
            1.79,
            1.66,
            2.12,
        }

        links = db.scalars(select(OddsEventLink)).all()
        assert {link.event_id for link in links} == {"evt-rennes", "evt-nantes"}
        assert {link.competition_code for link in links} == {"ligue1"}
        assert all(link.is_active for link in links)
        assert {link.method for link in links} == {"kickoff"}

        run = db.scalar(select(SyncRun))
        assert run is not None
        assert run.operation == "odds"
        assert run.status == "applied"
        assert run.credits_used == 4
        assert run.quota_remaining == 396


def test_second_run_is_idempotent(world, engine) -> None:
    client = _standard_client()
    with Session(engine) as db:
        _run(db, client)
        db.commit()
        first_markets = _markets(db)
        first_odds = _odds(db)

        second = _run(db, client)
        db.commit()

        assert second.status == "applied"
        assert _markets(db) == first_markets
        assert _odds(db) == first_odds
        assert second.totals["links_created"] == 0
        assert second.totals["links_reused"] == 2
        assert _links(db) == 2


def test_same_event_new_snapshot_is_recorded(world, engine) -> None:
    """Une cote réactualisée crée un relevé de plus, jamais un doublon."""
    client = _standard_client()
    with Session(engine) as db:
        _run(db, client)
        db.commit()
        before = _odds(db)

        refreshed = FakeOddsClient(
            listings=client.listings,
            competition={
                "soccer_france_ligue_one": [
                    _event(
                        "evt-rennes",
                        "Rennes",
                        "Lille",
                        MOMENT + timedelta(hours=6, minutes=10),
                        captured=CAPTURED + timedelta(hours=1),
                    ),
                    _event(
                        "evt-nantes",
                        "Nantes",
                        "Brest",
                        MOMENT + timedelta(hours=80),
                        captured=CAPTURED + timedelta(hours=1),
                    ),
                ]
            },
            per_event={},
        )
        report = _run(db, refreshed, include_extended=False)
        db.commit()

        assert report.status == "applied"
        assert _odds(db) == before + 10  # 5 relevés par événement
        assert _markets(db) == 6


def test_manual_market_is_never_overwritten(world, engine) -> None:
    with Session(engine) as db:
        rennes = world["matches"]["rennes"]
        template = resolve_template(db, "football.resultat_1x2")
        assert template is not None
        signature = build_signature(
            template_code="football.resultat_1x2",
            name=template.name,
            family=template.family,
            period=template.period,
            subject=template.subject,
            subject_team_id=None,
            subject_player=None,
            line=None,
            line2=None,
        )
        manual = Market(
            match_id=rennes,
            template_code="football.resultat_1x2",
            name=template.name,
            family=template.family,
            period=template.period,
            subject=template.subject,
            signature=signature,
            is_custom=True,
            notes="saisie manuelle",
            selections=[
                Selection(code="1", label="Domicile", sort_order=0),
                Selection(code="X", label="Nul", sort_order=1),
                Selection(code="2", label="Extérieur", sort_order=2),
            ],
        )
        db.add(manual)
        db.commit()

        report = _run(db, _standard_client())
        db.commit()

        assert report.totals["manual_kept"] == 1
        assert any("saisi(s) à la main" in warning for warning in report.leagues[0].warnings)
        stored = db.scalar(select(Market).where(Market.id == manual.id))
        assert stored is not None and stored.is_custom
        assert all(selection.snapshots == [] for selection in stored.selections)
        # L'import écrit tout de même les totaux, qu'il ne remplace pas.
        assert db.scalar(
            select(func.count())
            .select_from(Market)
            .where(Market.match_id == rennes, Market.family == "totaux")
        ) == 1


def test_missing_bookmaker_writes_no_odds(world, engine) -> None:
    rennes = _event(
        "evt-rennes",
        "Rennes",
        "Lille",
        MOMENT + timedelta(hours=6, minutes=10),
        bookmaker="",
    )
    nantes = _event(
        "evt-nantes", "Nantes", "Brest", MOMENT + timedelta(hours=80), bookmaker=""
    )
    client = FakeOddsClient(
        listings={"soccer_france_ligue_one": [_listing(rennes), _listing(nantes)]},
        competition={"soccer_france_ligue_one": [rennes, nantes]},
    )
    with Session(engine) as db:
        report = _run(db, client, include_extended=False)
        db.commit()

        assert report.status == "applied"
        assert _markets(db) == 0
        assert _odds(db) == 0
        assert report.totals["bookmaker_missing"] == 2
        assert report.credits_used == 2
        assert any("sans 1xBet" in warning for warning in report.leagues[0].warnings)
        # Le rattachement, lui, reste acquis pour la prochaine passe.
        assert _links(db) == 2


def test_budget_shortage_stops_before_any_paid_call(world, engine) -> None:
    with Session(engine) as db:
        consume(db, "the_odds_api", 399, now=MOMENT)
        client = _standard_client()
        report = _run(db, client)
        db.commit()

        assert report.status == "failed"
        assert report.credits_used == 0
        assert client.paid_calls == []
        assert _odds(db) == 0
        assert _links(db) == 2  # la décision est conservée, pas la dépense
        assert snapshot(db, "the_odds_api", now=MOMENT).remaining == 1


def test_extended_markets_are_limited_to_window_and_cap(world, engine) -> None:
    with Session(engine) as db:
        from app.models.reference import Sport

        football = db.scalar(select(Sport).where(Sport.code == "football"))
        assert football is not None
        lyon = _team(db, football.id, "Lyon")
        marseille = _team(db, football.id, "Marseille")
        _match(
            db,
            world["season_id"],
            lyon,
            marseille,
            MOMENT + timedelta(hours=73),
            "m-lyon",
        )
        db.commit()

        events = [
            _event("evt-rennes", "Rennes", "Lille", MOMENT + timedelta(hours=6)),
            _event("evt-nantes", "Nantes", "Brest", MOMENT + timedelta(hours=80)),
            _event("evt-lyon", "Lyon", "Marseille", MOMENT + timedelta(hours=73)),
        ]
        client = FakeOddsClient(
            listings={"soccer_france_ligue_one": [_listing(item) for item in events]},
            competition={"soccer_france_ligue_one": events},
            per_event={
                "evt-rennes": _event(
                    "evt-rennes",
                    "Rennes",
                    "Lille",
                    MOMENT + timedelta(hours=6),
                    extended=True,
                ),
                "evt-lyon": _event(
                    "evt-lyon",
                    "Lyon",
                    "Marseille",
                    MOMENT + timedelta(hours=73),
                    extended=True,
                ),
            },
        )
        report = _run(db, client, extended_limit=1)
        db.commit()

        extended_calls = [call for call in client.calls if call[0] == "event"]
        # Seul l'événement à moins de 72 h est éligible, malgré le plafond de 1.
        assert len(extended_calls) == 1
        assert extended_calls[0][1] == "evt-rennes"
        assert report.credits_used == 4  # 2 compétition + 2 étendus
        assert report.totals["extended_events"] == 1

        # Aperçu identique : mêmes bornes, même coût annoncé.
        preview = _preview(db, client)
        assert preview.credits_estimated == 4


def test_extended_cap_is_shared_across_competitions(world, engine) -> None:
    """Le plafond de 30 (ici 1) vaut pour la passe, pas par compétition."""
    with Session(engine) as db:
        from app.models.reference import Sport

        football = db.scalar(select(Sport).where(Sport.code == "football"))
        assert football is not None
        competition = Competition(
            sport_id=football.id, name="La Liga", code="laliga", country="Espagne", tier=1
        )
        db.add(competition)
        db.flush()
        season = Season(competition_id=competition.id, label="2026-2027")
        db.add(season)
        db.flush()
        barcelona = _team(db, football.id, "Barcelona")
        madrid = _team(db, football.id, "Real Madrid")
        _match(db, season.id, barcelona, madrid, MOMENT + timedelta(hours=5), "m-laliga")
        db.commit()

        ligue1_events = [
            _event("evt-rennes", "Rennes", "Lille", MOMENT + timedelta(hours=6)),
            _event("evt-nantes", "Nantes", "Brest", MOMENT + timedelta(hours=80)),
        ]
        laliga_event = _event(
            "evt-laliga", "Barcelona", "Real Madrid", MOMENT + timedelta(hours=5)
        )
        client = FakeOddsClient(
            listings={
                "soccer_france_ligue_one": [_listing(item) for item in ligue1_events],
                "soccer_spain_la_liga": [_listing(laliga_event)],
            },
            competition={
                "soccer_france_ligue_one": ligue1_events,
                "soccer_spain_la_liga": [laliga_event],
            },
            per_event={
                "evt-rennes": _event(
                    "evt-rennes", "Rennes", "Lille", MOMENT + timedelta(hours=6)
                ),
                "evt-laliga": _event(
                    "evt-laliga", "Barcelona", "Real Madrid", MOMENT + timedelta(hours=5)
                ),
            },
        )
        report = odds_sync.run(
            db,
            leagues=["ligue1", "laliga"],
            now=MOMENT,
            client=client,
            extended_limit=1,
        )
        db.commit()

        extended_calls = [call for call in client.calls if call[0] == "event"]
        assert len(extended_calls) == 1
        assert report.credits_used == 6  # 2 + 2 pour la première, 2 pour la seconde
        assert report.totals["extended_events"] == 1


def test_moved_event_replaces_the_link(world, engine) -> None:
    """Rencontre reportée : le nouveau lien remplace l'ancien, un seul actif."""
    with Session(engine) as db:
        first = _standard_client()
        _run(db, first, include_extended=False)
        db.commit()

        delayed = _event(
            "evt-rennes-reporte",
            "Rennes",
            "Lille",
            MOMENT + timedelta(days=3),
        )
        nantes = _event("evt-nantes", "Nantes", "Brest", MOMENT + timedelta(hours=80))
        scotch = FakeOddsClient(
            listings={"soccer_france_ligue_one": [_listing(delayed), _listing(nantes)]},
            competition={"soccer_france_ligue_one": [delayed, nantes]},
        )
        report = _run(db, scotch, include_extended=False)
        db.commit()

        assert report.totals["links_created"] == 1
        assert report.totals["links_deactivated"] == 1
        active = db.scalars(
            select(OddsEventLink).where(OddsEventLink.is_active.is_(True))
        ).all()
        assert {link.event_id for link in active} == {"evt-rennes-reporte", "evt-nantes"}
        moved = next(link for link in active if link.event_id == "evt-rennes-reporte")
        assert moved.method == "name_fallback"


def test_overview_counts_coverage(world, engine) -> None:
    with Session(engine) as db:
        _run(db, _standard_client())
        db.commit()

        state = odds_sync.overview(db, now=MOMENT)
        assert state["provider"] == "the_odds_api"
        assert state["quota"]["used"] == 4
        assert state["quota"]["remaining"] == 396
        assert state["costs"] == {
            "competition": 2,
            "event": 2,
            "extended_window_hours": 72,
            "extended_max_events": 30,
        }
        assert state["totals"]["markets"] == 6
        assert state["totals"]["odds_rows"] == 15
        assert state["totals"]["active_links"] == 2
        assert state["upcoming"]["ligue1"] == 2
        assert state["last_run"] is not None
        assert state["last_run"].operation == "odds"


def test_missing_key_is_reported_without_network(world, engine, monkeypatch) -> None:
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    with Session(engine) as db:
        report = _run(db, client=None)
        assert report.status == "failed"
        assert report.error is not None and "THE_ODDS_API_KEY" in report.error
        assert _links(db) == 0


def test_make_client_refuses_without_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    with pytest.raises(MissingKeyError):
        odds_sync.make_client()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_odds_routes_require_authentication(guest) -> None:
    assert guest.get("/api/v1/sync/odds/overview").status_code == 401
    assert guest.post("/api/v1/sync/odds/preview", json={}).status_code == 401
    assert guest.post("/api/v1/sync/odds/run", json={}).status_code == 401


def test_odds_routes_require_csrf(auth_client) -> None:
    del auth_client.headers["X-CSRF-Token"]
    response = auth_client.post("/api/v1/sync/odds/preview", json={})
    assert response.status_code == 403


def test_odds_routes_answer_503_without_key(auth_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    overview = auth_client.get("/api/v1/sync/odds/overview")
    assert overview.status_code == 200
    assert overview.json()["configured"] is False

    preview = auth_client.post("/api/v1/sync/odds/preview", json={})
    assert preview.status_code == 503
    assert "THE_ODDS_API_KEY" in preview.json()["detail"]

    run = auth_client.post("/api/v1/sync/odds/run", json={})
    assert run.status_code == 503


def test_odds_preview_route_shape(auth_client, monkeypatch) -> None:
    report = odds_sync.PreviewReport(
        status="preview",
        credits_estimated=2,
        quota_remaining=398,
        leagues=[
            odds_sync.PreviewLeague(
                code="ligue1",
                name="Ligue 1",
                events=1,
                matched=1,
                credits=2,
                items=[
                    odds_sync.PreviewEvent(
                        event_id="evt-1",
                        home_team="Rennes",
                        away_team="Lille",
                        commence_at=MOMENT + timedelta(hours=6),
                        decision="matched",
                        method="kickoff",
                        confidence=1.0,
                        margin=1.0,
                        match_id=_uuid(7),
                        match_label="Stade Rennais - Lille",
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(odds_sync, "preview", lambda db, **kwargs: report)
    monkeypatch.setattr(settings, "the_odds_api_key", "test-key")

    response = auth_client.post("/api/v1/sync/odds/preview", json={"leagues": ["ligue1"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["credits_estimated"] == 2
    assert payload["leagues"][0]["items"][0]["decision"] == "matched"
    assert payload["leagues"][0]["items"][0]["match_label"] == "Stade Rennais - Lille"
