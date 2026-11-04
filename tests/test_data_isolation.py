"""Testy nigdy nie piszą do prawdziwego `data/` (poza `data/sample`, tylko do odczytu)."""

from __future__ import annotations

from opimon import config


def test_paths_point_to_tmp(isolated_data_dir):
    real = config.ROOT_DIR / "data"
    for path in (config.DATA_DIR, config.DB_PATH, config.MODELS_DIR, config.DATASETS_DIR,
                 config.CACHE_DIR):
        assert real not in path.parents and path != real
        assert isolated_data_dir == path or isolated_data_dir in path.parents


def test_real_data_dir_has_only_sample():
    real = config.ROOT_DIR / "data"
    extra = {p.name for p in real.iterdir()} - {"sample"}
    # Lokalnie po `streamlit run` mogą być pliki runtime – ważne, że nie są w repo (.gitignore).
    allowed = {"opimon.db", "opimon.db-wal", "opimon.db-shm", "models", "datasets", "cache"}
    assert extra <= allowed, f"nieoczekiwane pliki w data/: {extra - allowed}"
