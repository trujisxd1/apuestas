"""Métodos de de-vig (quitar el margen de la casa) y consenso ponderado.

¿Por qué hay varios métodos? Porque quitar el margen NO es tan simple como dividir
entre la suma. Las casas no reparten su margen por igual: cargan MÁS margen sobre los
"no favoritos" (favourite-longshot bias). Si usas el método simple, terminas creyendo
que el underdog tiene más probabilidad de la real.

Métodos implementados (de peor a mejor):
  - proportional: p_i / suma.   Simple, pero sesgado (sobreestima al no favorito).
  - power:        p_i^k con k tal que la suma sea 1. Corrige el sesgo. <- DEFAULT
  - shin:         modelo de "apostadores informados". El estándar académico.

Además: no todas las casas son igual de buenas prediciendo. Pinnacle y los exchanges
(Betfair, Smarkets) son los que mejor clavan la probabilidad real porque aceptan
apostadores profesionales. Por eso pesan más en el consenso.
"""
from __future__ import annotations

import math
from collections import defaultdict

# Peso de cada casa en el consenso. Más peso = más confiable históricamente.
# Pinnacle y los exchanges son "sharp": mueven líneas con dinero profesional.
_BOOK_WEIGHTS: dict[str, float] = {
    "pinnacle": 3.0,
    "betfair": 2.5,
    "betfair exchange": 2.5,
    "smarkets": 2.2,
    "matchbook": 2.2,
    "circa sports": 2.0,
    "bookmaker.eu": 1.8,
    "bet365": 1.5,
    "william hill": 1.4,
    "1xbet": 1.2,
    "unibet": 1.2,
    "betmgm": 1.1,
    "draftkings": 1.1,
    "fanduel": 1.1,
    "caesars": 1.0,
    "caliente": 0.8,  # casa local: buena para apostar, floja para predecir
}
_DEFAULT_WEIGHT = 1.0


def book_weight(bookmaker: str) -> float:
    """Cuánto pesa esta casa al estimar la probabilidad real."""
    return _BOOK_WEIGHTS.get(bookmaker.strip().lower(), _DEFAULT_WEIGHT)


def implied_prob(decimal_odds: float) -> float:
    """Probabilidad implícita cruda de una cuota decimal (todavía incluye el margen)."""
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / decimal_odds


def overround(odds: dict[str, float]) -> float:
    """Margen de la casa. 1.05 = 5% de ventaja para ellos. Menor = casa más honesta."""
    return sum(implied_prob(p) for p in odds.values())


# ---------------------------------------------------------------- métodos

def devig_proportional(odds: dict[str, float]) -> dict[str, float]:
    """Método simple: normaliza para que sumen 1. Rápido pero sesgado."""
    raw = {n: implied_prob(p) for n, p in odds.items()}
    total = sum(raw.values())
    if total <= 0:
        return {n: 0.0 for n in odds}
    return {n: p / total for n, p in raw.items()}


def devig_power(odds: dict[str, float], *, tol: float = 1e-9, max_iter: int = 100) -> dict[str, float]:
    """Método de potencia: busca k tal que sum(p_i^k) == 1.

    Como k > 1, los valores chicos (no favoritos) se encogen MÁS que los grandes.
    Eso es justo lo que hay que corregir: las casas inflan al underdog.
    """
    raw = {n: implied_prob(p) for n, p in odds.items()}
    total = sum(raw.values())
    if total <= 0:
        return {n: 0.0 for n in odds}
    if len(raw) < 2 or abs(total - 1.0) < tol:
        return {n: p / total for n, p in raw.items()}

    def _sum_pow(k: float) -> float:
        return sum(p ** k for p in raw.values() if p > 0)

    # sum(p^k) decrece cuando k crece (todas las p < 1). Bisección para llegar a 1.
    lo, hi = 0.2, 10.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        s = _sum_pow(mid)
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2.0

    out = {n: (p ** k if p > 0 else 0.0) for n, p in raw.items()}
    s = sum(out.values())
    if s <= 0:
        return devig_proportional(odds)
    return {n: p / s for n, p in out.items()}  # renormaliza el residuo numérico


