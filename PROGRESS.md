# PROGRESS – stan realizacji projektu

> Plik dla ludzi i agentów AI. Zasady aktualizacji: [`AGENTS.md`](AGENTS.md) §6–7.
> Każda osoba edytuje **tylko swoją sekcję**; do dziennika dopisujemy wiersze **na końcu**.

**Statusy:** `⬜ TODO` · `🟦 IN_PROGRESS` · `✅ DONE` · `⛔ BLOCKED` · `🔁 REWORK`
**Zależności:** `!ID` twarda · `~ID` miękka (można zacząć na zaślepce z P0)
**Postęp:** odhaczone / wszystkie kryteria akceptacji w `docs/tasks/<ID>.md`

## Podsumowanie

| Osoba | Zakres | Etapy ukończone |
|-------|--------|-----------------|
| O1 | Fundament, źródła danych (API + scraping), baza, monitorowanie | 3 / 6 (+1 opcjonalny) |
| O2 | Modele sentymentu, trening, ewaluacja | 0 / 7 |
| O3 | Analiza, dashboard, przeglądarka opinii, alerty | 0 / 5 (+1 opcjonalny) |
| Wszyscy | Integracja, raport | 0 / 2 |

**Kolejność:** P0 jest jedynym etapem blokującym. Po jego merge do `main` wszystkie trzy osoby
pracują równolegle. Kolejność wewnątrz sekcji jest zalecana.
**Priorytet prowadzącego:** dane do predykcji z Internetu (D1, D3) → sentyment (M1–M3) → GUI
(A2, A3). Szczegóły: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#mapa-zależności-między-etapami).

---

## P0 – Fundament (O1) · BLOKUJĄCY

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [P0](docs/tasks/P0.md) | Fundament: kontrakty, zaślepki, szkielet GUI, dane przykładowe, testy, dokumentacja | ✅ DONE | 12/12 | – | 2026-11-04 · po merge do `main` startują wszyscy |

## O1 – Dane: źródła, baza, monitorowanie (właściciel: O1)

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [D1](docs/tasks/D1.md) | Źródło Steam Reviews API | ✅ DONE | 7/7 | !P0 | 2026-11-04 · `IUserReviewsService/GetAppReviews` (stary `/appreviews` wyłączony przez Valve) |
| [D2](docs/tasks/D2.md) | Repozytorium SQLite | ✅ DONE | 7/7 | !P0 | 2026-11-04 · dane trwałe w `data/opimon.db` (WAL, gotowe pod CLI z D5) |
| [D3](docs/tasks/D3.md) | Źródło przez web scraping (recenzje filmów) | ⬜ TODO | 0/7 | !P0, ~D1 | kluczowe: web scraping |
| [D4](docs/tasks/D4.md) | Widok „Źródła danych” | ⬜ TODO | 0/6 | !P0, ~D1, ~D2 | |
| [D5](docs/tasks/D5.md) | Monitorowanie: odświeżanie przyrostowe i CLI | ⬜ TODO | 0/6 | !D2, ~D1 | |
| [D6](docs/tasks/D6.md) | (opcjonalnie) Filtr jakości opinii | ⬜ TODO | 0/4 | ~D1, ~D3 | |

## O2 – Modele sentymentu (właściciel: O2)

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [M1](docs/tasks/M1.md) | Zbiór treningowy IMDB | ⬜ TODO | 0/6 | !P0 | |
| [M2](docs/tasks/M2.md) | Model słownikowy VADER | ⬜ TODO | 0/5 | !P0 | |
| [M3](docs/tasks/M3.md) | TF-IDF + regresja logistyczna | ⬜ TODO | 0/7 | !M1 | domyślny model |
| [M4](docs/tasks/M4.md) | Model transformerowy (DistilBERT SST-2) | ⬜ TODO | 0/5 | !P0 | testy `slow` |
| [M5](docs/tasks/M5.md) | Ewaluacja i porównanie modeli (ta sama vs inna domena) | ⬜ TODO | 0/6 | !M1, ~M2, ~M3, ~M4, ~D1 | rdzeń merytoryczny |
| [M6](docs/tasks/M6.md) | Widok „Modele” | ⬜ TODO | 0/5 | !P0, ~M3 | |
| [M7](docs/tasks/M7.md) | Widok „Ewaluacja i porównanie modeli” | ⬜ TODO | 0/5 | ~M5 | |

