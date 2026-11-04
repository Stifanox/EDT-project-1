# Architektura

## Przepływ danych

```
 Internet                         opimon                                   GUI (Streamlit)
┌──────────────┐   fetch()   ┌──────────────────┐  add_reviews   ┌────────────────────┐
│ Steam API    │────────────▶│ ReviewSource     │───────────────▶│ ReviewRepository   │
│ (D1)         │             │ (O1)             │                │ (O1: SQLite, D2)   │
│ IMDb/…  HTML │────────────▶│ clean_text()     │                │ targets / reviews  │
│ (D3)         │             └──────────────────┘                │ / predictions      │
└──────────────┘                                                 └─────────┬──────────┘
                                                                           │
┌──────────────┐   load()    ┌──────────────────┐ train()        ┌─────────▼──────────┐
│ IMDB 50k     │────────────▶│ TrainingData     │───────────────▶│ SentimentModel     │
│ (Kaggle, M1) │             │ Provider (O2)    │                │ (O2: VADER, TF-IDF │
└──────────────┘             └──────────────────┘                │  + LR, DistilBERT) │
                                                                 └─────────┬──────────┘
                                         AppServices.analyze_pending()     │ predict_proba
                                         -> Prediction(review, model, score)
                                                                           │
                             ┌──────────────────┐ scored_reviews ┌─────────▼──────────┐
                             │ OpinionAnalytics │◀───────────────│ AppServices        │
                             │ (O3: trend,      │                │ (fasada, P0)       │
                             │  słowa, alerty)  │───────────────▶│                    │──▶ pages/*
                             └──────────────────┘                └────────────────────┘
```

1. **Pobieranie** (`AppServices.fetch_reviews`): źródło zwraca opinie nowsze niż ostatnia zapisana
   (`latest_review_time`), repozytorium zapisuje nowe (deduplikacja po `Review.id`), a domyślny model
   od razu je analizuje.
2. **Analiza** (`analyze_pending`): opinie bez predykcji danego modelu → `predict_proba` w paczkach
   → `Prediction` zapisane per (opinia, model). Przełączenie modelu w GUI nie wymaga przeliczania.
3. **Trening** (`train_model`): provider → `model.train` → usunięcie starych predykcji modelu →
   ponowna analiza wszystkich opinii.
4. **Ewaluacja** (`evaluate_model`): `test` = część testowa zbioru treningowego (ta sama domena),
   `live` = opinie z Internetu, które mają etykietę ze źródła (inna domena, prawdziwe dane).
5. **Prezentacja**: GUI bierze `scored_reviews(...)` i przekazuje je do `services.analytics`.

## Zaślepki z P0 i kto je zastępuje

| Interfejs | Zaślepka P0 | Docelowo | Etap | Właściciel | Fabryka |
|-----------|-------------|----------|------|------------|---------|
| `ReviewSource` | `SampleSource` – `data/sample/reviews.jsonl`, offline | `SteamReviewSource` (API), źródło scrapujące (IMDb/…) | D1, D3 | O1 | `_make_sources()` |
| `ReviewRepository` | `InMemoryReviewRepository` | `SqliteReviewRepository` | D2 | O1 | `_make_repository()` |
| `TrainingDataProvider` | `SampleTrainingData` – 240 recenzji filmowych | `ImdbTrainingData` (50k) | M1 | O2 | `_make_training_data()` |
| `SentimentModel` | `LexiconStubModel` (bez treningu), `WordCountModel` (trenowany, w pamięci) | `VaderModel`, `TfidfLogRegModel`, `TransformerModel` | M2–M4 | O2 | `_make_models()` |
| `OpinionAnalytics` | `BasicAnalytics` – zliczanie, bez wygładzania, bez alertów | pełna analityka | A1, A4, A5 | O3 | `_make_analytics()` |

`SampleSource` zostaje po integracji jako tryb offline (demo bez sieci, testy).

## Kontrakty (pliki zamrożone po P0)

