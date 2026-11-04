"""Wiersz poleceń do monitorowania (D5): `python -m opimon.cli <polecenie>`.

    refresh [--limit N] [--source S]   pobierz przyrostowo nowe opinie wszystkich celów
    add <źródło> <nazwa|id|URL>        dodaj cel (i od razu pobierz opinie, chyba że --no-fetch)
    list                               monitorowane cele z liczbą opinii i ostatnim pobraniem
    remove <target_id> [--yes]         usuń cel z opiniami, predykcjami i dziennikiem
    log [--target ID] [--limit N]      dziennik pobrań (od najnowszego)
    sources                            dostępne źródła

Korzysta z tej samej bazy co GUI (`config.DB_PATH`; katalog danych: zmienna `OPIMON_DATA_DIR`).
GUI czyta bazę przy każdym odświeżeniu strony, więc zmiany z CLI widać bez restartu.
Nie wczytuje danych przykładowych do pustej bazy (to robi tylko GUI).

Kody wyjścia: 0 – sukces, 1 – błędy pobierania (np. źródło niedostępne), 2 – złe użycie
(nieznane źródło / cel, brak potwierdzenia).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import datetime

from opimon.errors import SourceError
from opimon.models import FetchReport
from opimon.services import AppServices, build_services
from opimon.sources.resolve import resolve_target

EXIT_OK, EXIT_FETCH_ERRORS, EXIT_USAGE = 0, 1, 2


def _fmt_time(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else "–"


def _report_line(services: AppServices, report: FetchReport) -> str:
    status = "OK " if report.ok else "BŁĄD"
    line = (f"[{status}] {services.target_name(report.target_id)} ({report.target_id}): "
            f"pobrano {report.fetched}, nowych {report.new}, przeanalizowano {report.analyzed} "
            f"({report.seconds:.1f} s)")
    return line + "".join(f"\n       ! {e}" for e in report.errors)


def cmd_refresh(services: AppServices, args: argparse.Namespace) -> int:
    targets = services.repository.list_targets()
    if args.source:
        if args.source not in services.sources:
            print(f"Nieznane źródło: {args.source}", file=sys.stderr)
            return EXIT_USAGE
        targets = [t for t in targets if t.source == args.source]
    if not targets:
        print("Brak monitorowanych celów. Dodaj cel: python -m opimon.cli add <źródło> <nazwa>")
        return EXIT_OK
    reports = []
    for t in targets:          # pojedynczo: błąd jednego celu nie przerywa pozostałych
        try:
            report = services.fetch_reviews(t.source, t, args.limit)
        except Exception as exc:  # noqa: BLE001
            report = FetchReport(t.id, errors=[f"Nieoczekiwany błąd: {exc}"])
        reports.append(report)
        print(_report_line(services, report), flush=True)
    failed = sum(not r.ok for r in reports)
    print(f"Razem: {len(reports)} celów, nowych opinii {sum(r.new for r in reports)}, "
          f"błędów {failed}.")
    return EXIT_FETCH_ERRORS if failed else EXIT_OK


def cmd_add(services: AppServices, args: argparse.Namespace) -> int:
    source = services.sources.get(args.source)
    if source is None:
        print(f"Nieznane źródło: {args.source}. Dostępne: {', '.join(services.sources)}",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        target = resolve_target(source, " ".join(args.query))
    except SourceError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    if args.no_fetch:
        services.repository.save_target(target)
        print(f"Dodano: {target.name} ({target.id}).")
        return EXIT_OK
    report = services.fetch_reviews(source.name, target, args.limit)
    print(_report_line(services, report))
    return EXIT_OK if report.ok else EXIT_FETCH_ERRORS


def cmd_list(services: AppServices, args: argparse.Namespace) -> int:
    targets = services.repository.list_targets()
    if not targets:
        print("Brak monitorowanych celów.")
        return EXIT_OK
    for t in targets:
        last = services.fetch_log.last(t.id)
        status = "–" if last is None else ("OK" if last.ok else f"BŁĄD: {last.errors[0]}")
        print(f"{t.id}\n    {t.name} · opinii: {services.repository.count_reviews(t.id)} · "
              f"najnowsza: {_fmt_time(services.repository.latest_review_time(t.id))} · "
              f"ostatnie pobranie: {_fmt_time(last.started_at if last else None)} ({status})")
    return EXIT_OK


def cmd_remove(services: AppServices, args: argparse.Namespace) -> int:
    target = services.repository.get_target(args.target_id)
    if target is None:
        print(f"Nieznany cel: {args.target_id} (zobacz: python -m opimon.cli list)",
              file=sys.stderr)
        return EXIT_USAGE
    count = services.repository.count_reviews(target.id)
    if not args.yes:
        if not sys.stdin.isatty():
            print("Potwierdź usunięcie flagą --yes.", file=sys.stderr)
            return EXIT_USAGE
        answer = input(f"Usunąć „{target.name}” i {count} opinii? [t/N] ").strip().lower()
        if answer not in {"t", "tak", "y", "yes"}:
            print("Anulowano.")
            return EXIT_OK
    removed = services.remove_target(target.id)
    print(f"Usunięto „{target.name}” i {removed} opinii.")
    return EXIT_OK


def cmd_log(services: AppServices, args: argparse.Namespace) -> int:
    entries = services.fetch_log.history(args.target, args.limit)
    if not entries:
        print("Dziennik pobrań jest pusty.")
    for e in entries:
        status = "OK " if e.ok else "BŁĄD"
        print(f"{_fmt_time(e.started_at)} [{status}] {e.target_id}: pobrano {e.fetched}, "
              f"nowych {e.new}, przeanalizowano {e.analyzed} ({e.seconds:.1f} s)"
              + "".join(f"\n       ! {err}" for err in e.errors))
    return EXIT_OK


def cmd_sources(services: AppServices, args: argparse.Namespace) -> int:
    for name, src in services.sources.items():
        print(f"{name:12} {src.label}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m opimon.cli",
        description="Monitorowanie opinii z wiersza poleceń (ta sama baza co GUI).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="więcej logów na stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh", help="pobierz nowe opinie wszystkich celów")
    p.add_argument("--limit", type=int, default=None, help="maks. opinii na cel")
    p.add_argument("--source", help="tylko cele z tego źródła (np. steam)")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("add", help="dodaj cel i pobierz jego opinie")
    p.add_argument("source", help="źródło: steam, metacritic, sample")
    p.add_argument("query", nargs="+", help="nazwa, identyfikator (appid) lub URL")
    p.add_argument("--limit", type=int, default=None, help="maks. opinii do pobrania")
    p.add_argument("--no-fetch", action="store_true", help="tylko zapisz cel")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="monitorowane cele")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("remove", help="usuń cel z opiniami")
    p.add_argument("target_id", help="np. steam:570 (patrz: list)")
    p.add_argument("--yes", "-y", action="store_true", help="bez pytania o potwierdzenie")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("log", help="dziennik pobrań")
    p.add_argument("--target", help="tylko ten cel")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("sources", help="dostępne źródła")
    p.set_defaults(func=cmd_sources)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    services = build_services(load_samples=False)
    return args.func(services, args)


if __name__ == "__main__":
    sys.exit(main())
