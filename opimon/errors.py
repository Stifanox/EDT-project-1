"""Wspólne wyjątki (P0, kontrakt). Komunikaty po polsku – GUI pokazuje je użytkownikowi."""

from __future__ import annotations


class OpimonError(Exception):
    """Bazowy wyjątek aplikacji."""


class SourceError(OpimonError):
    """Błąd źródła danych: sieć, limit zapytań, zmiana struktury strony, nieznany cel."""


class ModelNotReadyError(OpimonError):
    """Model wymaga treningu (lub wczytania z dysku) przed predykcją."""


class DatasetUnavailableError(OpimonError):
    """Zbioru treningowego nie ma lokalnie; komunikat mówi, jak go pobrać."""
