# Inteligentny system monitorowania opinii

Aplikacja pobiera recenzje z Internetu (**Steam Reviews API** oraz **web scraping** recenzji
filmów), automatycznie ocenia ich **sentyment** (pozytywny / negatywny) modelami trenowanymi na
zbiorze **IMDB 50k** i pokazuje wyniki w GUI (Streamlit): dashboard z trendem, słowami
kluczowymi i alertami o spadku sentymentu, przeglądarkę opinii oraz porównanie modeli.

## Zespół

| ID | Osoba | Branch | Zakres |
|----|-------|--------|--------|
| O1 | Mateusz | `dev/o1` | fundament (P0), źródła danych (API + scraping), baza, monitorowanie, integracja |
| O2 | Karol | `dev/o2` | modele sentymentu: zbiór IMDB, VADER, TF-IDF + LR, DistilBERT, ewaluacja |
| O3 | Marcin | `dev/o3` | analiza: statystyki, dashboard, przeglądarka opinii, słowa kluczowe, alerty |

Stan prac: [`PROGRESS.md`](PROGRESS.md) · zasady pracy (także dla agentów AI): [`AGENTS.md`](AGENTS.md) ·
git: [`CONTRIBUTING.md`](CONTRIBUTING.md) · architektura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Wymagania prowadzącego → realizacja

| Wymaganie | Realizacja | Etapy |
|-----------|------------|-------|
| Pobieranie tekstów z Internetu (API / web scraping) | Steam Reviews API; scraping recenzji filmów (IMDb lub inny serwis) | D1, D3 |
| Automatyczna analiza sentymentu (pozytywny / negatywny) | VADER, TF-IDF + regresja logistyczna, DistilBERT; analiza od razu po pobraniu | M2–M4 |
| Model trenowany na danych zgromadzonych wcześniej | IMDB 50k (Kaggle / Hugging Face) | M1, M3 |
| Dane do predykcji pochodzą z Internetu | opinie pobierane na żądanie i cyklicznie (CLI / cron) | D1, D3, D5 |
| Spójność zbiorów treningowego i predykcyjnego | anglojęzyczne recenzje rozrywki z oceną binarną, to samo czyszczenie tekstu; D3 w tej samej domenie co IMDB; ewaluacja na danych z Internetu z etykietą źródła | M1, M5 |
| Prosty GUI | Streamlit: źródła, modele, ewaluacja, dashboard, opinie | D4, M6, M7, A2, A3 |

## Szybki start

```bash
python -m venv .venv && source .venv/bin/activate     # Python ≥ 3.11
pip install -r requirements-dev.txt
streamlit run app.py
```

Przy pustej bazie aplikacja wczytuje **przykładowe opinie offline** (`data/sample/`), więc wszystkie
widoki działają od razu, bez sieci i bez treningu.

Testy i linter:

```bash
pytest -m "not slow and not network"     # obowiązkowe przed merge do main
pytest -m network                        # prawdziwe zapytania do Internetu (D1, D3)
pytest -m slow                           # ciężkie modele (M4) / pełny IMDB
ruff check .
```

Zbiór IMDB (od etapu M1): pobierz *IMDB Dataset of 50K Movie Reviews* z Kaggle i zapisz jako
`data/datasets/IMDB Dataset.csv` (szczegóły i alternatywa z Hugging Face: `docs/tasks/M1.md`).

## Monitorowanie z wiersza poleceń (cron / systemd)

CLI korzysta z tej samej bazy co GUI (`data/opimon.db`), a GUI widzi zmiany bez restartu.

```bash
python -m opimon.cli add steam "Hades II"                 # nazwa, appid lub URL sklepu
python -m opimon.cli add metacritic "Dune: Part Two"      # tytuł, URL lub movie/<slug>
python -m opimon.cli list                                 # cele, liczba opinii, ostatnie pobranie
python -m opimon.cli refresh --limit 200                  # tylko nowe opinie + analiza
python -m opimon.cli log --limit 20                       # dziennik pobrań
python -m opimon.cli remove steam:1145350 --yes
```

Kod wyjścia `refresh`: `0` – wszystko pobrane, `1` – błąd przynajmniej jednego celu (pozostałe
cele i tak są odświeżane), `2` – złe użycie. Katalog danych można zmienić zmienną `OPIMON_DATA_DIR`.

**cron** (co 30 minut; Steam cache'uje odpowiedzi do 10 minut, więc częściej nie ma sensu):

```cron
*/30 * * * * cd /ścieżka/do/projektu && .venv/bin/python -m opimon.cli refresh --limit 200 >> data/refresh.log 2>&1
```

**systemd** (użytkownika), `~/.config/systemd/user/opimon-refresh.service`:

```ini
[Unit]
Description=Monitor opinii – pobranie nowych recenzji

[Service]
Type=oneshot
WorkingDirectory=/ścieżka/do/projektu
ExecStart=/ścieżka/do/projektu/.venv/bin/python -m opimon.cli refresh --limit 200
```

`~/.config/systemd/user/opimon-refresh.timer`:

```ini
[Unit]
Description=Monitor opinii – co 30 minut

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload && systemctl --user enable --now opimon-refresh.timer
journalctl --user -u opimon-refresh.service     # wyniki ostatnich uruchomień
```

## Struktura

```
app.py                      # strona startowa (KPI, linki)
opimon/cli.py               # CLI: python -m opimon.cli refresh|add|list|remove|log (D5)
pages/                      # widoki: 1 Źródła danych (O1), 2 Modele, 3 Ewaluacja (O2), 4 Dashboard, 5 Opinie (O3)
opimon/
  models.py interfaces.py   # KONTRAKTY (zamrożone): modele danych i Protocol-e
  errors.py config.py textproc.py
  services.py               # fasada AppServices + fabryki per osoba
  sources/                  # O1: źródła opinii (zaślepka: SampleSource)
  storage/                  # O1: repozytorium (zaślepka: w pamięci)
  sentiment/                # O2: modele, zbiory treningowe, ewaluacja
  analytics/                # O3: statystyki, trend, słowa, alerty
  ui/                       # state, nav (kontrakt nawigacji), components
data/sample/                # przykładowe dane (w repo); reszta data/ poza repo
scripts/make_sample_data.py # generator data/sample
docs/ARCHITECTURE.md        # przepływ danych, kontrakty, zaślepki, zależności
docs/tasks/<ID>.md          # opis każdego etapu z kryteriami akceptacji
tests/contracts/            # testy kontraktowe – nowa implementacja dopisuje się do listy
```

## Demo (docelowo, po X1)

1. **Źródła danych**: wyszukaj grę na Steam (np. „Cyberpunk”), pobierz 200 najnowszych opinii.
2. **Dashboard**: udział pozytywnych, trend dzienny, słowa chwalone i krytykowane, alerty.
3. **Opinie**: kliknij „negatywne”, przejrzyj opinie, porównaj predykcje modeli z oceną autora.
4. **Ewaluacja**: porównaj modele na teście IMDB i na opiniach ze Steam (zmiana domeny).

Na danych przykładowych: „Starfall Odyssey” ma wyraźny spadek sentymentu w ostatnim tygodniu
(„patch 2.0”), na którym demonstrujemy alerty.
