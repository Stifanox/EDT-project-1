"""Atomowy cache JSON z synchronizacją odczytów i zapisów w procesie."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

_CACHE_LOCK = RLock()


def read_json(path: Path) -> Any:
    with _CACHE_LOCK, path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, payload: Any) -> None:
    """Zamknij czytniki przed podmianą; obsłuż blokadę istniejącego cache na Windows."""
    with _CACHE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            try:
                os.replace(temporary, path)
            except PermissionError:
                # Inny proces może czytać ten sam niezmienny klucz cache. Jego gotowy
                # plik pozostaje poprawny, a bieżący klient ma właśnie obliczone dane.
                if not path.is_file():
                    raise
        finally:
            Path(temporary).unlink(missing_ok=True)
