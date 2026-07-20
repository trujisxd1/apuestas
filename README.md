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

### Mejoras del motor (v2)

- **De-vig ponderado**: quita el margen con el método de **potencia/Shin** (corrige
  el sesgo favorito-underdog, no solo divide entre la suma).
- **Casas "sharp" pesan más**: Pinnacle y los exchanges predicen mejor que una casa
  local, así que aportan más al consenso. Las casas con margen absurdo se descartan.
- **Nivel de confianza**: cada predicción trae qué tan de acuerdo están las casas
  (*acuerdo*), cuántas se usaron y una etiqueta 🟢🟡🟠🔴 de confiabilidad.
- **Enfocado en Caliente**: te dice cómo se ve la apuesta **en tu casa**, no solo
  "la mejor cuota está en Pinnacle" (que no puedes apostar). Filtro *solo Caliente*.
- **Combinadas automáticas**: `/parlay/suggest` arma una combinada sensata (una pata
  por partido) con la matemática real; o ármala tú y ve probabilidad y value al vuelo.
- **Registro real (bankroll)**: apunta cada apuesta, marca ganada/perdida y ve tu
  **ROI, racha, acierto y calibración** del motor. Con **límite diario** que no te deja pasarte.
- **Caché** de 10 min para no quemar las 500 consultas/mes gratuitas de la API.

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

| Endpoint                  | Qué hace                                         |
|---------------------------|--------------------------------------------------|
| `GET /`                   | Panel web                                        |
| `GET /info`               | Estado, config, caché                            |
| `GET /predictions`        | Quién puede ganar, con % y confiabilidad         |
| `GET /events`             | Eventos con cuotas de todas las casas            |
| `GET /value-bets`         | Apuestas con value (`?only_caliente=true`)       |
| `GET /best`               | La mejor apuesta (mayor value)                   |
| `GET /legs`               | Patas seleccionables para combinar               |
| `GET /parlay/suggest`     | Combinada armada por el motor (`?size=3`)        |
| `POST /parlay/evaluate`   | Evalúa una combinada tuya                        |
| `GET /bets` · `POST /bets`| Historial / registrar apuesta                    |
| `POST /bets/{id}/settle`  | Marcar ganada/perdida/nula                       |
| `GET /stats`              | Bankroll, ROI, racha, calibración                |
| `GET /usage`              | Requests restantes de tu API key                 |

Parámetro `?sport=ligamx` (o mlb, epl…) en los de lectura.

## Pruebas

```bash
python -m pytest tests/ -q        # con pytest
python tests/test_engine.py       # sin pytest (resumen rápido)
```

## Estructura

```
betting-platform/
├── src/
│   ├── config.py       # configuración desde .env
│   ├── models.py       # tipos de datos (Event, ValueBet, ParlayEvaluation…)
│   ├── odds_client.py  # cliente The Odds API + modo demo + caché
│   ├── devig.py        # de-vig ponderado (potencia/Shin) + consenso  ← el cerebro
│   ├── analysis.py     # predicción, EV, Kelly, value, combinadas
│   ├── cache.py        # caché en memoria con expiración
│   ├── store.py        # registro de apuestas en SQLite (bankroll real)
│   └── api.py          # API FastAPI
├── web/index.html      # panel web
├── tests/test_engine.py
├── cli.py              # línea de comandos
├── requirements.txt
└── .env.example
```

## Límites sanos (recomendado)

- Apuesta **poco** por jugada (Kelly fraccionado ya lo hace por ti).
- Si un día no hay value, la app te dice *"no apostar"* — **hazle caso**.
- Ponte un tope diario y un stop-loss. Perder está permitido; perder el control no.
- México, ayuda por juego problemático: **Línea de la Vida 800 911 2000**.
