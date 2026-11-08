"""Pobierz publiczny IMDB z Hugging Face; zachowaj oficjalny train/test w CSV.

Uruchom z katalogu projektu: python scripts/download_imdb.py
Duże dane trafiają wyłącznie do ignorowanego data/datasets/.
"""

from __future__ import annotations

import csv
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opimon import config  # noqa: E402


def main() -> None:
    import pandas as pd

    config.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    destination = config.DATASETS_DIR / "IMDB Dataset.csv"
    if destination.exists():
        print(f"Plik już istnieje: {destination}. Zachowano dane lokalne.")
        return
    temporary = destination.with_suffix(".csv.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["review", "sentiment", "split"])
            for split in ("train", "test"):
                url = ("https://huggingface.co/datasets/stanfordnlp/imdb/resolve/main/"
                       f"plain_text/{split}-00000-of-00001.parquet")
                request = urllib.request.Request(
                    url, headers={"User-Agent": config.HTTP_USER_AGENT}
                )
                part = config.DATASETS_DIR / f"imdb-{split}.parquet"
                print(f"Pobieranie {split}…", flush=True)
                with (
                    urllib.request.urlopen(request, timeout=120) as response,
                    part.open("wb") as fh,
                ):
                    while chunk := response.read(1024 * 1024):
                        fh.write(chunk)
                frame = pd.read_parquet(part)
                for row in frame.itertuples(index=False):
                    writer.writerow([row.text, "positive" if row.label == 1 else "negative", split])
                print(f"Zapisano {len(frame)} przykładów {split}.", flush=True)
        temporary.replace(destination)
        print(f"Gotowe: {destination}")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
