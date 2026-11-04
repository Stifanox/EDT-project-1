# AGENTS.md – zasady dla agentów AI (i ludzi)

Projekt realizują 3 osoby (O1, O2, O3) równolegle; każda może pracować z własnym agentem AI.
Ten plik opisuje, jak pracować, żeby nie blokować innych i nie psuć ich kodu.

## 1. Procedura startowa (zawsze, przed pierwszą zmianą)

1. Przeczytaj [`PROGRESS.md`](PROGRESS.md): aktualne statusy etapów, prośby i dziennik decyzji.
2. Ustal, **którą osobą jest użytkownik** (O1/O2/O3):
   - nazwa brancha `dev/o1`, `dev/o2`, `dev/o3` (`git branch --show-current`), albo
   - tabela *Zespół* w `README.md`, albo
   - jeśli nadal nie wiadomo, **zapytaj**.
3. Ustal etap: ten, który wskazał użytkownik, albo pierwszy etap tej osoby o statusie
   `TODO`, którego zależności twarde (`!`) są `DONE`.
4. Przeczytaj opis etapu `docs/tasks/<ID>.md` oraz [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
5. Sprawdź w *Prośbach do innych osób*, czy ktoś czegoś od tej osoby nie potrzebuje.
6. W `PROGRESS.md` zmień status etapu na `🟦 IN_PROGRESS` (tylko swój wiersz).

## 2. Własność plików (najważniejsza zasada)

| Właściciel | Pliki |
|------------|-------|
| **O1** | `opimon/sources/**`, `opimon/storage/**`, `opimon/cli.py`, `opimon/ui/sources_view.py`, `pages/1_Zrodla_danych.py`, `app.py`; w `opimon/services.py`: fabryki `_make_repository()`, `_make_sources()` i metody `fetch_reviews`, `refresh_all`, `load_samples_if_empty` (+ nowe metody dotyczące danych); `tests/test_source*.py`, `tests/test_storage*.py`, `tests/test_cli.py`, `tests/test_sources_view.py`, `tests/fixtures/{steam,imdb_html,…}/**`; listy `SOURCE_CASES`, `REPOSITORY_FACTORIES`; `scripts/make_sample_data.py`, `data/sample/**` |
| **O2** | `opimon/sentiment/**`, `opimon/ui/models_view.py`, `opimon/ui/evaluation_view.py`, `pages/2_Modele.py`, `pages/3_Ewaluacja.py`; w `opimon/services.py`: fabryki `_make_models()`, `_make_training_data()` i metody `model_infos`, `train_model`, `predict_text`, `evaluate_model` (+ nowe metody dotyczące modeli); `tests/test_*model*.py`, `tests/test_imdb.py`, `tests/test_evaluation*.py`, `tests/fixtures/imdb_mini.csv`; listy `MODEL_FACTORIES`, `PROVIDER_FACTORIES`; `scripts/download_imdb.py` |
| **O3** | `opimon/analytics/**`, `opimon/ui/charts.py`, `opimon/ui/dashboard_view.py`, `opimon/ui/reviews_view.py`, `pages/4_Dashboard.py`, `pages/5_Opinie.py`; w `opimon/services.py`: fabryka `_make_analytics()`; `tests/test_analytics*.py`, `tests/test_terms.py`, `tests/test_alerts.py`, `tests/test_filters.py`, `tests/test_report.py`, `tests/test_dashboard_view.py`, `tests/test_reviews_view.py`; lista `ANALYTICS_FACTORIES` |
| **Wspólne (kontrakty)** | `opimon/models.py`, `opimon/interfaces.py`, `opimon/errors.py`, `opimon/config.py`, `opimon/textproc.py`, `opimon/ui/nav.py`, `opimon/ui/components.py`, `opimon/ui/state.py`, pozostała część `opimon/services.py` (`AppServices.__init__`, `analyze_pending`, `scored_reviews`, `ready_models`, `build_services`), `tests/conftest.py`, `tests/test_ui_smoke.py`, `tests/test_services.py`, `PROGRESS.md` (każdy tylko swoją sekcję), `requirements.txt` (każdy tylko swoją sekcję) |

- **Edytuj tylko pliki osoby, dla której pracujesz.** Potrzebujesz zmiany w cudzym pliku?
  Zapisz ją w `PROGRESS.md` → *Prośby do innych osób* i zastosuj obejście u siebie (np. lokalną
  funkcję pomocniczą).
- **Pliki wspólne:** wolno wprowadzać wyłącznie zmiany **wstecznie zgodne** (nowe pole z wartością
  domyślną, nowa funkcja, nowy opcjonalny parametr, nowa stała w config). Każdą taką zmianę opisz
  w `PROGRESS.md` → *Dziennik decyzji*. Zmiana niezgodna (zmiana nazwy, usunięcie, zmiana typu
  lub semantyki) wymaga zgody całego zespołu: zapytaj użytkownika i nie rób jej samodzielnie.
- Testy wspólne (`test_ui_smoke.py`, `test_services.py`) mogą się zepsuć, gdy podmienisz zaślepkę
  (np. inne liczby). Poprawka takiego testu jest dozwolona, jeśli zachowuje jego intencję;
  opisz ją w notatkach etapu.
- Nie formatuj ani nie refaktoryzuj cudzych plików „przy okazji”.

## 3. Zasady architektury

- GUI (`pages/`, `opimon/ui/`) **tylko prezentuje**. Logika (pobieranie, modele, metryki,
  agregacje, alerty) jest w `opimon/sources`, `opimon/sentiment`, `opimon/analytics` i jest
  testowalna bez Streamlit.
- GUI pobiera wszystko przez `get_services()` → `AppServices`. Nie tworzy źródeł, modeli ani
  repozytoriów samodzielnie.
- Nowa implementacja = klasa spełniająca Protocol z `opimon/interfaces.py` + podmiana w **swojej**
  fabryce w `opimon/services.py` + dopisanie do listy w teście kontraktowym (`tests/contracts/`).
- Ciężkie biblioteki (`torch`, `transformers`, `sklearn`) importuj **leniwie** (w metodzie lub
  w fabryce), żeby reszta aplikacji i testów działała bez nich.
- Tekst z Internetu i tekst treningowy czyść **tą samą** funkcją `textproc.clean_text`.
- `score` zawsze oznacza P(pozytywny) ∈ [0, 1]. Daty zawsze w UTC (aware).
- Etykieta ze źródła (`Review.label`) to nie predykcja. Służy do ewaluacji (M5) i porównań (A1/A3).
- Ścieżki (`config.DB_PATH`, `MODELS_DIR`, `DATASETS_DIR`, `CACHE_DIR`) czytaj z `config`
  **w chwili użycia**, nigdy w domyślnych argumentach funkcji ani przez `from config import X`.
- Przejścia między widokami tylko przez `opimon.ui.nav` (`open_reviews`, `open_dashboard`).
- Źródła sieciowe: `config.HTTP_USER_AGENT`, `config.HTTP_TIMEOUT_S`, `config.REQUEST_DELAY_S`;
  wszystkie błędy zamieniane na `SourceError` z komunikatem po polsku.

## 4. Konwencje

- Python ≥ 3.11, type hints, `from __future__ import annotations`.
- Identyfikatory, nazwy w kodzie i **wiadomości commitów po angielsku**; teksty w GUI, docstringi
  i dokumentacja **po polsku**.
- Długość linii 100 (`ruff check .` musi być czyste).
- Bez nowych zależności „na zapas”. Nową zależność dopisz do `requirements.txt` w sekcji swojego
  modułu i zgłoś w *Dzienniku decyzji*.
- Dane runtime (`data/opimon.db`, `data/models/`, `data/datasets/`, `data/cache/`) nie trafiają
  do repo. Duże zbiory (IMDB) i wagi modeli pobiera się skryptem / instrukcją z README.

## 5. Testy

- `pytest -m "not slow and not network"` musi przechodzić **przed każdym merge do `main`**.
- Każda implementacja interfejsu musi przejść test kontraktowy w `tests/contracts/`.
- `@pytest.mark.slow`: ciężkie modele / pełny IMDB. `@pytest.mark.network`: prawdziwe zapytania
  do Internetu. Pozostałe testy działają **offline** (źródła testuj na nagranych odpowiedziach
  w `tests/fixtures/`).
- Fixture'y: `tiny_reviews`, `tiny_targets`, `tiny_training`, `make_review(...)` w `tests/conftest.py`.
- Każdy test dostaje automatycznie tymczasowy katalog danych (fixture `isolated_data_dir`).
- Testy GUI (`streamlit.testing.v1.AppTest`), wzór w `tests/test_ui_smoke.py`:
  - start od `app.py` + `at.switch_page("pages/…")` (inaczej `st.switch_page` nie znajdzie stron);
  - `get_services.clear()` przed testem (świeże `AppServices`);
  - elementy wybieraj **po kluczu** (`at.button(key="…")`), nie po indeksie; każdy widżet ma `key`
    z prefiksem widoku (`src_`, `mdl_`, `ev_`, `dash_`, `rev_`);
  - zaznaczenie w `st.dataframe`: `at.session_state[key] = {"selection": {"rows": [...], "columns": [], "cells": []}}`;
  - `st.dialog` trzymaj na stanie w `session_state` (plus `on_dismiss`), a nie na samym kliknięciu;
  - upload plików nie jest wspierany przez `AppTest`, więc logikę importu testuj osobno.
- Komunikaty przed `st.rerun()` przekazuj przez `components.flash(...)`.
- Liczby w tabelach jako liczby (formatowanie przez `column_config`), nie sformatowane stringi.

## 6. Zakończenie etapu (Definition of Done)

1. Wszystkie kryteria akceptacji w `docs/tasks/<ID>.md` odhaczone (`- [x]`). Jeśli któregoś
   świadomie nie zrobiono, opisz to w sekcji *Notatki z realizacji* tego pliku.
2. `pytest -m "not slow and not network"` przechodzi, `ruff check .` czyste,
   `streamlit run app.py` startuje bez błędów.
3. W `PROGRESS.md`: status `✅ DONE`, postęp `n/n`, data w *Uwagach*, podsumowanie osoby;
   jeśli zmieniono kontrakt, dodaj wpis w dzienniku. Spójność sprawdza `tests/test_progress_consistency.py`.
   Aktualizuj *Postęp* także w trakcie pracy, po każdym odhaczonym kryterium.
4. *Notatki z realizacji* w pliku etapu: decyzje, odstępstwa, ograniczenia, wyniki pomiarów.
5. Commit **po angielsku** z prefiksem etapu, np. `[D1] Add Steam reviews source with cursor pagination`.
6. Merge do `main` według [`CONTRIBUTING.md`](CONTRIBUTING.md).

Etap zablokowany: status `⛔ BLOCKED` + w kolumnie *Uwagi* napisz, przez co (ID etapu lub osoba).

## 7. Format statusów w PROGRESS.md

`⬜ TODO` · `🟦 IN_PROGRESS` · `✅ DONE` · `⛔ BLOCKED` · `🔁 REWORK`
Kolumna *Postęp* = `odhaczone/wszystkie` kryteria akceptacji z pliku etapu.
Zależności: `!ID` = twarda (bez niej nie da się zacząć), `~ID` = miękka (można zacząć na zaślepce).
