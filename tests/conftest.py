import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never reach Open-Meteo, DriveBC or Openverse."""
    monkeypatch.setenv("GBS_LIVE_DATA", "0")
    monkeypatch.setenv("GBS_I18N", "0")          # test_i18n.py turns it back on
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _fake_rewriter(monkeypatch):
    """No network LLM in tests: a deterministic rewriter that passes the originality gate."""
    from gbs.editorial import scriptwriter
    from tests.helpers import fake_chat
    monkeypatch.setattr(scriptwriter, "_chat", fake_chat)
    monkeypatch.setattr(scriptwriter, "resolve_model", lambda cfg: "fake")
