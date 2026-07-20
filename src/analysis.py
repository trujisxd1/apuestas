"""Motor de análisis: de-vig, probabilidad justa de consenso, EV, Kelly y detección de value.

Idea central (el método que usan los profesionales):
1. Cada casa publica cuotas con un margen (overround) a su favor.
2. Si juntamos MUCHAS casas y le quitamos el margen a cada una, el promedio ponderado
   de esas probabilidades "limpias" es la mejor estimación de la probabilidad REAL.
3. Cuando UNA casa paga una cuota mayor a la justa, ahí hay VALUE: nos pagan de más.

Mejoras sobre el consenso simple (ver src/devig.py):
- De-vig con método de potencia/Shin (corrige el sesgo favorito-underdog).
- Casas "sharp" (Pinnacle, exchanges) pesan más; casas locales pesan menos.
- Medimos el ACUERDO entre casas: si discrepan mucho, avisamos que es menos confiable.
- Comparamos contra TU casa (Caliente) para que la recomendación sea accionable.
"""
from __future__ import annotations

from collections import defaultdict

from .config import settings
from .devig import (
    agreement_score,
    overround,
    weighted_consensus,
)
from .models import (
    Event,
    Leg,
    MatchPrediction,
    OutcomeProb,
    ParlayEvaluation,
    ParlayLegResult,
    ValueBet,
)

# Traducción de nombres genéricos de resultado.
_TRAD = {"Draw": "Empate", "Tie": "Empate"}

# Casa propia del usuario (donde realmente apuesta).
MY_BOOK = "caliente"


def _es(name: str) -> str:
    return _TRAD.get(name, name)


# Etiquetas legibles de cada mercado.
_MARKET_LABEL = {"h2h": "Resultado", "totals": "Goles", "btts": "Ambos anotan"}


def _leg_selection_text(market: str, raw_name: str) -> str:
    """Convierte el nombre crudo de la API en texto listo para mostrar."""
    if market == "totals":
        parts = raw_name.split()
        line = parts[-1] if parts and parts[-1].replace(".", "").isdigit() else ""
        if raw_name.startswith("Over"):
            return f"Más de {line} goles"
        if raw_name.startswith("Under"):
            return f"Menos de {line} goles"
        return raw_name
    if market == "btts":
        if raw_name.lower().startswith("y"):
            return "Ambos anotan: Sí"
        return "Ambos anotan: No"
    return _es(raw_name)


# --------------------------------------------------------------- consenso

def _books_for_market(event: Event, market: str) -> list[tuple[str, dict[str, float]]]:
    """[(casa, {selección: cuota})] para un mercado."""
    out: list[tuple[str, dict[str, float]]] = []
    for bm in event.markets:
        if bm.market != market:
            continue
        out.append((bm.bookmaker, {o.name: o.price for o in bm.outcomes}))
    return out


def consensus_probabilities(event: Event, market: str = "h2h") -> dict[str, float]:
    """Probabilidad justa de consenso por selección (ponderada, sin margen)."""
    probs, _ = weighted_consensus(_books_for_market(event, market), method="power")
    return probs


def consensus_with_spread(event: Event, market: str = "h2h"):
    """Igual que consensus_probabilities pero devuelve también la dispersión."""
    return weighted_consensus(_books_for_market(event, market), method="power")


def best_price_per_selection(event: Event, market: str = "h2h") -> dict[str, tuple[str, float]]:
    """Mejor cuota (la más alta) por selección y en qué casa está. {sel: (casa, cuota)}"""
    best: dict[str, tuple[str, float]] = {}
    for bm in event.markets:
        if bm.market != market:
            continue
        for o in bm.outcomes:
            if o.name not in best or o.price > best[o.name][1]:
                best[o.name] = (bm.bookmaker, o.price)
    return best


