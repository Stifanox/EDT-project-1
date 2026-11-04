"""Globalna konfiguracja aplikacji (ścieżki, stałe, nazwy modeli).

Plik współdzielony – zmiany zgłaszaj w PROGRESS.md -> „Dziennik decyzji”.
Wartości można nadpisać zmiennymi środowiskowymi (przydatne w testach).

WAŻNE: ścieżki czytaj z modułu w chwili użycia (`config.DB_PATH`), a nie przez
`from opimon.config import DB_PATH` ani w domyślnych argumentach funkcji – testy
podmieniają je na katalog tymczasowy.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("OPIMON_DATA_DIR", ROOT_DIR / "data"))

SAMPLE_DIR = ROOT_DIR / "data" / "sample"   # przykładowe dane (w repo)
DB_PATH = DATA_DIR / "opimon.db"            # baza opinii i predykcji (poza repo, D2)
MODELS_DIR = DATA_DIR / "models"            # wytrenowane modele (poza repo, M3/M4)
DATASETS_DIR = DATA_DIR / "datasets"        # pobrane zbiory treningowe, np. IMDB (poza repo, M1)
CACHE_DIR = DATA_DIR / "cache"              # cache HTTP / pośrednie wyniki (poza repo)

# Gdy baza jest pusta przy starcie, wczytaj opinie z przykładowego źródła offline.
LOAD_SAMPLES_IF_EMPTY = os.environ.get("OPIMON_LOAD_SAMPLES", "1") == "1"

# --- pobieranie danych (O1) ---
DEFAULT_FETCH_LIMIT = 100
HTTP_TIMEOUT_S = 15.0
HTTP_USER_AGENT = "opimon-student-project/0.1 (educational; sentiment monitoring)"
REQUEST_DELAY_S = 1.0          # minimalny odstęp między zapytaniami do jednego serwisu

# --- sentyment (O2) ---
POSITIVE_THRESHOLD = 0.5       # score >= próg -> POSITIVE
TRANSFORMER_MODEL_NAME = os.environ.get(
    "OPIMON_TRANSFORMER", "distilbert-base-uncased-finetuned-sst-2-english"
)

# --- analiza i alerty (O3) ---
ALERT_WINDOW_DAYS = 7          # okno bieżące
ALERT_BASELINE_DAYS = 30       # okno odniesienia (poprzedzające okno bieżące)
ALERT_DROP_PP = 15.0           # spadek udziału pozytywnych o tyle punktów procentowych -> alert
ALERT_MIN_REVIEWS = 10         # minimalna liczba opinii w oknie, żeby liczyć alert