## O3 – Analiza i monitoring (właściciel: O3)

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [A1](docs/tasks/A1.md) | Statystyki i trend sentymentu | ⬜ TODO | 0/6 | !P0 | |
| [A2](docs/tasks/A2.md) | Widok „Dashboard” | ⬜ TODO | 0/6 | !P0, ~A1 | główny ekran demo |
| [A3](docs/tasks/A3.md) | Widok „Opinie” – przeglądarka | ⬜ TODO | 0/6 | !P0 | |
| [A4](docs/tasks/A4.md) | Słowa kluczowe: co chwalą, a co krytykują | ⬜ TODO | 0/5 | !P0 | |
| [A5](docs/tasks/A5.md) | Alerty o spadku sentymentu | ⬜ TODO | 0/5 | !A1 | |
| [A6](docs/tasks/A6.md) | (opcjonalnie) Eksport i raport | ⬜ TODO | 0/4 | ~A1, ~A4, ~A5 | |

## Wspólne – na koniec

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [X1](docs/tasks/X1.md) | Integracja end-to-end i scenariusz demo | ⬜ TODO | 0/6 | !D1, !D2, !M3, !A2, ~pozostałe | prowadzi O1 |
| [X2](docs/tasks/X2.md) | Raport i prezentacja | ⬜ TODO | 0/5 | ~X1 | |

---

## Prośby do innych osób

| Data | Od | Do | Prośba | Status |
|------|----|----|--------|--------|
| – | – | – | – | – |

## Dziennik decyzji i zmian kontraktów

| Data | Kto | Decyzja |
|------|-----|---------|
| 2026-11-04 | O1 | Stack: Python ≥ 3.11, Streamlit (`pages/`), pandas; pakiet `opimon`. Podział pionowy na 3 osoby, branch per osoba, merge po etapie. |
| 2026-11-04 | O1 | Dane anglojęzyczne. Trening: IMDB 50k (M1). Predykcja: Steam Reviews API (D1) + scraping recenzji filmów (D3). Spójność: anglojęzyczne recenzje rozrywki z oceną binarną; D3 jest w tej samej domenie co IMDB. |
| 2026-11-04 | O1 | Sentyment binarny; `Prediction.score` = P(pozytywny) ∈ [0, 1], próg `config.POSITIVE_THRESHOLD`. Predykcje przechowywane per (opinia, model). |
| 2026-11-04 | O1 | Etykieta ze źródła (`Review.label`: Steam `voted_up`, ocena IMDb ≥ 7 / ≤ 4) oddzielona od predykcji; służy do ewaluacji na danych z Internetu (M5). |
| 2026-11-04 | O1 | Domyślny model = pierwszy gotowy w `_make_models()` (kolejność ustala O2). Nowo pobrane opinie są analizowane nim automatycznie. |
| 2026-11-04 | O1 | Kontrakty P0 zamrożone: `models.py`, `interfaces.py`, `errors.py`, `ui/nav.py` – tylko zmiany wstecznie zgodne z wpisem tutaj. |
| 2026-11-04 | O1 | [D1] Nowa zależność `requests>=2.32` (sekcja O1). Wspólny klient `opimon/sources/http.py` (bez przekierowań, błędy -> `SourceError`). `steam` pierwszym źródłem w `_make_sources()`, `sample` zostaje jako offline. |
| 2026-11-04 | O1 | [D1] `tests/fixtures/` jest pakietem (transporty offline, np. `tests.fixtures.steam.fake`). Test wspólny `test_ui_smoke.py::test_fetch_flow_on_sources_page` wybiera jawnie źródło `sample` (bez sieci). |
| 2026-11-04 | O1 | [D1] Steam: `store.steampowered.com/appreviews` wyłączony przez Valve 22.10.2026, więc źródło używa `api.steampowered.com/IUserReviewsService/GetAppReviews/v1` (bez klucza). Recenzje „off-topic” (review bomb) są pobierane (`filter_offtopic_activity=false`). |
| 2026-11-04 | O1 | [D2] `_make_repository()` zwraca `SqliteReviewRepository(config.DB_PATH)`: dane w `data/opimon.db` (WAL), przetrwają restart. Bez kluczy obcych (zachowanie jak w zaślepce); schemat wersjonowany `PRAGMA user_version`. Reset danych = usunięcie pliku. |
