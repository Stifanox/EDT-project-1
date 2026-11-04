# Praca z gitem

Model: **każdy na swoim branchu**, merge po ukończonym etapie, bez obowiązkowego review.
`main` zawsze musi się uruchamiać i przechodzić `pytest -m "not slow and not network"`.

## Branche

| Branch | Kto |
|--------|-----|
| `main` | stabilna wersja, scalamy tylko ukończone etapy |
| `dev/o1`, `dev/o2`, `dev/o3` | robocze branche osób |

## Codzienna praca

```bash
git checkout dev/o2
git pull                       # własne zmiany z innego komputera
git merge origin/main          # pobierz ukończone etapy innych (rób to często!)
# ... praca ...
git add -A && git commit -m "[M3] Add TF-IDF logistic regression model"
git push
```

## Ukończenie etapu → `main`

```bash
git fetch && git merge origin/main     # najpierw scal main do siebie i rozwiąż konflikty u siebie
pytest -m "not slow and not network"   # musi przejść
ruff check .
git checkout main && git pull
git merge --no-ff dev/o2 -m "[M3] Merge TF-IDF model"
git push
git checkout dev/o2
```

Możesz też zrobić Pull Request na GitHubie i zmergować go samodzielnie, co ułatwia późniejsze
śledzenie historii.

## Commity

- **Wiadomości commitów piszemy po angielsku**, w trybie rozkazującym (`Add …`, `Fix …`, `Update …`),
  np. `[D1] Add Steam reviews source with cursor pagination`.
- Prefiks z ID etapu: `[D1]`, `[M3]`, `[A5]`, `[X1]`; zmiany ogólne: `[docs]`, `[infra]`.
- Zmiana pliku wspólnego (kontraktu): osobny commit z prefiksem `[contract]` i wpis w `PROGRESS.md`.

## Konflikty

- `PROGRESS.md`: każda osoba edytuje tylko **swoją sekcję** tabeli i dopisuje wiersze **na końcu**
  dziennika. Jeśli mimo to pojawi się konflikt, zachowaj obie wersje wierszy.
- `opimon/services.py`: każda osoba edytuje tylko **swoje** fabryki i metody, więc konflikty
  powinny dotyczyć sąsiednich linii i dać się łatwo rozwiązać.
- `requirements.txt`: każdy tylko swoją sekcję.

## Pierwsza publikacja na GitHubie (jednorazowo, O1)

```bash
git init -b main
git add -A && git commit -m "[P0] Add project foundation: contracts, stubs, GUI skeleton, docs"
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
for b in dev/o1 dev/o2 dev/o3; do git branch $b && git push -u origin $b; done
```

Pozostałe osoby:

```bash
git clone git@github.com:<org>/<repo>.git && cd <repo>
git checkout dev/o2            # swój branch
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -m "not slow and not network"
```
