"""Tests du moteur pur de règlement et de performance."""

import pytest
from engine.settlement import (
    CombinationSettlement,
    CombinationStatus,
    LegRule,
    LegStatus,
    MatchResult,
    settle_combination,
    settle_leg,
    summarize_performance,
)


def _rule(
    family: str,
    code: str,
    *,
    line: float | None = None,
    period: str = "match",
    odds: float = 2.0,
) -> LegRule:
    return LegRule(
        family=family,
        period=period,
        selection_code=code,
        line=line,
        decimal_odds=odds,
    )


def _result(
    status: str = "termine",
    home: int | None = 2,
    away: int | None = 1,
) -> MatchResult:
    return MatchResult(status=status, home_score=home, away_score=away)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("1", LegStatus.GAGNEE),
        ("X", LegStatus.PERDUE),
        ("2", LegStatus.PERDUE),
    ],
)
def test_1x2_home_win(code: str, expected: LegStatus) -> None:
    assert settle_leg(_rule("resultat", code), _result(home=2, away=1)).status == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("1", LegStatus.PERDUE),
        ("X", LegStatus.GAGNEE),
        ("2", LegStatus.PERDUE),
    ],
)
def test_1x2_draw(code: str, expected: LegStatus) -> None:
    assert settle_leg(_rule("resultat", code), _result(home=1, away=1)).status == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("1X", LegStatus.GAGNEE),
        ("12", LegStatus.GAGNEE),
        ("X2", LegStatus.PERDUE),
    ],
)
def test_double_chance(code: str, expected: LegStatus) -> None:
    assert (
        settle_leg(_rule("double_chance", code), _result(home=2, away=1)).status
        == expected
    )


@pytest.mark.parametrize(
    ("code", "line", "total", "expected"),
    [
        ("plus", 2.5, (2, 1), LegStatus.GAGNEE),
        ("moins", 2.5, (2, 1), LegStatus.PERDUE),
        ("plus", 3.5, (2, 1), LegStatus.PERDUE),
        ("moins", 3.5, (2, 1), LegStatus.GAGNEE),
        ("plus", 3.0, (2, 1), LegStatus.REMBOURSEE),
        ("moins", 3.0, (2, 1), LegStatus.REMBOURSEE),
    ],
)
def test_totals(
    code: str,
    line: float,
    total: tuple[int, int],
    expected: LegStatus,
) -> None:
    settlement = settle_leg(
        _rule("totaux", code, line=line),
        _result(home=total[0], away=total[1]),
    )
    assert settlement.status == expected


@pytest.mark.parametrize(
    ("code", "home", "away", "expected"),
    [
        ("oui", 1, 1, LegStatus.GAGNEE),
        ("oui", 2, 1, LegStatus.GAGNEE),
        ("oui", 4, 3, LegStatus.GAGNEE),
        ("oui", 1, 0, LegStatus.PERDUE),
        ("oui", 0, 0, LegStatus.PERDUE),
        ("non", 1, 0, LegStatus.GAGNEE),
        ("non", 0, 0, LegStatus.GAGNEE),
        ("non", 2, 2, LegStatus.PERDUE),
    ],
)
def test_btts(code: str, home: int, away: int, expected: LegStatus) -> None:
    settlement = settle_leg(_rule("btts", code), _result(home=home, away=away))
    assert settlement.status == expected


def test_btts_missing_score_is_unavailable() -> None:
    settlement = settle_leg(_rule("btts", "oui"), _result(home=None, away=None))
    assert settlement.status == LegStatus.INDISPONIBLE


def test_btts_void_match_is_refunded() -> None:
    settlement = settle_leg(_rule("btts", "non"), _result(status="reporte", home=None, away=None))
    assert settlement.status == LegStatus.REMBOURSEE


@pytest.mark.parametrize("status", ["programme", "en_cours"])
def test_pending_match(status: str) -> None:
    settlement = settle_leg(_rule("resultat", "1"), _result(status=status, home=None, away=None))
    assert settlement.status == LegStatus.EN_ATTENTE


@pytest.mark.parametrize("status", ["reporte", "annule"])
def test_void_match(status: str) -> None:
    settlement = settle_leg(_rule("resultat", "1"), _result(status=status, home=None, away=None))
    assert settlement.status == LegStatus.REMBOURSEE


