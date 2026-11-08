"""Modele sentymentu, zbiory treningowe i ewaluacja (właściciel: O2)."""

from opimon.sentiment.evaluation import evaluate
from opimon.sentiment.imdb import ImdbTrainingData
from opimon.sentiment.stub import LexiconStubModel, WordCountModel
from opimon.sentiment.training_data import SampleTrainingData, split_balanced

__all__ = [
    "ImdbTrainingData",
    "LexiconStubModel",
    "SampleTrainingData",
    "WordCountModel",
    "evaluate",
    "split_balanced",
]
