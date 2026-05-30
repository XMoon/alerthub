import pytest
from fastapi.testclient import TestClient

# Set testing environment variables before importing app
@pytest.fixture
def test_env(monkeypatch):
    monkeypatch.setenv("BARK_KEY", "test_bark_key")
    monkeypatch.setenv("BARK_URL", "https://api.day.app")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_tg_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test_tg_chat_id")
    monkeypatch.setenv("REQUEST_TIMEOUT", "5")


@pytest.fixture
def client(test_env):
    # Import inside fixture to ensure environment variables are set first
    from app.main import app
    with TestClient(app) as c:
        yield c

