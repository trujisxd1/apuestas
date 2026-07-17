# 🎯 Plataforma de Value Betting

Motor de análisis + API REST que detecta **apuestas con value** comparando el
consenso del mercado contra la mejor cuota disponible. No adivina ganadores:
encuentra cuándo una casa te paga **de más** (ventaja estadística real).

> ⚠️ Apostar es entretenimiento, no una inversión. La casa siempre tiene ventaja
> matemática. El value **reduce** ese margen en tu contra a largo plazo; **no
> garantiza** ganar ninguna apuesta individual. Úsalo con límites y cabeza fría.

## Cómo funciona (el método pro)

1. Cada casa publica cuotas con un **margen** (overround) a su favor.
2. Juntamos **muchas casas**, le quitamos el margen a cada una (*de-vig*) y
   promediamos → esa es la **probabilidad justa** del consenso.
3. Si una casa (ej. Caliente) paga una cuota **mayor** a la que corresponde a esa
   probabilidad → hay **VALUE** (+EV). El motor lo detecta y calcula cuánto apostar
   con **Kelly fraccionado** (conservador).

## Instalación

```bash
cd betting-platform
pip install -r requirements.txt
```

## Modo demo (funciona YA, sin API key)

```bash
python cli.py best              # la mejor apuesta (datos de ejemplo)
python cli.py value             # todas las apuestas con value
python cli.py events            # eventos y cuotas
```

## Modo real (cuotas en vivo)

1. Consigue tu API key gratis (500 req/mes) en <https://the-odds-api.com/>
2. Copia `.env.example` a `.env` y pon tu key en `ODDS_API_KEY`.
3. Ajusta `BANKROLL`, `MIN_EDGE`, `KELLY_FRACTION` a tu gusto.

```bash
python cli.py best --sport ligamx
python cli.py best --sport mlb
python cli.py value --sport epl
python cli.py usage             # cuántas requests te quedan
```

Ligas disponibles: `ligamx`, `epl`, `laliga`, `champions`, `mlb`, `nba`, `nfl`
(o cualquier `sport_key` de The Odds API).

## API REST (FastAPI)

```bash
uvicorn src.api:app --reload
```

Luego abre <http://127.0.0.1:8000/docs> (documentación interactiva). Endpoints:

| Endpoint       | Qué hace                                    |
|----------------|---------------------------------------------|
| `GET /`        | Estado y configuración                      |
| `GET /events`  | Eventos con cuotas de todas las casas       |
| `GET /value-bets` | Todas las apuestas con value              |
| `GET /best`    | La mejor apuesta (mayor value)              |
| `GET /usage`   | Requests restantes de tu API key            |

Parámetro `?sport=ligamx` (o mlb, epl…) en todos.

## Estructura

```
betting-platform/
├── src/
│   ├── config.py       # configuración desde .env
│   ├── models.py       # tipos de datos (Event, ValueBet…)
│   ├── odds_client.py  # cliente The Odds API + modo demo
│   ├── analysis.py     # de-vig, EV, Kelly, detección de value  ← el cerebro
│   └── api.py          # API FastAPI
├── cli.py              # línea de comandos
├── requirements.txt
└── .env.example
```

## Límites sanos (recomendado)

- Apuesta **poco** por jugada (Kelly fraccionado ya lo hace por ti).
- Si un día no hay value, la app te dice *"no apostar"* — **hazle caso**.
- Ponte un tope diario y un stop-loss. Perder está permitido; perder el control no.
- México, ayuda por juego problemático: **Línea de la Vida 800 911 2000**.
