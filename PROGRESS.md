# PROGRESS – stan realizacji projektu

> Plik dla ludzi i agentów AI. Zasady aktualizacji: [`AGENTS.md`](AGENTS.md) §6–7.
> Każda osoba edytuje **tylko swoją sekcję**; do dziennika dopisujemy wiersze **na końcu**.

**Statusy:** `⬜ TODO` · `🟦 IN_PROGRESS` · `✅ DONE` · `⛔ BLOCKED` · `🔁 REWORK`
**Zależności:** `!ID` twarda · `~ID` miękka (można zacząć na zaślepce z P0)
**Postęp:** odhaczone / wszystkie kryteria akceptacji w `docs/tasks/<ID>.md`

## Podsumowanie

| Osoba | Zakres | Etapy ukończone |
|-------|--------|-----------------|
| O1 | Fundament, źródła danych (API + scraping), baza, monitorowanie | 1 / 6 (+1 opcjonalny) |
| O2 | Modele sentymentu, trening, ewaluacja | 7 / 7 |
| O3 | Analiza, dashboard, przeglądarka opinii, alerty | 5 / 5 (+ A6) |
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
| [D1](docs/tasks/D1.md) | Źródło Steam Reviews API | ⬜ TODO | 0/7 | !P0 | kluczowe: dane z Internetu (API) |
| [D2](docs/tasks/D2.md) | Repozytorium SQLite | ⬜ TODO | 0/7 | !P0 | |
| [D3](docs/tasks/D3.md) | Źródło przez web scraping (recenzje filmów) | ⬜ TODO | 0/7 | !P0, ~D1 | kluczowe: web scraping |
| [D4](docs/tasks/D4.md) | Widok „Źródła danych” | ⬜ TODO | 0/6 | !P0, ~D1, ~D2 | |
| [D5](docs/tasks/D5.md) | Monitorowanie: odświeżanie przyrostowe i CLI | ⬜ TODO | 0/6 | !D2, ~D1 | |
| [D6](docs/tasks/D6.md) | (opcjonalnie) Filtr jakości opinii | ⬜ TODO | 0/4 | ~D1, ~D3 | |

## O2 – Modele sentymentu (właściciel: O2)

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [M1](docs/tasks/M1.md) | Zbiór treningowy IMDB | ✅ DONE | 6/6 | !P0 | 2026-11-08 · CSV/HF, cache 0,43 s, synchronizacja Windows i testy |
| [M2](docs/tasks/M2.md) | Model słownikowy VADER | ✅ DONE | 5/5 | !P0 | 2026-11-08 · kontrakt, IMDB i Steam live (199); wyniki w M2 |
| [M3](docs/tasks/M3.md) | TF-IDF + regresja logistyczna | ✅ DONE | 7/7 | !M1 | 2026-11-08 · IMDB accuracy 90,53%, trening 11,58 s; wariant NB |
| [M4](docs/tasks/M4.md) | Model transformerowy (DistilBERT SST-2) | ✅ DONE | 5/5 | !P0 | 2026-11-08 · kontrakt slow OK; IMDB n=1000 i Steam live n=199 |
| [M5](docs/tasks/M5.md) | Ewaluacja i porównanie modeli (ta sama vs inna domena) | ✅ DONE | 6/6 | !M1, ~M2, ~M3, ~M4, ~D1 | 2026-11-08 · wspólna próba IMDB/Steam, cache, błędy i wnioski |
| [M6](docs/tasks/M6.md) | Widok „Modele” | ✅ DONE | 5/5 | !P0, ~M3 | 2026-11-08 · trening, wyjaśnienia, przykłady, analiza i AppTest |
| [M7](docs/tasks/M7.md) | Widok „Ewaluacja i porównanie modeli” | ✅ DONE | 5/5 | ~M5 | 2026-11-08 · porównanie, macierz, wykresy, błędy i AppTest |

### Podsumowanie O2 — Karol, 2026-11-08

- M1–M7 ukończone: IMDB, VADER, trwały TF-IDF + LR, opcjonalny DistilBERT CPU,
  cache ewaluacji i porównań, kompletne widoki Modele/Ewaluacja z testami GUI.
- Pełny IMDB: trening TF-IDF 11,58 s, accuracy 90,53% na 24 532 recenzjach testowych.
  Uczciwe porównanie trzech modeli na wspólnych próbkach i ograniczenia w M5.
- Weryfikacja końcowa: 133 testy zaliczone, 3 pominięte (brak treningu dla modeli
  niewymagających treningu), w tym rzeczywisty kontrakt DistilBERT; Ruff czysty,
  Streamlit HTTP 200. Dane, wagi oraz cache pozostają poza repo.
- Po ujawnieniu wyścigu cache na Windows dodano synchronizację odczytu/zapisu oraz
  obsługę blokady przez drugi proces; 20 niezależnych uruchomień testów współbieżności
  (40 testów) bez błędu, następnie cały zestaw ponownie zaliczony.
