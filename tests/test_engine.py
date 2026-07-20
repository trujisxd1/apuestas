# -*- coding: utf-8 -*-
"""Pruebas del motor: de-vig, consenso, Kelly, value y combinadas.

Correr con:  python -m pytest tests/ -q
(o simplemente:  python tests/test_engine.py  para un resumen sin pytest)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.devig import (
    devig_proportional, devig_power, devig_shin, overround,
    weighted_consensus, agreement_score, book_weight,
)
from src.analysis import (
    expected_value, kelly_stake, practical_stake, evaluate_parlay,
    consensus_probabilities, predict_match,
)
from src.models import Leg
from src.odds_client import demo_events
from datetime import datetime, timezone


# ---------------------------------------------------------------- de-vig

def test_devig_suma_uno():
    odds = {"A": 2.10, "B": 3.40, "C": 4.00}
    for fn in (devig_proportional, devig_power, devig_shin):
        p = fn(odds)
        assert abs(sum(p.values()) - 1.0) < 1e-6, fn.__name__


def test_devig_dos_via_justa():
    # Cuotas 2.00 / 2.00 sin margen -> 50/50 exacto.
    p = devig_proportional({"A": 2.0, "B": 2.0})
    assert abs(p["A"] - 0.5) < 1e-9 and abs(p["B"] - 0.5) < 1e-9


def test_power_corrige_underdog():
    # Con margen real (overround > 1), el método de potencia debe dar MENOS prob al
    # no favorito que el proporcional (corrige el sesgo favorito-longshot).
    odds = {"Fav": 1.30, "Under": 3.00}  # implícitas 0.769 + 0.333 = 1.103 > 1
    assert overround(odds) > 1.0
    prop = devig_proportional(odds)
    powr = devig_power(odds)
    assert powr["Under"] <= prop["Under"] + 1e-9
    assert powr["Fav"] >= prop["Fav"] - 1e-9


def test_overround_positivo():
    # Una casa siempre carga margen: overround > 1.
    assert overround({"A": 1.90, "B": 1.90}) > 1.0


def test_shin_valido():
    p = devig_shin({"A": 1.50, "B": 4.00, "C": 7.00})
    assert all(0.0 <= v <= 1.0 for v in p.values())
    assert abs(sum(p.values()) - 1.0) < 1e-6


# ---------------------------------------------------------------- consenso ponderado

def test_pinnacle_pesa_mas():
    assert book_weight("Pinnacle") > book_weight("Caliente")
    assert book_weight("desconocida") == 1.0


def test_consenso_ignora_casa_basura():
    # Una casa con overround absurdo (>20%) debe ser ignorada.
    per_book = [
        ("Pinnacle", {"A": 2.00, "B": 2.00}),
        ("Basura", {"A": 1.20, "B": 1.20}),  # overround ~1.67, se descarta
    ]
    probs, _ = weighted_consensus(per_book, max_overround=1.20)
    assert abs(probs["A"] - 0.5) < 0.02  # domina Pinnacle, no la basura


def test_agreement_score():
    # Sin dispersión -> 100. Con dispersión de 0.05 -> 0.
    assert agreement_score({"A": 0.0}) == 100.0
    assert agreement_score({"A": 0.05}) == 0.0
    assert 0 < agreement_score({"A": 0.025}) < 100


# ---------------------------------------------------------------- EV / Kelly

def test_ev_signo():
    # Prob 0.5 a cuota 2.10 -> value positivo. A cuota 1.90 -> negativo.
    assert expected_value(0.5, 2.10) > 0
    assert expected_value(0.5, 1.90) < 0


def test_kelly_no_negativo_sin_value():
    # Sin value, Kelly no debe recomendar apostar.
    assert kelly_stake(0.5, 1.90, 100, 0.25) == 0.0


def test_kelly_crece_con_value():
    poco = kelly_stake(0.55, 2.00, 100, 0.25)
    mucho = kelly_stake(0.70, 2.00, 100, 0.25)
    assert mucho > poco > 0


def test_practical_stake_entero_y_topes():
    s = practical_stake(0.9, bankroll=100, min_stake=10, max_stake_pct=15)
    assert s == 10.0  # sube al mínimo de la casa
    assert s == int(s)  # entero
    capped = practical_stake(999, bankroll=100, min_stake=10, max_stake_pct=15)
    assert capped == 15.0  # respeta el tope del 15%
    daily = practical_stake(999, bankroll=100, min_stake=10, max_stake_pct=50, daily_cap=8)
    assert daily == 8.0


# ---------------------------------------------------------------- combinadas

def _leg(prob, odds, event_id="e"):
    return Leg(event="X vs Y", event_id=event_id, market="Resultado", selection="X",
               probability=prob, best_odds=odds, best_bookmaker="Bet365",
               commence_time=datetime.now(timezone.utc))


def test_parlay_multiplica():
    legs = [_leg(0.6, 1.8, "a"), _leg(0.5, 2.0, "b")]
    ev = evaluate_parlay(legs, bankroll=100, kelly_fraction=0.25, min_stake=10, max_stake_pct=15)
    assert abs(ev.combined_probability - 0.30) < 1e-9
    assert abs(ev.combined_odds - 3.60) < 1e-9


def test_parlay_avisa_correlacion():
    # Dos patas del MISMO evento -> debe avisar correlación.
    legs = [_leg(0.6, 1.8, "same"), _leg(0.5, 2.0, "same")]
    ev = evaluate_parlay(legs, bankroll=100, kelly_fraction=0.25, min_stake=10, max_stake_pct=15)
    assert any("correlacion" in w.lower() or "correlación" in w.lower() for w in ev.warnings)


def test_parlay_avisa_loteria():
    legs = [_leg(0.3, 3.0, "a"), _leg(0.3, 3.0, "b")]  # 9% conjunto
    ev = evaluate_parlay(legs, bankroll=100, kelly_fraction=0.25, min_stake=10, max_stake_pct=15)
    assert ev.combined_probability < 0.15
    assert any("loter" in w.lower() for w in ev.warnings)


# ---------------------------------------------------------------- integración con demo

def test_demo_prediction():
    evs = demo_events()
    pred = predict_match(evs[0])
    assert pred is not None
    assert 0 < pred.favorite_probability <= 1
    assert 0 <= pred.trust_score <= 100
    # Las probabilidades de los resultados deben sumar ~1.
    total = sum(o.probability for o in pred.outcomes)
    assert abs(total - 1.0) < 0.02


def test_demo_consenso_suma_uno():
    evs = demo_events()
    probs = consensus_probabilities(evs[0], "h2h")
    assert abs(sum(probs.values()) - 1.0) < 1e-6


# ---------------------------------------------------------------- runner sin pytest

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {fn.__name__}  -> {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} pruebas pasaron")
    sys.exit(0 if passed == len(fns) else 1)
