"""CLI de la plataforma de value betting.

Uso:
    python cli.py best                 # la mejor apuesta de Liga MX
    python cli.py best --sport mlb      # la mejor apuesta de MLB
    python cli.py value --sport epl     # todas las apuestas con value
    python cli.py events --sport ligamx # eventos y cuotas
    python cli.py usage                 # cuántas requests te quedan
"""
from __future__ import annotations

import argparse
import sys

# La consola de Windows suele venir en cp1252 y no traga emojis/acentos.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

from src.analysis import find_value_bets
from src.config import settings
from src.odds_client import OddsClient, POPULAR_SPORTS


def _banner():
    mode = "DEMO (sin API key — datos de ejemplo)" if settings.demo_mode else "LIVE"
    print("=" * 64)
    print(f"  PLATAFORMA DE VALUE BETTING  ·  modo: {mode}")
    print(f"  Bankroll: ${settings.bankroll:.0f}  |  Kelly: {settings.kelly_fraction}  |  "
          f"Value mín: {settings.min_edge}%")
    print("=" * 64)


def cmd_best(client: OddsClient, sport: str):
    evs = client.fetch_events(POPULAR_SPORTS.get(sport, sport))
    bets = find_value_bets(
        evs, bankroll=settings.bankroll, kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge, min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
    )
    if not bets:
        print("\n🚫 Hoy NO hay apuestas con value suficiente.")
        print("   La mejor decisión hoy: NO apostar. Guardar la lana también es ganar.\n")
        return
    print("\n⭐ MEJOR APUESTA DEL DÍA:\n")
    print(bets[0].summary())
    print("\n⚠️  Value ≠ garantía. Es una ventaja estadística a largo plazo, no un premio seguro.\n")


def cmd_value(client: OddsClient, sport: str):
    evs = client.fetch_events(POPULAR_SPORTS.get(sport, sport))
    bets = find_value_bets(
        evs, bankroll=settings.bankroll, kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge, min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
    )
    if not bets:
        print("\n🚫 Sin apuestas con value hoy. No apostar es la jugada correcta.\n")
        return
    print(f"\n💎 {len(bets)} apuesta(s) con value (mayor a menor):\n")
    for i, b in enumerate(bets, 1):
        print(f"{i}. {b.summary()}\n")


def cmd_events(client: OddsClient, sport: str):
    evs = client.fetch_events(POPULAR_SPORTS.get(sport, sport))
    if not evs:
        print("\nSin eventos para ese deporte ahora mismo.\n")
        return
    print(f"\n📅 {len(evs)} evento(s):\n")
    for ev in evs:
        print(f"• {ev.label}  [{ev.sport_title}]  — {ev.commence_time:%d/%m %H:%M} UTC "
              f"({len([m for m in ev.markets if m.market=='h2h'])} casas)")
    print()


def cmd_usage(client: OddsClient, _sport: str):
    print("\n📊 Uso de la API:", client.usage(), "\n")


COMMANDS = {"best": cmd_best, "value": cmd_value, "events": cmd_events, "usage": cmd_usage}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plataforma de value betting")
    parser.add_argument("command", choices=COMMANDS.keys(), help="Qué quieres hacer")
    parser.add_argument("--sport", default="ligamx",
                        help=f"Liga. Opciones: {', '.join(POPULAR_SPORTS)} (o una clave de The Odds API)")
    args = parser.parse_args(argv)

    _banner()
    client = OddsClient()
    try:
        COMMANDS[args.command](client, args.sport)
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Error: {exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
