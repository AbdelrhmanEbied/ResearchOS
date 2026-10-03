from __future__ import annotations

import pytest

from settings import reset_settings_store


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Never read or write the developer's real settings.json in tests."""
    monkeypatch.setattr("settings.store.DEFAULT_SETTINGS_PATH", tmp_path / "settings.json")
    reset_settings_store()
    yield
    reset_settings_store()
