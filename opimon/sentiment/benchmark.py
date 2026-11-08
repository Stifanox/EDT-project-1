"""Powtarzalny pomiar O2: python -m opimon.sentiment.benchmark --help.

To narzędzie pomiarowe O2; nie zastępuje produkcyjnego źródła D1 należącego do O1.
Dane, wagi i wyniki zapisuje wyłącznie w ignorowanych katalogach runtime.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
import urllib.parse
import urllib.request
from dataclasses import asdict

import pandas as pd

from opimon import config
from opimon.errors import SourceError
from opimon.models import Review, Sentiment, Target, utcnow
from opimon.services import build_services
from opimon.textproc import clean_text

APPS = (1091500, 570)


def fetch_live_sample() -> None:
    """Po jednej stronie publicznego API na grę, wyłącznie do pomiaru M2–M5."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for i, app in enumerate(APPS):
        if i:
            time.sleep(config.REQUEST_DELAY_S)
        payload = {"appid": app, "filter": 1, "languages": ["english"],
                   "num_per_page": 100, "purchase_type": 1}
        endpoint = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
        url = endpoint + "?" + urllib.parse.urlencode({"input_json": json.dumps(payload)})
        try:
            request = urllib.request.Request(url, headers={"User-Agent": config.HTTP_USER_AGENT})
            with urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT_S) as response:
                raw = json.load(response)
            data = raw.get("response", raw)
            if not isinstance(data.get("reviews"), list):
                raise ValueError("Brak listy reviews w odpowiedzi Steam.")
            data["retrieved_at"] = utcnow().isoformat()
            data["appid"] = app
            path = config.CACHE_DIR / f"steam-benchmark-{app}.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SourceError(f"Nie można pobrać próbki pomiarowej Steam: {exc}") from exc


def cached_live_reviews() -> list[Review]:
    """Wczytaj zapisane próbki API, odrzucając puste teksty i powtarzające się ID."""
    from datetime import UTC, datetime

    reviews = {}
    for app in APPS:
        path = config.CACHE_DIR / f"steam-benchmark-{app}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data["reviews"]:
            text = clean_text(row["review"])
            if not text:
                continue
            review = Review("steam", str(row["recommendationid"]), f"steam:{app}", text,
                            datetime.fromtimestamp(row["timestamp_created"], UTC),
                            label=Sentiment.POSITIVE if row["voted_up"] else Sentiment.NEGATIVE)
            reviews[review.id] = review
    return list(reviews.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Porównanie modeli IMDB vs Steam (O2).")
    parser.add_argument("--fetch-live", action="store_true", help="Pobierz świeżą próbkę Steam.")
    parser.add_argument("--download-transformer", action="store_true", help="Pobierz wagi SST-2.")
    parser.add_argument("--train", action="store_true", help="Wytrenuj TF-IDF na pełnym IMDB.")
    parser.add_argument("--max-test", type=int, default=1000,
                        help="Limit IMDB test, domyślnie 1000.")
    args = parser.parse_args()
    if args.fetch_live:
        fetch_live_sample()
    services = build_services(load_samples=False)
    train_seconds = None
    if args.train:
        start = time.perf_counter()
        services.train_model("tfidf_lr", "imdb")
        train_seconds = time.perf_counter() - start
    if args.download_transformer:
        info = services.load_model("distilbert", allow_download=True)
        if not info.ready:
            parser.exit(1, info.notes + "\n")
    for app in APPS:
        services.repository.save_target(Target("steam", str(app), f"Steam {app}"))
    services.repository.add_reviews(cached_live_reviews())
    print("Modele:", services.ready_models(), flush=True)
    tables = []
    details = {}
    for on, source in [("test", None), *[("live", s) for s in services.evaluation_sources()]]:
        table = services.compare_models(on=on, dataset_name="imdb",
                                        max_test=args.max_test if on == "test" else None,
                                        source_name=source)
        tables.append(table)
        details[f"{on}:{source or 'imdb'}"] = services.evaluation_details(
            on=on, dataset_name="imdb", max_test=args.max_test if on == "test" else None,
            source_name=source, limit=10)
        print(table.to_string(index=False), flush=True)
    combined = pd.concat(tables, ignore_index=True)
    report = {"recorded_at": utcnow().isoformat(), "platform": platform.platform(),
              "processor": platform.processor(), "train_seconds": train_seconds,
              "models": [asdict(i) for i in services.model_infos()],
              "results": json.loads(combined.to_json(orient="records")), "details": details}
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CACHE_DIR / "m5-benchmark.json"
    path.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wyniki: {path}", flush=True)
    if any(combined["error"]):
        parser.exit(1, "Część modeli zgłosiła błąd; sprawdź wyniki.\n")


if __name__ == "__main__":
    main()
