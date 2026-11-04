"""Generator przykładowych danych (P0). Wynik jest commitowany do `data/sample/`.

    python scripts/make_sample_data.py

* `data/sample/reviews.jsonl` – opinie w stylu recenzji Steam dla 3 fikcyjnych gier,
  używane przez zaślepkę źródła `SampleSource` (offline). Daty są względne (`age_hours`),
  więc dashboard zawsze pokazuje „ostatnie 30 dni”.
  Zaprojektowane pod demo:
  - „Starfall Odyssey”: ~80% pozytywnych, ale w ostatnich 7 dniach spadek po „patchu 2.0”
    (do pokazania alertów, A5);
  - opinie „podchwytliwe” (negacja, sarkazm, kontrast „but”), na których model słownikowy
    myli się częściej niż modele uczone (M5);
  - pole `voted_up` = etykieta ze źródła, jak w Steam (ewaluacja na danych „na żywo”).
* `data/sample/train_sample.csv` – mały zbiór recenzji FILMOWYCH (`text,label`) w stylu IMDB:
  zaślepka zbioru treningowego. Inna domena niż gry, ale ta sama struktura i charakter
  (anglojęzyczne recenzje rozrywki z etykietą binarną).

Generator jest deterministyczny (seed). `tests/test_sample_data.py` sprawdza, że pliki
w repo są zgodne z wynikiem generatora.
"""

from __future__ import annotations

import csv
import io
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "sample"

GAME_POS = [
    "Absolutely loved this game.",
    "One of the best games I have played this year.",
    "Great value for the price.",
    "Beautiful art style and a fantastic soundtrack.",
    "The combat feels smooth and responsive.",
    "The story kept me hooked for hours.",
    "The developers are active and really listen to the community.",
    "Excellent co-op mode, perfect to play with friends.",
    "Runs perfectly even on my old laptop.",
    "Charming, relaxing and very polished.",
    "Amazing level design, every area feels unique.",
    "Highly recommended, worth every penny.",
]
GAME_NEG = [
    "Honestly a waste of money.",
    "Very disappointing experience.",
    "I cannot recommend this in its current state.",
    "Boring grind and repetitive missions.",
    "The frame rate drops below 20 fps in every city.",
    "Terrible balance, the late game is broken.",
    "Refunded after two hours.",
    "Awful user interface and clunky controls.",
    "Too many bugs, my quests keep failing.",
    "Overpriced for the amount of content.",
]
GAME_TRICKY_POS = [
    "Not bad at all, I was not expecting it to be this addictive.",
    "I did not think I would sink two hundred hours into this, but here we are.",
    "Hard to put down. Lost a whole weekend to it.",
    "Never had a single crash, which is rare these days.",
    "Not perfect, but I keep coming back every evening.",
]
GAME_TRICKY_NEG = [
    "I wanted to love it, but the performance is a joke.",
    "Great, another update that breaks my save files.",
    "The trailer looked amazing. The actual game does not.",
    "Good idea, terrible execution.",
    "Fun for the first hour, then nothing new happens.",
]
PATCH_NEG = [
    "Patch 2.0 ruined the performance, stuttering everywhere.",
    "Since the 2.0 update the game crashes on launch.",
    "The new patch broke my saves and the servers are down.",
    "After the latest update my fps halved. Please roll it back.",
]

MOVIE_POS = [
    "A brilliant film with outstanding performances.",
    "The acting was superb and the plot was gripping.",
    "Beautifully shot, with a moving soundtrack.",
    "One of the best movies I have seen in years.",
    "Funny, warm and surprisingly deep.",
    "The director did an excellent job with the pacing.",
    "A great cast and a clever, original script.",
    "I loved every minute of it.",
    "Highly recommended for the whole family.",
    "A masterpiece of modern cinema.",
]
MOVIE_NEG = [
    "Dull, predictable and far too long.",
    "The worst movie I have seen in years.",
    "Wooden acting and a boring script.",
    "A complete waste of time and money.",
    "The plot makes no sense and the ending is awful.",
    "Terrible dialogue, I almost walked out.",
    "Overhyped and disappointing.",
    "Poor special effects and a lazy story.",
    "I was bored after twenty minutes.",
    "Cheap, loud and forgettable.",
]
MOVIE_TRICKY_POS = [
    "Not what I expected, in the best possible way.",
    "I did not think a three hour film could fly by so fast.",
    "Never boring, not even for a second.",
]
MOVIE_TRICKY_NEG = [
    "I wanted to like it, but the story falls apart.",
    "Great trailer, shame about the movie.",
    "The first act is promising. Then it goes nowhere.",
]

GAMES = [
    # key, name, liczba opinii, udział pozytywnych, (udział w ostatnich 7 dniach | None)
    ("starfall", "Starfall Odyssey", 90, 0.82, 0.30),
    ("ironharbor", "Iron Harbor Tactics", 60, 0.58, None),
    ("pixelbakery", "Pixel Bakery Tycoon", 45, 0.88, None),
]
DAYS = 30


def _compose(rng: random.Random, plain: list[str], tricky: list[str], k: int) -> str:
    """1–2 zwykłe zdania + z prawdopodobieństwem 0.3 zdanie „podchwytliwe”."""
    if rng.random() < 0.3:
        parts = [rng.choice(tricky), *rng.sample(plain, k=rng.randint(0, k - 1))]
    else:
        parts = rng.sample(plain, k=rng.randint(1, k))
    return " ".join(parts)


def make_reviews(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for key, name, count, share, recent_share in GAMES:
        for i in range(count):
            age_hours = round(rng.uniform(1, DAYS * 24), 1)
            recent = age_hours <= 7 * 24
            p = recent_share if (recent and recent_share is not None) else share
            positive = rng.random() < p
            if positive:
                text = _compose(rng, GAME_POS, GAME_TRICKY_POS, 3)
            else:
                text = _compose(rng, GAME_NEG, GAME_TRICKY_NEG, 3)
                if recent and recent_share is not None and rng.random() < 0.7:
                    text = f"{rng.choice(PATCH_NEG)} {text}"
            rows.append({
                "target_key": key,
                "target_name": name,
                "external_id": f"{key}-{i:04d}",
                "author": f"player_{rng.randint(1000, 9999)}",
                "age_hours": age_hours,
                "voted_up": positive,
                "playtime_hours": round(rng.uniform(0.5, 300), 1),
                "text": text,
            })
    rows.sort(key=lambda r: (r["target_key"], r["age_hours"]))
    return rows


def make_training(seed: int = 7, per_class: int = 120) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    rows = [(_compose(rng, MOVIE_POS, MOVIE_TRICKY_POS, 3), "positive") for _ in range(per_class)]
    rows += [(_compose(rng, MOVIE_NEG, MOVIE_TRICKY_NEG, 3), "negative") for _ in range(per_class)]
    rng.shuffle(rows)
    return rows


def render() -> dict[str, str]:
    """Nazwa pliku -> zawartość (używane też przez test zgodności)."""
    reviews = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in make_reviews())
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["text", "label"])
    writer.writerows(make_training())
    return {"reviews.jsonl": reviews, "train_sample.csv": buf.getvalue()}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in render().items():
        (OUT_DIR / name).write_text(content, encoding="utf-8")
        print(f"zapisano {OUT_DIR / name}")


if __name__ == "__main__":
    main()
