"""Registro de apuestas en SQLite: lo que realmente apostaste y cómo te fue.

Esto es lo único que te dice LA VERDAD. Todos creemos que vamos ganando porque
recordamos los aciertos y olvidamos las fallas. El registro no olvida.

También sirve para medir si el motor sirve: si las apuestas que marcó con 60% de
probabilidad ganan cerca del 60% de las veces, el modelo está calibrado.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "apuestas.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    event         TEXT    NOT NULL,
    selection     TEXT    NOT NULL,
    market        TEXT    NOT NULL DEFAULT 'Resultado',
    bookmaker     TEXT    NOT NULL DEFAULT 'Caliente',
    odds          REAL    NOT NULL,
    stake         REAL    NOT NULL,
    probability   REAL,               -- lo que el motor estimó (para calibración)
    is_parlay     INTEGER NOT NULL DEFAULT 0,
    status        TEXT    NOT NULL DEFAULT 'pendiente',  -- pendiente|ganada|perdida|nula
    payout        REAL    NOT NULL DEFAULT 0,
    settled_at    TEXT,
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
"""

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _lock, _connect() as con:
        con.executescript(_SCHEMA)


def add_bet(
    *,
    event: str,
    selection: str,
    odds: float,
    stake: float,
    market: str = "Resultado",
    bookmaker: str = "Caliente",
    probability: float | None = None,
    is_parlay: bool = False,
    notes: str | None = None,
) -> int:
    with _lock, _connect() as con:
        cur = con.execute(
            """INSERT INTO bets
               (created_at, event, selection, market, bookmaker, odds, stake,
                probability, is_parlay, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (_now(), event, selection, market, bookmaker, odds, stake,
             probability, 1 if is_parlay else 0, notes),
        )
        return int(cur.lastrowid)


def settle_bet(bet_id: int, status: str) -> bool:
    """Marca una apuesta como ganada/perdida/nula y calcula el pago."""
    status = status.lower().strip()
    if status not in {"ganada", "perdida", "nula"}:
        raise ValueError("status debe ser: ganada, perdida o nula")

    with _lock, _connect() as con:
        row = con.execute("SELECT odds, stake FROM bets WHERE id = ?", (bet_id,)).fetchone()
        if row is None:
            return False
        if status == "ganada":
            payout = row["stake"] * row["odds"]
        elif status == "nula":
            payout = row["stake"]          # te devuelven lo apostado
        else:
            payout = 0.0
        con.execute(
            "UPDATE bets SET status = ?, payout = ?, settled_at = ? WHERE id = ?",
            (status, payout, _now(), bet_id),
        )
        return True


def delete_bet(bet_id: int) -> bool:
    with _lock, _connect() as con:
        cur = con.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
        return cur.rowcount > 0


def list_bets(limit: int = 100) -> list[dict]:
    with _lock, _connect() as con:
        rows = con.execute(
            "SELECT * FROM bets ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def stats(bankroll_inicial: float) -> dict:
    """Números reales: cuánto llevas ganado/perdido, ROI, racha y calibración."""
    with _lock, _connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()]

    resueltas = [b for b in rows if b["status"] in ("ganada", "perdida")]
    pendientes = [b for b in rows if b["status"] == "pendiente"]

    apostado = sum(b["stake"] for b in resueltas)
    devuelto = sum(b["payout"] for b in resueltas)
    neto = devuelto - apostado
    ganadas = sum(1 for b in resueltas if b["status"] == "ganada")

    # Racha actual (positiva = seguidas ganadas, negativa = seguidas perdidas).
    racha = 0
    for b in reversed(resueltas):
        if b["status"] == "ganada":
            if racha < 0:
                break
            racha += 1
        else:
            if racha > 0:
                break
            racha -= 1

    # Calibración: ¿las que el motor dijo 60% ganaron ~60% de las veces?
    con_prob = [b for b in resueltas if b["probability"]]
    esperadas = sum(b["probability"] for b in con_prob)
    calibracion = None
    if len(con_prob) >= 5:
        reales = sum(1 for b in con_prob if b["status"] == "ganada")
        calibracion = {
            "apuestas_evaluadas": len(con_prob),
            "aciertos_esperados": round(esperadas, 1),
            "aciertos_reales": reales,
            "veredicto": (
                "El motor va calibrado ✅" if abs(reales - esperadas) <= max(1.5, 0.15 * len(con_prob))
                else ("El motor va optimista ⚠️" if reales < esperadas else "El motor va conservador")
            ),
        }

    return {
        "bankroll_inicial": bankroll_inicial,
        "bankroll_actual": round(bankroll_inicial + neto - sum(b["stake"] for b in pendientes), 2),
        "total_apuestas": len(rows),
        "pendientes": len(pendientes),
        "resueltas": len(resueltas),
        "ganadas": ganadas,
        "perdidas": len(resueltas) - ganadas,
        "acierto_pct": round(100.0 * ganadas / len(resueltas), 1) if resueltas else 0.0,
        "total_apostado": round(apostado, 2),
        "neto": round(neto, 2),
        "roi_pct": round(100.0 * neto / apostado, 1) if apostado else 0.0,
        "racha": racha,
        "en_juego": round(sum(b["stake"] for b in pendientes), 2),
        "calibracion": calibracion,
    }


def staked_today() -> float:
    """Cuánto llevas apostado hoy (para respetar el límite diario)."""
    hoy = datetime.now(timezone.utc).date().isoformat()
    with _lock, _connect() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(stake), 0) AS s FROM bets WHERE substr(created_at, 1, 10) = ?",
            (hoy,),
        ).fetchone()
        return float(row["s"])
