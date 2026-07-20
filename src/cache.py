"""Caché en memoria con expiración.

La API gratuita da 500 consultas al mes. Sin caché, cada vez que abres el panel y
picas entre pestañas quemas consultas de a gratis. Las cuotas no cambian cada
segundo, así que guardarlas ~10 minutos no te quita nada y estira la cuota mucho.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self.ttl = ttl_seconds
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires, value = item
            if time.time() >= expires:
                del self._data[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time() + self.ttl, value)

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        """Devuelve lo cacheado o llama a producer() y lo guarda."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        # No cacheamos respuestas vacías: probablemente algo falló.
        if value:
            self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entradas": len(self._data),
                "aciertos": self.hits,
                "fallos": self.misses,
                "ahorro_pct": round(100.0 * self.hits / total, 1) if total else 0.0,
                "ttl_segundos": self.ttl,
            }