- Kod O1/O3 i zamrożone interfejsy nie były zmieniane. Integracja X1 i końcowy raport
  zespołowy X2 wymagają wkładu pozostałych osób; materiał O2 i prośby są zapisane poniżej.

## O3 – Analiza i monitoring (właściciel: O3)

| ID | Etap | Status | Postęp | Zależności | Uwagi |
|----|------|--------|--------|------------|-------|
| [A1](docs/tasks/A1.md) | Statystyki i trend sentymentu | ✅ DONE | 6/6 | !P0 | 2026-11-14 · trend z wygładzaniem, Wilson, `filter_period`, `label_agreement` |
| [A2](docs/tasks/A2.md) | Widok „Dashboard” | ✅ DONE | 6/6 | !P0, ~A1 | 2026-11-14 · główny ekran demo: KPI z CI i deltą, trend D/W, porównanie, przejścia |
| [A3](docs/tasks/A3.md) | Widok „Opinie” – przeglądarka | ✅ DONE | 6/6 | !P0 | 2026-11-14 · filtry (daty, score, „model się myli”), szczegóły z predykcjami wszystkich modeli, `review_id`, paginacja |
| [A4](docs/tasks/A4.md) | Słowa kluczowe: co chwalą, a co krytykują | ✅ DONE | 5/5 | !P0 | 2026-11-14 · log-odds z priorem, bigramy, `emerging_terms` (patch, update), klikalne wykresy |
| [A5](docs/tasks/A5.md) | Alerty o spadku sentymentu | ✅ DONE | 5/5 | !A1 | 2026-11-14 · spadek udziału + skok wolumenu; Starfall na demo; przejścia z dashboardu |
| [A6](docs/tasks/A6.md) | (opcjonalnie) Eksport i raport | ✅ DONE | 4/4 | ~A1, ~A4, ~A5 | 2026-11-14 · CSV + raport HTML z dashboardu i Opinii |

### Podsumowanie O3 — 2026-11-14

- A1 ukończony: `SentimentAnalytics` zastępuje zaślepkę w `_make_analytics()`; trend z pustymi
  okresami i wygładzonym udziałem, przedziały Wilsona w porównaniu obiektów, pomocniki
  `filter_period`, `label_agreement`, `wilson_interval`.
- A2–A6 ukończone na `dev/o3`: dashboard (KPI, trend, porównanie, słowa, alerty, eksport),
  przeglądarka Opinii (filtry, `review_id` z prośby O2/M7, szczegóły, paginacja, CSV),
  log-odds + `emerging_terms`, alerty spadku/wolumenu, raport HTML.
- Weryfikacja: 213 testów zaliczonych, 2 pominięte; Ruff czysty. Bez merge do `main` –
  na koniec PR z `dev/o3`.

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
| 2026-11-08 | O2 | O1 | D1: stary `/appreviews/<appid>?json=1` przekierowuje do strony głównej. Aktualne API: `https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/`, parametry w `input_json`, enumy liczbowe, `languages` jako lista; klucz opcjonalny. Dokumentacja: https://partner.steamgames.com/doc/webapi/IUserReviewsService . Proszę uwzględnić migrację w D1 i README. | OTWARTE |
| 2026-11-08 | O2 | O3 | M7 korzysta z `nav.open_reviews(review_id=...)`; proszę w A3 odczytać `review_id` i wyświetlić szczegóły wskazanej opinii (zaślepka go ignoruje). Tymczasowo M7 przekazuje też cel i pełną frazę. Wyjaśnienia dostępne przez `AppServices.explain_text(text, model_name)`. | ZROBIONE (A3, 2026-11-14) |
| 2026-11-08 | O2 | O1 / wszyscy | M1–M7 gotowe. Materiał O2 do X2: tabele i ograniczenia w `docs/tasks/M1.md`–`M5.md`, odtwarzalny benchmark `python -m opimon.sentiment.benchmark --help`. X1 czeka na D1/D2/A2; po D3 proszę powtórzyć porównanie IMDb live (API fasady obsługuje etykiety dowolnego źródła). | DO INTEGRACJI |

## Dziennik decyzji i zmian kontraktów

