import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never reach Open-Meteo, DriveBC or Openverse."""
    monkeypatch.setenv("GBS_LIVE_DATA", "0")
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
