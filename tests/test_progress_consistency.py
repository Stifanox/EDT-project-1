"""PROGRESS.md musi być spójny z docs/tasks/*.md (kolumna Postęp = odhaczone kryteria).

Jeśli ten test nie przechodzi: zaktualizuj kolumnę *Postęp* w PROGRESS.md albo checkboxy
w sekcji „Kryteria akceptacji” pliku etapu.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROW_RE = re.compile(
    r"^\| \[(?P<id>\w+)\]\(docs/tasks/(?P=id)\.md\) \|[^|]+\| (?P<status>[^|]+?) \| "
    r"(?P<done>\d+)/(?P<total>\d+) \|",
    re.M,
)
ROWS = list(ROW_RE.finditer((ROOT / "PROGRESS.md").read_text(encoding="utf-8")))
STATUSES = {"⬜ TODO", "🟦 IN_PROGRESS", "✅ DONE", "⛔ BLOCKED", "🔁 REWORK"}
TASK_FILES = {p.stem for p in (ROOT / "docs" / "tasks").glob("*.md")} - {"_TEMPLATE"}


def _criteria(stage_id: str) -> tuple[int, int]:
    text = (ROOT / "docs" / "tasks" / f"{stage_id}.md").read_text(encoding="utf-8")
    section = text.split("## Kryteria akceptacji", 1)[1].split("\n## ", 1)[0]
    return (len(re.findall(r"^- \[x\]", section, re.M)),
            len(re.findall(r"^- \[[ x]\]", section, re.M)))


def test_every_task_file_has_a_row():
    assert {r["id"] for r in ROWS} == TASK_FILES


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_progress_matches_task_file(row):
    done, total = _criteria(row["id"])
    assert (int(row["done"]), int(row["total"])) == (done, total), (
        f"{row['id']}: PROGRESS.md mówi {row['done']}/{row['total']}, plik etapu {done}/{total}"
    )
    assert row["status"] in STATUSES, f"{row['id']}: nieznany status {row['status']!r}"
    if row["status"] == "✅ DONE":
        assert done == total, f"{row['id']}: DONE, ale nie wszystkie kryteria odhaczone"