| Plik | Zawartość |
|------|-----------|
| [`opimon/models.py`](../opimon/models.py) | `Target`, `Review`, `Prediction`, `Sentiment`, `LabeledText`, `Dataset`, `ModelInfo`, `EvalResult`, `ScoredReview`, `SentimentSummary`, `TermStat`, `Alert`, `FetchReport` |
| [`opimon/interfaces.py`](../opimon/interfaces.py) | Protocol-e z opisaną semantyką (sortowanie, filtry, błędy, przypadki brzegowe) |
| [`opimon/errors.py`](../opimon/errors.py) | `SourceError`, `ModelNotReadyError`, `DatasetUnavailableError` |
| [`opimon/ui/nav.py`](../opimon/ui/nav.py) | nazwy stron, `open_reviews(...)`, `open_dashboard(...)`, `MODEL_KEY` |
| [`opimon/textproc.py`](../opimon/textproc.py) | `clean_text`, `tokenize`, `content_tokens`, `STOPWORDS_EN` |

Najważniejsze ustalenia:
- `Review.id = "<source>:<external_id>"`, `Target.id = "<source>:<key>"`; daty UTC (aware).
- `Prediction.score` = P(pozytywny) ∈ [0, 1]; `Sentiment.from_score` z progiem 0.5.
- `Review.label` = etykieta ze źródła (Steam `voted_up`, ocena ≥ 7 / ≤ 4), **nie** predykcja.
- `predict_proba` zachowuje długość i kolejność; pusty tekst → 0.5; model nietrenowany → `ModelNotReadyError`.
- Źródła nie rzucają surowych wyjątków sieciowych, tylko `SourceError` z komunikatem po polsku.

## Fasada i odporność

`opimon/services.py`:
- każda osoba ma **swoje** fabryki; podmiana zaślepki to edycja jednej funkcji;
- wyjątek w fabryce → zaślepka P0 + wpis w `module_errors` (GUI pokazuje go w rozwijanym panelu);
- wyjątek modelu w `analyze_pending` → wpis `model:<nazwa>` w `module_errors`, reszta działa;
- błąd źródła w `fetch_reviews` → `FetchReport.errors`, bez wyjątku;
- domyślny model = pierwszy **gotowy** w `_make_models()`.

`AppServices` nie trzyma opinii w pamięci, każde odświeżenie GUI czyta repozytorium. Dzięki temu
zmiany z CLI (D5) w tej samej bazie SQLite są widoczne bez restartu i bez synchronizacji.

## Widoki

| Strona | Właściciel | Etap | Klucze widżetów |
|--------|------------|------|-----------------|
| `app.py` – start, KPI, linki | O1 | P0 | – |
| `pages/1_Zrodla_danych.py` | O1 | D4 | `src_*` |
| `pages/2_Modele.py` | O2 | M6 | `mdl_*` |
| `pages/3_Ewaluacja.py` | O2 | M7 | `ev_*` |
| `pages/4_Dashboard.py` | O3 | A2 (+A4, A5) | `dash_*` |
| `pages/5_Opinie.py` | O3 | A3 | `rev_*` |

Nawigacja: Dashboard → Opinie (`nav.open_reviews(target_id, sentiment, term, review_id)`),
Źródła → Dashboard (`nav.open_dashboard(target_id)`); wybór modelu jest wspólny (`nav.MODEL_KEY`).

## Dane przykładowe

`scripts/make_sample_data.py` → `data/sample/` (commitowane, test sprawdza zgodność z generatorem):
- `reviews.jsonl` – 195 opinii w stylu Steam dla 3 fikcyjnych gier, z datami względnymi
  (ostatnie 30 dni). „Starfall Odyssey” ma ok. 80% pozytywnych opinii, ale w ostatnich 7 dniach
  udział spada do ok. 30% po „patchu 2.0” (demo alertów i słów `patch` / `update`).
  Ok. 30% opinii jest „podchwytliwych” (negacja, sarkazm, „but”).
- `train_sample.csv` – 240 recenzji **filmowych**. Model trenowany na nich traci ok. 17 p.p. na
  grach, co jest materiałem do opisu zmiany domeny (M5).

## Mapa zależności między etapami

```
P0 ──┬── O1: D1 ──┐   D2 ── D5        D3   D4(~D1,~D2)   D6(opc.)
     │            │
     ├── O2: M1 ── M3 ──┐   M2   M4   M5(!M1, ~M2–M4, ~D1) ── M7    M6(~M3)
     │                  │
     └── O3: A1 ── A5   A2(~A1)   A3   A4   A6(opc.)
                        │
            X1 (!D1, !D2, !M3, !A2) ── X2
```

Twarde zależności (`!`) istnieją tylko wewnątrz sekcji jednej osoby (oraz w etapach wspólnych X).
Między osobami są wyłącznie zależności miękkie (`~`): każdy pracuje na zaślepkach innych, a
podmiana implementacji nie zmienia kontraktu.