def devig_shin(odds: dict[str, float], *, tol: float = 1e-10, max_iter: int = 200) -> dict[str, float]:
    """Método de Shin: modela que parte del dinero viene de apostadores con información.

    Estima z = proporción de dinero "informado" y despeja la probabilidad real.
    Es el método más aceptado académicamente para mercados de 3 vías.
    """
    raw = [implied_prob(p) for p in odds.values()]
    names = list(odds.keys())
    total = sum(raw)
    if total <= 0:
        return {n: 0.0 for n in odds}
    if len(raw) < 2 or abs(total - 1.0) < tol:
        return {n: p / total for n, p in zip(names, raw)}

    def _probs(z: float) -> list[float]:
        if z >= 1.0:
            z = 0.999999
        denom = 2.0 * (1.0 - z)
        out = []
        for pi in raw:
            inner = z * z + 4.0 * (1.0 - z) * (pi * pi) / total
            out.append((math.sqrt(max(inner, 0.0)) - z) / denom)
        return out

    # Buscamos z tal que las probabilidades sumen 1.
    lo, hi = 0.0, 0.5
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        s = sum(_probs(mid))
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    z = (lo + hi) / 2.0

    vals = _probs(z)
    s = sum(vals)
    if s <= 0:
        return devig_proportional(odds)
    return {n: v / s for n, v in zip(names, vals)}


_METHODS = {
    "proportional": devig_proportional,
    "power": devig_power,
    "shin": devig_shin,
}


def devig_book(odds: dict[str, float], method: str = "power") -> dict[str, float]:
    """Quita el margen de UNA casa con el método elegido."""
    fn = _METHODS.get(method, devig_power)
    return fn(odds)


# ---------------------------------------------------------------- consenso

def weighted_consensus(
    per_book: list[tuple[str, dict[str, float]]],
    *,
    method: str = "power",
    max_overround: float = 1.20,
) -> tuple[dict[str, float], dict[str, float]]:
    """Combina las cuotas de varias casas en UNA probabilidad de consenso.

    per_book: [(nombre_casa, {selección: cuota}), ...]
    return:   (probabilidades, dispersión por selección)

    La dispersión (desviación estándar entre casas) dice qué tan de acuerdo están.
    Poca dispersión = mercado seguro. Mucha = las casas no se ponen de acuerdo y la
    predicción es menos confiable.
    """
    acc: dict[str, list[tuple[float, float]]] = defaultdict(list)  # sel -> [(prob, peso)]

    for name, odds in per_book:
        if len(odds) < 2:
            continue
        # Casa con margen absurdo (>20%) = cuotas basura, la ignoramos.
        if overround(odds) > max_overround:
            continue
        w = book_weight(name)
        for sel, prob in devig_book(odds, method).items():
            acc[sel].append((prob, w))

    if not acc:
        return {}, {}

    probs: dict[str, float] = {}
    spread: dict[str, float] = {}
    for sel, pairs in acc.items():
        tw = sum(w for _, w in pairs)
        if tw <= 0:
            continue
        mean = sum(p * w for p, w in pairs) / tw
        probs[sel] = mean
        if len(pairs) > 1:
            var = sum(w * (p - mean) ** 2 for p, w in pairs) / tw
            spread[sel] = math.sqrt(max(var, 0.0))
        else:
            spread[sel] = 0.0

    total = sum(probs.values())
    if total <= 0:
        return {}, {}
    return {n: p / total for n, p in probs.items()}, spread


def agreement_score(spread: dict[str, float]) -> float:
    """0-100: qué tan de acuerdo están las casas. 100 = todas dicen lo mismo.

    Una desviación de 0.05 (5 puntos porcentuales) ya es mucha discrepancia.
    """
    if not spread:
        return 0.0
    worst = max(spread.values())
    return max(0.0, min(100.0, 100.0 * (1.0 - worst / 0.05)))
