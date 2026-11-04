"""Testy CLI i dziennika pobrań (D5). Offline: źródło przykładowe + nagrane odpowiedzi."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opimon import cli, config
from opimon import services as services_mod
from opimon.errors import SourceError
from opimon.models import FetchReport, Target
from opimon.services import build_services
from opimon.sources import MetacriticReviewSource, SampleSource, SteamReviewSource
from opimon.storage import FetchLogEntry, InMemoryFetchLog, SqliteFetchLog
from opimon.storage.db import SCHEMA_VERSION
from tests.fixtures.metacritic.fake import FakeMetacriticHttp
from tests.fixtures.steam.fake import FakeSteamHttp

ROOT = Path(__file__).resolve().parent.parent


class BrokenSource:
    """Źródło, które zawsze zgłasza błąd (np. serwis niedostępny)."""

    name = "broken"
    label = "Zepsute źródło"

    def find_targets(self, query, limit=10):
        return [Target(self.name, "x", "Zepsuty cel")]

    def fetch(self, target, limit=100, since=None):
        raise SourceError("Zepsute źródło: brak połączenia z serwisem.")


@pytest.fixture(autouse=True)
def offline_sources(monkeypatch):
    monkeypatch.setattr(services_mod, "_make_sources", lambda: {
        "steam": SteamReviewSource(http=FakeSteamHttp()),
        "metacritic": MetacriticReviewSource(http=FakeMetacriticHttp()),
        "sample": SampleSource(),
        "broken": BrokenSource(),
    })


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


# ------------------------------------------------------------------ dziennik pobrań
@pytest.mark.parametrize("factory", [InMemoryFetchLog, lambda: SqliteFetchLog(config.DB_PATH)],
                         ids=["memory", "sqlite"])
def test_fetch_log_contract(factory):
    log = factory()
    t0 = datetime(2026, 11, 1, 12, tzinfo=UTC)
    log.record(FetchLogEntry("s:a", "s", t0, 1.5, 10, 7, 7))
    log.record(FetchLogEntry("s:b", "s", t0 + timedelta(minutes=1), 0.2, 0, 0, 0, ("błąd",)))
    log.record(FetchLogEntry("s:a", "s", t0 + timedelta(minutes=2), 0.3, 3, 1, 1))
    assert [e.new for e in log.history()] == [1, 0, 7]
    assert log.last("s:a").new == 1 and log.last("s:none") is None
    assert not log.last("s:b").ok and log.last("s:b").errors == ("błąd",)
    assert len(log.history("s:a", limit=1)) == 1
    log.remove_target("s:a")
    assert [e.target_id for e in log.history()] == ["s:b"]


def test_fetch_is_logged_in_database():
    app = build_services(load_samples=False)
    target = SampleSource().find_targets("pixel")[0]
    app.fetch_reviews("sample", target, 1000)
    app.fetch_reviews("broken", Target("broken", "x", "Zepsuty"))
    again = build_services(load_samples=False)          # nowy proces / restart
    assert again.fetch_log.last(target.id).new == 45
    assert "brak połączenia" in again.fetch_log.last("broken:x").errors[0]
    again.remove_target(target.id)
    assert again.fetch_log.last(target.id) is None


def test_schema_migration_from_v1_adds_fetch_log(tmp_path):
    import sqlite3

    from opimon.storage.db import connect

    path = tmp_path / "old.db"
    conn = connect(path)                                   # baza w wersji 1 = bez fetch_log
    conn.execute("DROP TABLE fetch_log")
    conn.execute("PRAGMA user_version = 1")
    conn.close()
    log = SqliteFetchLog(path)
    log.record(FetchLogEntry("s:a", "s", datetime.now(UTC), 0.1, 1, 1, 1))
    assert log.last("s:a") is not None
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_broken_fetch_log_does_not_break_fetch():
    app = build_services(load_samples=False)

    class BrokenLog(InMemoryFetchLog):
        def record(self, entry):
            raise RuntimeError("dysk pełny")

    app.fetch_log = BrokenLog()
    report = app.fetch_reviews("sample", SampleSource().find_targets("pixel")[0], 10)
    assert report.ok and report.new == 10 and "fetch_log" in app.module_errors


def test_refresh_all_isolates_unexpected_errors(monkeypatch):
    app = build_services(load_samples=False)
    for t in SampleSource().targets()[:2]:
        app.repository.save_target(t)
    original = app.fetch_reviews

    def flaky(source_name, target, *args, **kwargs):
        if target.key == "ironharbor":
            raise RuntimeError("baza zablokowana")
        return original(source_name, target, *args, **kwargs)

    monkeypatch.setattr(app, "fetch_reviews", flaky)
    reports = app.refresh_all()
    assert [r.ok for r in reports] == [False, True]
    assert "baza zablokowana" in reports[0].errors[0] and reports[1].new == 45
    assert not app.fetch_log.last("sample:ironharbor").ok


# ------------------------------------------------------------------ CLI
def test_add_list_refresh_log_remove(capsys):
    code, out, _ = run(capsys, "add", "sample", "starfall")
    assert code == 0 and "[OK ] Starfall Odyssey (sample:starfall): pobrano 90, nowych 90" in out

    code, out, _ = run(capsys, "add", "steam", "https://store.steampowered.com/app/570/Dota_2/")
    assert code == 0 and "Dota 2 (steam:570): pobrano 9, nowych 9" in out

    code, out, _ = run(capsys, "list")
    assert code == 0 and "sample:starfall" in out and "opinii: 90" in out and "(OK)" in out

    code, out, _ = run(capsys, "refresh")
    assert code == 0
    # SampleSource liczy daty względem chwili utworzenia, więc w nowym wywołaniu najnowsza
    # opinia bywa „nowsza” o milisekundy i jest pobierana ponownie – deduplikacja: 0 nowych
    assert "Starfall Odyssey (sample:starfall): pobrano" in out
    assert "Razem: 2 celów, nowych opinii 0, błędów 0." in out

    code, out, _ = run(capsys, "log", "--target", "sample:starfall")
    assert code == 0 and out.count("sample:starfall") == 2

    code, out, _ = run(capsys, "remove", "sample:starfall", "--yes")
    assert code == 0 and "Usunięto „Starfall Odyssey” i 90 opinii." in out
    assert "sample:starfall" not in run(capsys, "list")[1]


def test_refresh_continues_after_failing_target_and_exits_1(capsys):
    run(capsys, "add", "broken", "cokolwiek", "--no-fetch")
    run(capsys, "add", "sample", "pixel", "--no-fetch")
    code, out, _ = run(capsys, "refresh", "--limit", "5")
    assert code == 1
    assert "[BŁĄD] Zepsuty cel (broken:x)" in out and "brak połączenia" in out
    assert "[OK ] Pixel Bakery Tycoon (sample:pixelbakery): pobrano 5, nowych 5" in out
    assert "błędów 1." in out


def test_refresh_filter_by_source(capsys):
    run(capsys, "add", "broken", "x", "--no-fetch")
    run(capsys, "add", "sample", "pixel", "--no-fetch")
    code, out, _ = run(capsys, "refresh", "--source", "sample")
    assert code == 0 and "broken" not in out
    assert run(capsys, "refresh", "--source", "nope")[0] == 2


def test_refresh_without_targets(capsys):
    code, out, _ = run(capsys, "refresh")
    assert code == 0 and "Brak monitorowanych celów" in out


def test_add_errors(capsys):
    code, _, err = run(capsys, "add", "nope", "x")
    assert code == 2 and "Nieznane źródło" in err
    code, _, err = run(capsys, "add", "steam", "999999999")
    assert code == 2 and "nie zna gry" in err
    code, out, _ = run(capsys, "add", "broken", "x")
    assert code == 1 and "[BŁĄD]" in out


def test_remove_requires_confirmation(capsys, monkeypatch):
    run(capsys, "add", "sample", "pixel", "--no-fetch")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    code, _, err = run(capsys, "remove", "sample:pixelbakery")
    assert code == 2 and "--yes" in err
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert run(capsys, "remove", "sample:pixelbakery")[1].strip() == "Anulowano."
    monkeypatch.setattr("builtins.input", lambda prompt: "t")
    assert "Usunięto" in run(capsys, "remove", "sample:pixelbakery")[1]
    assert run(capsys, "remove", "sample:pixelbakery")[0] == 2      # już nie istnieje


def test_cli_does_not_load_samples(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    assert "Brak monitorowanych celów" in run(capsys, "list")[1]


def test_sources_command(capsys):
    out = run(capsys, "sources")[1]
    assert "steam" in out and "metacritic" in out and "sample" in out


def test_cli_as_separate_process_shares_database(tmp_path):
    """`python -m opimon.cli` w osobnym procesie pisze do bazy, którą widzi aplikacja."""
    env = {**os.environ, "OPIMON_DATA_DIR": str(tmp_path / "data"), "OPIMON_LOAD_SAMPLES": "0"}

    def cli_run(*argv):
        return subprocess.run([sys.executable, "-m", "opimon.cli", *argv], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=120)

    added = cli_run("add", "sample", "Iron Harbor")
    assert added.returncode == 0, added.stderr
    assert "nowych 60" in added.stdout
    refreshed = cli_run("refresh")
    assert refreshed.returncode == 0 and "nowych opinii 0" in refreshed.stdout
    assert cli_run("--help").returncode == 0

    from opimon.storage import SqliteReviewRepository

    with SqliteReviewRepository(tmp_path / "data" / "opimon.db") as repo:
        assert repo.count_reviews("sample:ironharbor") == 60
    log = SqliteFetchLog(tmp_path / "data" / "opimon.db")
    assert [e.new for e in log.history("sample:ironharbor")] == [0, 60]


def test_report_line_format():
    app = build_services(load_samples=False)
    line = cli._report_line(app, FetchReport("x:y", errors=["a", "b"]))
    assert line.startswith("[BŁĄD] x:y (x:y): pobrano 0") and line.count("\n       ! ") == 2
