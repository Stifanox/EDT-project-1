"""Zaślepka repozytorium (P0): wszystko w pamięci procesu. D2 zastępuje ją SQLite."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from opimon.models import Prediction, Review, Target


def _order(reviews: Iterable[Review]) -> list[Review]:
    by_id = sorted(reviews, key=lambda r: r.id)
    return sorted(by_id, key=lambda r: r.created_at, reverse=True)


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self._reviews: dict[str, Review] = {}
        self._targets: dict[str, Target] = {}
        self._predictions: dict[str, dict[str, Prediction]] = {}   # model -> review_id -> pred

    # --- opinie ---
    def add_reviews(self, reviews: Iterable[Review]) -> int:
        new = 0
        for r in reviews:
            if r.id not in self._reviews:
                self._reviews[r.id] = r
                new += 1
        return new

    def get_review(self, review_id: str) -> Review | None:
        return self._reviews.get(review_id)

    def list_reviews(
        self,
        target_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[Review]:
        rows = [
            r for r in self._reviews.values()
            if (target_id is None or r.target_id == target_id)
            and (since is None or r.created_at >= since)
            and (until is None or r.created_at < until)
        ]
        rows = _order(rows)
        return rows if limit is None else rows[:limit]

    def count_reviews(self, target_id: str | None = None) -> int:
        if target_id is None:
            return len(self._reviews)
        return sum(1 for r in self._reviews.values() if r.target_id == target_id)

    # --- cele ---
    def save_target(self, target: Target) -> None:
        self._targets[target.id] = target

    def get_target(self, target_id: str) -> Target | None:
        return self._targets.get(target_id)

    def list_targets(self) -> list[Target]:
        return sorted(self._targets.values(), key=lambda t: (t.name, t.id))

    def remove_target(self, target_id: str) -> None:
        self._targets.pop(target_id, None)
        removed = [rid for rid, r in self._reviews.items() if r.target_id == target_id]
        for rid in removed:
            del self._reviews[rid]
            for preds in self._predictions.values():
                preds.pop(rid, None)

    def latest_review_time(self, target_id: str) -> datetime | None:
        times = [r.created_at for r in self._reviews.values() if r.target_id == target_id]
        return max(times, default=None)

    # --- predykcje ---
    def save_predictions(self, predictions: Iterable[Prediction]) -> None:
        for p in predictions:
            self._predictions.setdefault(p.model_name, {})[p.review_id] = p

    def get_predictions(
        self, model_name: str, review_ids: Iterable[str] | None = None
    ) -> dict[str, Prediction]:
        preds = self._predictions.get(model_name, {})
        if review_ids is None:
            return dict(preds)
        return {rid: preds[rid] for rid in review_ids if rid in preds}

    def delete_predictions(self, model_name: str) -> int:
        return len(self._predictions.pop(model_name, {}))

    def reviews_without_prediction(
        self, model_name: str, target_id: str | None = None
    ) -> list[Review]:
        preds = self._predictions.get(model_name, {})
        return [r for r in self.list_reviews(target_id) if r.id not in preds]
