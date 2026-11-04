"""Źródła opinii (właściciel: O1). D1: Steam API, D3: web scraping."""

from opimon.sources.http import HttpClient
from opimon.sources.metacritic import MetacriticReviewSource
from opimon.sources.sample import SampleSource
from opimon.sources.steam import SteamReviewSource

__all__ = ["HttpClient", "MetacriticReviewSource", "SampleSource", "SteamReviewSource"]