| Data | Kto | Decyzja |
|------|-----|---------|
| 2026-11-04 | O1 | Stack: Python ≥ 3.11, Streamlit (`pages/`), pandas; pakiet `opimon`. Podział pionowy na 3 osoby, branch per osoba, merge po etapie. |
| 2026-11-04 | O1 | Dane anglojęzyczne. Trening: IMDB 50k (M1). Predykcja: Steam Reviews API (D1) + scraping recenzji filmów (D3). Spójność: anglojęzyczne recenzje rozrywki z oceną binarną; D3 jest w tej samej domenie co IMDB. |
| 2026-11-04 | O1 | Sentyment binarny; `Prediction.score` = P(pozytywny) ∈ [0, 1], próg `config.POSITIVE_THRESHOLD`. Predykcje przechowywane per (opinia, model). |
| 2026-11-04 | O1 | Etykieta ze źródła (`Review.label`: Steam `voted_up`, ocena IMDb ≥ 7 / ≤ 4) oddzielona od predykcji; służy do ewaluacji na danych z Internetu (M5). |
| 2026-11-04 | O1 | Domyślny model = pierwszy gotowy w `_make_models()` (kolejność ustala O2). Nowo pobrane opinie są analizowane nim automatycznie. |
| 2026-11-04 | O1 | Kontrakty P0 zamrożone: `models.py`, `interfaces.py`, `errors.py`, `ui/nav.py` – tylko zmiany wstecznie zgodne z wpisem tutaj. |
| 2026-11-08 | O2 | M1: IMDB jest pierwszym providerem; próbka offline pozostaje jawnie dostępna jako `sample_movies`. Testy P0 wybierają ją jawnie, zachowując intencję testowania bez sieci i pełnego zbioru. Eksport Hugging Face zachowuje oficjalny podział, usuwa duplikaty/konflikty po czyszczeniu i równoważy klasy osobno w obu częściach. |
| 2026-11-08 | O2 | M2: dodano zależność `vaderSentiment` w sekcji O2; VADER jest pierwszym gotowym modelem do M3. Test fasady sprawdza nowy model domyślny zamiast nazwy zaślepki. Score VADER to liniowo przeskalowany compound, bez kalibracji probabilistycznej. |
| 2026-11-08 | O2 | M3: zależności `scikit-learn`, `joblib` w sekcji O2. `_make_models()` rejestruje TF-IDF jako pierwszy, VADER jako gotowy fallback przed treningiem; zaślepki pozostają w awaryjnej fabryce P0 i testach kontraktowych. Wspólne testy fasady sprawdzają prawdziwy model zamiast zaślepki, z tą samą intencją treningu, ponownej analizy i odporności. |
| 2026-11-08 | O2 | M4: zależności `transformers>=4.44,<5` i `torch>=2.3` w sekcji O2. Nowa opcjonalna metoda O2 `AppServices.load_model(name, allow_download=False)` udostępnia jawne pobranie wag; zwykły start i odświeżenia GUI nie używają sieci. Transformer jest trzeci w fabryce, CPU i limit 512 tokenów. |
| 2026-11-08 | O2 | M5: nowe metody O2 `compare_models`, `evaluation_sources`, `evaluation_details`, `explain_text`; `evaluate_model` zachowuje dotychczasowe argumenty i wynik, dodaje opcjonalne `source_name` i `force`. Cache JSON identyfikuje dane, etykiety, model, biblioteki i próg. Źródło `sample` w porównaniach ma nazwę `demo:sample`, aby nie udawać danych z Internetu. Narzędzie pomiarowe `python -m opimon.sentiment.benchmark` zapisuje wyniki poza repo. |
| 2026-11-08 | O2 | M7 wymaga Plotly do macierzy pomyłek i wykresu accuracy/F1; dodano `plotly>=5.20` w sekcji O2 wymagań. Sekcja O3 pozostaje bez zmian; docelowo zależność wspólna dla wykresów obu osób. |
| 2026-11-08 | O2 | Końcowe powtórzenie testów ujawniło sporadyczny wyścig cache Windows; poprzedni commit został błędnie scalony i opublikowany mimo niepowodzenia testu. Poprawka w modułach O2 synchronizuje odczyt/zapis JSON i obsługuje blokadę istniejącego cache przez inny proces. Przed publikacją poprawki zaliczono 20 niezależnych powtórzeń testów współbieżności, pełne 133 testy oraz Ruff i start Streamlit. |
| 2026-11-14 | O3 | A1: test kontraktowy `OpinionAnalytics` sprawdzał dokładną listę kolumn `trend`/`compare_targets`, co przeczyło zapisowi „dodatkowe kolumny są dozwolone” (A1). Teraz wymaga, by kolumny kontraktowe były pierwsze i w tej samej kolejności; `SentimentAnalytics` dodaje `positive_share_smoothed` oraz `ci_low`/`ci_high`. `trend` ma nowy opcjonalny argument `window`. Interfejsy i modele bez zmian. |
| 2026-11-14 | O3 | A3: `nav.open_reviews` i `ReviewFilters` dostały opcjonalne `date_from` / `date_to` (`datetime.date`, UTC, włącznie) – zmiana wstecznie zgodna; dotychczasowe wywołania (M7, dashboard) działają bez zmian. Widok „Opinie” zeruje pozostałe filtry przy przejściu i pokazuje opinię `review_id` nawet poza filtrami. |