def test_missing_score_is_unavailable() -> None:
    settlement = settle_leg(_rule("resultat", "1"), _result(home=None, away=None))
    assert settlement.status == LegStatus.INDISPONIBLE


def test_unknown_market_and_period_are_unavailable() -> None:
    assert (
        settle_leg(_rule("corners", "plus", line=9.5), _result()).status
        == LegStatus.INDISPONIBLE
    )
    assert (
        settle_leg(_rule("resultat", "1", period="mi_temps"), _result()).status
        == LegStatus.INDISPONIBLE
    )
    assert (
        settle_leg(_rule("totaux", "plus", line=None), _result()).status
        == LegStatus.INDISPONIBLE
    )


def test_combination_precedence() -> None:
    lost = settle_combination(
        [LegStatus.PERDUE, LegStatus.EN_ATTENTE],
        [2.0, 3.0],
    )
    assert lost.status == CombinationStatus.PERDUE
    assert lost.payout_units == 0.0
    assert lost.net_units == -1.0

    unavailable = settle_combination(
        [LegStatus.INDISPONIBLE, LegStatus.EN_ATTENTE],
        [2.0, 3.0],
    )
    assert unavailable.status == CombinationStatus.INDISPONIBLE
    assert unavailable.payout_units is None

    pending = settle_combination(
        [LegStatus.EN_ATTENTE, LegStatus.GAGNEE],
        [2.0, 3.0],
    )
    assert pending.status == CombinationStatus.EN_ATTENTE
    assert pending.payout_units is None


def test_combination_refunded_and_won_with_void_leg() -> None:
    refunded = settle_combination(
        [LegStatus.REMBOURSEE, LegStatus.REMBOURSEE],
        [2.0, 3.0],
    )
    assert refunded.status == CombinationStatus.REMBOURSEE
    assert refunded.effective_odds == 1.0
    assert refunded.payout_units == 1.0
    assert refunded.net_units == 0.0

    won = settle_combination(
        [LegStatus.GAGNEE, LegStatus.REMBOURSEE],
        [2.5, 3.0],
    )
    assert won.status == CombinationStatus.GAGNEE
    assert won.effective_odds == pytest.approx(2.5)
    assert won.payout_units == pytest.approx(2.5)
    assert won.net_units == pytest.approx(1.5)


def test_combination_validation() -> None:
    with pytest.raises(ValueError):
        settle_combination([], [])
    with pytest.raises(ValueError):
        settle_combination([LegStatus.GAGNEE], [2.0, 3.0])
    with pytest.raises(ValueError):
        settle_combination([LegStatus.GAGNEE], [1.0])


def test_performance_summary() -> None:
    summary = summarize_performance(
        [
            CombinationSettlement(CombinationStatus.GAGNEE, 2.5, 2.5, 1.5),
            CombinationSettlement(CombinationStatus.PERDUE, 2.0, 0.0, -1.0),
            CombinationSettlement(CombinationStatus.REMBOURSEE, 1.0, 1.0, 0.0),
            CombinationSettlement(CombinationStatus.EN_ATTENTE, 2.0, None, None),
            CombinationSettlement(CombinationStatus.INDISPONIBLE, 2.0, None, None),
        ]
    )
    assert summary.total == 5
    assert summary.gagnees == 1
    assert summary.perdues == 1
    assert summary.remboursees == 1
    assert summary.en_attente == 1
    assert summary.indisponibles == 1
    assert summary.reglees == 3
    assert summary.taux_reussite == pytest.approx(0.5)
    assert summary.unites_engagees == pytest.approx(3.0)
    assert summary.unites_retournees == pytest.approx(3.5)
    assert summary.resultat_net == pytest.approx(0.5)
    assert summary.roi == pytest.approx(0.5 / 3.0)
    assert summary.cote_moyenne == pytest.approx((2.5 + 2.0 + 1.0) / 3.0)


def test_performance_empty() -> None:
    summary = summarize_performance([])
    assert summary.total == 0
    assert summary.reglees == 0
    assert summary.taux_reussite is None
    assert summary.cote_moyenne is None
    assert summary.roi is None
    assert summary.resultat_net == 0.0
