"""Wspólny klient HTTP dla źródeł O1 (D1, D3).

* nagłówek `User-Agent` projektu (`config.HTTP_USER_AGENT`), timeout `config.HTTP_TIMEOUT_S`;
* odstęp między zapytaniami tego klienta: `config.REQUEST_DELAY_S` (czytany w chwili zapytania);
* przekierowania NIE są wykonywane: API zwracające 3xx zamiast danych to błąd
  (np. Steam przekierowuje na stronę główną, gdy odrzuca zapytanie);
* każdy błąd (sieć, timeout, HTTP, zły JSON) -> `SourceError` z komunikatem po polsku.

Źródła przyjmują w konstruktorze dowolny obiekt z metodą `get_json(url, params)`,
więc testy podmieniają transport na nagrane odpowiedzi (`tests/fixtures/`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

import requests

from opimon import config
from opimon.errors import SourceError


class JsonGetter(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any: ...


class HttpClient:
    def __init__(
        self,
        service: str,
        session: requests.Session | None = None,
        delay_s: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service = service              # nazwa serwisu do komunikatów, np. "Steam"
        self._session = session or requests.Session()
        self._delay_s = delay_s
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def _wait_for_slot(self) -> None:
        delay = config.REQUEST_DELAY_S if self._delay_s is None else self._delay_s
        if self._last_request is not None and delay > 0:
            remaining = delay - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._clock()

    def get(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        self._wait_for_slot()
        try:
            resp = self._session.get(
                url,
                params=params,
                headers={"User-Agent": config.HTTP_USER_AGENT},
                timeout=config.HTTP_TIMEOUT_S,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise SourceError(
                f"{self.service}: przekroczono czas oczekiwania na odpowiedź "
                f"({config.HTTP_TIMEOUT_S:.0f} s). Spróbuj ponownie."
            ) from exc
        except requests.ConnectionError as exc:
            raise SourceError(
                f"{self.service}: brak połączenia z serwisem. Sprawdź dostęp do Internetu."
            ) from exc
        except requests.RequestException as exc:
            raise SourceError(f"{self.service}: błąd zapytania HTTP ({exc}).") from exc

        status = resp.status_code
        if status == 429:
            raise SourceError(
                f"{self.service}: przekroczono limit zapytań (HTTP 429). Odczekaj chwilę "
                "i spróbuj ponownie."
            )
        if 300 <= status < 400:
            where = resp.headers.get("Location", "?")
            raise SourceError(
                f"{self.service}: serwis przekierował zapytanie ({where}) zamiast zwrócić dane. "
                "API może być niedostępne z tej sieci albo zmieniło adres."
            )
        if status >= 400:
            raise SourceError(f"{self.service}: serwis zwrócił błąd HTTP {status}.")
        return resp

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.get(url, params)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(
                f"{self.service}: niepoprawna odpowiedź serwisu (oczekiwano JSON)."
            ) from exc