def my_book_price(event: Event, selection: str, market: str = "h2h") -> float | None:
    """Cuota de TU casa (Caliente) para una selección, si la ofrece."""
    for bm in event.markets:
        if bm.market != market or bm.bookmaker.strip().lower() != MY_BOOK:
            continue
        for o in bm.outcomes:
            if o.name == selection:
                return o.price
    return None


def market_overround_pct(event: Event, market: str = "h2h") -> float:
    """Margen promedio de las casas en este mercado, en %."""
    ors = []
    for _, odds in _books_for_market(event, market):
        if len(odds) >= 2:
            ors.append(overround(odds))
    if not ors:
        return 0.0
    return (sum(ors) / len(ors) - 1.0) * 100.0


def expected_value(prob: float, decimal_odds: float) -> float:
    """EV por unidad apostada. Positivo = apuesta con value."""
    return prob * (decimal_odds - 1.0) - (1.0 - prob)


def kelly_stake(prob: float, decimal_odds: float, bankroll: float, fraction: float) -> float:
    """Monto a apostar según Kelly fraccionado. Nunca negativo."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    full_kelly = (b * prob - (1.0 - prob)) / b
    stake = bankroll * full_kelly * fraction
    return max(0.0, round(stake, 2))


# --------------------------------------------------------------- confiabilidad

def _confidence_label(top_prob: float, is_draw: bool) -> str:
    if top_prob >= 0.65:
        return "Favorito fuerte 💪"
    if top_prob >= 0.55:
        return "Favorito claro"
    if top_prob >= 0.45:
        return "Ligera ventaja"
    return "Partido muy parejo ⚖️"


def _reliability(n_books: int, agreement: float) -> tuple[str, float]:
    """Qué tan confiable es la predicción: más casas + más acuerdo = más confianza."""
    # Componente por número de casas (satura ~8 casas).
    book_comp = min(1.0, n_books / 8.0)
    # Componente por acuerdo entre casas.
    agree_comp = agreement / 100.0
    trust = 100.0 * (0.45 * book_comp + 0.55 * agree_comp)

    if trust >= 70:
        label = "Dato muy confiable 🟢"
    elif trust >= 50:
        label = "Dato confiable 🟡"
    elif trust >= 30:
        label = "Tómalo con reservas 🟠"
    else:
        label = "Poco confiable 🔴"
    return label, round(trust, 1)


def predict_match(event: Event, market: str = "h2h", min_books: int = 2) -> MatchPrediction | None:
    """Predicción de UN partido: probabilidad de cada resultado según el consenso
    ponderado, con nivel de confiabilidad y comparación contra tu casa."""
    fair, spread = consensus_with_spread(event, market)
    n_books = sum(1 for bm in event.markets if bm.market == market)
    if not fair or n_books < min_books:
        return None

    ordered = sorted(fair.items(), key=lambda kv: kv[1], reverse=True)
    outcomes = [
        OutcomeProb(name=_es(name), probability=p, fair_odds=(1.0 / p) if p > 0 else 0.0)
        for name, p in ordered
    ]
    fav_name, fav_p = ordered[0]
    is_draw = _es(fav_name) == "Empate"

    agreement = agreement_score(spread)
    reliability, trust = _reliability(n_books, agreement)
    mor = market_overround_pct(event, market)

    second = ordered[1] if len(ordered) > 1 else None
    if is_draw:
        analysis = (
            f"El mercado ve el partido tan parejo que el resultado más probable es el "
            f"empate ({fav_p*100:.0f}%). No hay un favorito claro para ganar."
        )
    elif fav_p >= 0.65:
        analysis = (
            f"{_es(fav_name)} es claramente el más probable para ganar ({fav_p*100:.0f}%). "
            f"El mercado lo ve como favorito fuerte."
        )
    elif fav_p >= 0.50:
        extra = f" {_es(second[0])} le sigue con {second[1]*100:.0f}%." if second else ""
        analysis = f"{_es(fav_name)} es favorito ({fav_p*100:.0f}%), pero no es seguro.{extra}"
    else:
        extra = f" (vs {_es(second[0])} {second[1]*100:.0f}%)" if second else ""
        analysis = (
            f"Partido parejo: {_es(fav_name)} apenas encabeza con {fav_p*100:.0f}%{extra}. "
            f"Difícil de acertar — cuidado aquí."
        )

    if agreement < 40:
        analysis += " ⚠️ Ojo: las casas no coinciden mucho, la estimación es menos firme."

    # ¿Hay value en el favorito? Y ¿cómo se ve en TU casa?
    value_note = None
    my_book_note = None
    best = best_price_per_selection(event, market)
    if fav_name in best:
        _, price = best[fav_name]
        edge = expected_value(fav_p, price) * 100
        if edge >= 2.0:
            value_note = f"Además, la mejor cuota del favorito ({price:.2f}) trae +{edge:.1f}% de value."

    my_price = my_book_price(event, fav_name, market)
    if my_price is not None:
        my_edge = expected_value(fav_p, my_price) * 100
        if my_edge >= 1.0:
            my_book_note = (
                f"En Caliente el favorito paga {my_price:.2f} → +{my_edge:.1f}% de value. "
                f"Ahí SÍ puedes apostarlo."
            )
        else:
            my_book_note = (
                f"En Caliente el favorito paga {my_price:.2f} (cuota justa {1/fav_p:.2f}). "
                f"Sin value, pero es el resultado más probable."
            )

    return MatchPrediction(
        event=event.label,
        sport=event.sport_title,
        commence_time=event.commence_time,
        outcomes=outcomes,
        favorite=_es(fav_name),
        favorite_probability=fav_p,
        confidence=_confidence_label(fav_p, is_draw),
        analysis=analysis,
        num_books=n_books,
        value_note=value_note,
        agreement=round(agreement, 1),
        reliability=reliability,
        trust_score=trust,
        market_overround=round(mor, 1),
        my_book_note=my_book_note,
    )


def predict_all(events: list[Event], market: str = "h2h", min_books: int = 2) -> list[MatchPrediction]:
    """Predicciones ordenadas por confianza global (trust) y luego por claridad del favorito."""
    preds = [p for ev in events if (p := predict_match(ev, market, min_books))]
    preds.sort(key=lambda p: (p.trust_score, p.favorite_probability), reverse=True)
    return preds


def safe_picks(
    events: list[Event],
    *,
    min_prob: float = 0.72,
    min_trust: float = 40.0,
    market: str = "h2h",
    min_books: int = 2,
) -> list[MatchPrediction]:
    """MODO ALTA CONFIANZA: solo los pronósticos que casi siempre entran.

    Un pick entra en la lista solo si cumple TODO esto:
      - El favorito es un EQUIPO (nunca un empate: un empate nunca es 'seguro').
      - Su probabilidad de ganar es alta (min_prob, default 72%).
      - Las casas están de acuerdo (min_trust): si discrepan, no es seguro.

    Ojo honesto: entre más alto pongas min_prob, MENOS partidos aparecen (a veces
    ninguno) y MENOS pagan. Acertar mucho = ganar poco. Es matemática, no magia.
    """
    picks: list[MatchPrediction] = []
    for ev in events:
        p = predict_match(ev, market, min_books)
        if p is None:
            continue
        if p.favorite == "Empate":
            continue
        if p.favorite_probability >= min_prob and p.trust_score >= min_trust:
            picks.append(p)
    picks.sort(key=lambda p: (p.favorite_probability, p.trust_score), reverse=True)
    return picks


# --------------------------------------------------------------- combinadas

def build_legs(events: list[Event], markets: tuple[str, ...] = ("h2h", "totals", "btts")) -> list[Leg]:
    """Patas seleccionables para combinadas, con prob. de consenso, acuerdo y cuota de tu casa."""
    legs: list[Leg] = []
    for ev in events:
        for mk in markets:
            fair, spread = consensus_with_spread(ev, mk)
            if not fair:
                continue
            best = best_price_per_selection(ev, mk)
            agree = agreement_score(spread)
            for raw_name, prob in fair.items():
                if raw_name not in best or prob <= 0:
                    continue
                book, price = best[raw_name]
                legs.append(
                    Leg(
                        event=ev.label,
                        event_id=ev.id,
                        market=_MARKET_LABEL.get(mk, mk),
                        selection=_leg_selection_text(mk, raw_name),
                        probability=prob,
                        best_odds=price,
                        best_bookmaker=book,
                        commence_time=ev.commence_time,
                        agreement=round(agree, 1),
                        my_book_odds=my_book_price(ev, raw_name, mk),
                    )
                )
    # Ordena por probabilidad desc: las patas más "seguras" primero.
    legs.sort(key=lambda l: l.probability, reverse=True)
    return legs


def evaluate_parlay(
    legs: list[Leg],
    *,
    bankroll: float,
    kelly_fraction: float,
    min_stake: float,
    max_stake_pct: float,
) -> ParlayEvaluation:
    """Evalúa una combinada YA armada: probabilidad real, value y cuánto apostar.

    Recuerda: en una combinada TODAS las patas deben acertar. La probabilidad
    conjunta es el producto — por eso 4 patas de 60% dan solo ~13%.
    """
    warnings: list[str] = []
    prob = 1.0
    odds = 1.0
    results: list[ParlayLegResult] = []
    for lg in legs:
        prob *= lg.probability
        odds *= lg.best_odds
        results.append(
            ParlayLegResult(
                event=lg.event,
                selection=lg.selection,
                probability=lg.probability,
                odds=lg.best_odds,
                bookmaker=lg.best_bookmaker,
            )
        )

    fair_odds = (1.0 / prob) if prob > 0 else 0.0
    edge = expected_value(prob, odds) * 100 if prob > 0 else -100.0

    # Stake: Kelly sobre la combinada, con topes prácticos.
    raw = kelly_stake(prob, odds, bankroll, kelly_fraction)
    stake = practical_stake(raw, bankroll=bankroll, min_stake=min_stake, max_stake_pct=max_stake_pct)
    payout = round(stake * odds, 2)

    # Avisos.
    same_event = [e for e, c in _count_events(legs).items() if c > 1]
    if same_event:
        warnings.append(
            "Tienes varias patas del MISMO partido: están correlacionadas, así que la "
            "probabilidad real puede ser distinta a la del cálculo (que asume independencia)."
        )
    if prob < 0.15:
        warnings.append(
            f"Probabilidad de que entre completa: {prob*100:.1f}%. Es casi un billete de "
            f"lotería — divertido, pero no cuentes con ello."
        )
    if len(legs) >= 5:
        warnings.append(
            f"{len(legs)} patas es mucho: cada una multiplica el riesgo. El margen de la "
            f"casa se acumula en cada pata."
        )

    # Veredicto.
    if edge > 3:
        verdict = f"Combinada con value (+{edge:.1f}%). Rara, pero esta pinta bien."
    elif edge >= -3:
        verdict = f"Combinada neutral ({edge:+.1f}%). Para divertirte con poco, ok."
    else:
        verdict = f"Combinada con value negativo ({edge:.1f}%). La casa tiene ventaja aquí."

    return ParlayEvaluation(
        legs=results,
        combined_probability=prob,
        combined_odds=round(odds, 2),
        fair_odds=round(fair_odds, 2),
        edge_pct=round(edge, 1),
        stake_suggestion=stake,
        payout=payout,
        verdict=verdict,
        warnings=warnings,
    )


def _count_events(legs: list[Leg]) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for lg in legs:
        c[lg.event_id] += 1
    return c


def suggest_parlay(
    events: list[Event],
    *,
    bankroll: float,
    kelly_fraction: float,
    min_stake: float,
    max_stake_pct: float,
    size: int = 3,
    max_size: int = 4,
) -> ParlayEvaluation | None:
    """Arma automáticamente una combinada 'sensata': las patas más probables de
    partidos DISTINTOS (para evitar correlación). Es la combinada con mejor balance
    entre acertar y pagar algo interesante."""
    all_legs = build_legs(events)
    # Solo patas decentes y de mercados de resultado/goles (evita ruido).
    candidates = [l for l in all_legs if l.probability >= 0.45 and l.agreement >= 40]

    # Una pata por partido: la más probable de cada evento.
    best_per_event: dict[str, Leg] = {}
    for lg in candidates:
        cur = best_per_event.get(lg.event_id)
        if cur is None or lg.probability > cur.probability:
            best_per_event[lg.event_id] = lg

    picked = sorted(best_per_event.values(), key=lambda l: l.probability, reverse=True)
    size = max(2, min(size, max_size, len(picked)))
    if len(picked) < 2:
        return None
    return evaluate_parlay(
        picked[:size],
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        min_stake=min_stake,
        max_stake_pct=max_stake_pct,
    )


# --------------------------------------------------------------- stakes / value

def practical_stake(
    raw_stake: float,
    *,
    bankroll: float,
    min_stake: float,
    max_stake_pct: float,
    daily_cap: float | None = None,
) -> float:
    """Convierte el monto teórico de Kelly en un monto REAL y apostable en pesos."""
    if raw_stake <= 0:
        return 0.0
    max_by_pct = bankroll * (max_stake_pct / 100.0)
    stake = max(min_stake, raw_stake)
    stake = min(stake, max_by_pct)
    if daily_cap is not None:
        stake = min(stake, max(0.0, daily_cap))
    return float(round(stake))


def find_value_bets(
    events: list[Event],
    *,
    bankroll: float,
    kelly_fraction: float,
    min_edge_pct: float,
    market: str = "h2h",
    min_books: int = 2,
    min_stake: float = 10.0,
    max_stake_pct: float = 15.0,
    daily_cap: float | None = None,
    only_my_book: bool = False,
) -> list[ValueBet]:
    """Apuestas con value, ordenadas de mayor a menor edge.

    only_my_book: si True, solo cuenta el value que existe EN TU CASA (Caliente),
    porque de nada sirve un value en Pinnacle si no puedes apostar ahí.
    """
    results: list[ValueBet] = []

    for ev in events:
        fair, spread = consensus_with_spread(ev, market)
        if not fair:
            continue
        n_books = sum(1 for bm in ev.markets if bm.market == market)
        if n_books < min_books:
            continue

        best = best_price_per_selection(ev, market)
        agree = agreement_score(spread)
        for selection, prob in fair.items():
            if prob <= 0:
                continue

            if only_my_book:
                price = my_book_price(ev, selection, market)
                if price is None:
                    continue
                book = "Caliente"
            else:
                if selection not in best:
                    continue
                book, price = best[selection]

            edge = expected_value(prob, price)
            edge_pct = edge * 100.0
            if edge_pct < min_edge_pct:
                continue

            raw = kelly_stake(prob, price, bankroll, kelly_fraction)
            stake = practical_stake(
                raw, bankroll=bankroll, min_stake=min_stake,
                max_stake_pct=max_stake_pct, daily_cap=daily_cap,
            )

            results.append(
                ValueBet(
                    event=ev.label,
                    sport=ev.sport_title,
                    commence_time=ev.commence_time,
                    selection=_es(selection),
                    best_bookmaker=book,
                    best_price=price,
                    fair_price=(1.0 / prob) if prob > 0 else 0.0,
                    fair_probability=prob,
                    edge_pct=edge_pct,
                    stake_suggestion=stake,
                    num_books=n_books,
                )
            )

    results.sort(key=lambda v: v.edge_pct, reverse=True)
    return results
