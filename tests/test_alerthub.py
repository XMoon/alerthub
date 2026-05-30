from concurrent.futures import Future
import pytest
from requests import Response
from app.modules.AlertHub import AlertHub, AlerHubException


def create_mock_future(status_code=200, text="ok", json_data=None, exception=None, reason="OK"):
    future = Future()
    if exception:
        future.set_exception(exception)
    else:
        resp = Response()
        resp.status_code = status_code
        resp.reason = reason
        resp._content = (text or "").encode('utf-8')
        if json_data is not None:
            import json
            resp._content = json.dumps(json_data).encode('utf-8')
        future.set_result(resp)
    return future


def test_alerthub_init_env(monkeypatch):
    monkeypatch.setenv("BARK_KEY", "env_bark")
    monkeypatch.setenv("BARK_URL", "https://env_bark_url")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_tg_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "env_tg_chat")
    monkeypatch.setenv("SOCKS_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("REQUEST_TIMEOUT", "15")

    hub = AlertHub()
    assert hub.config["bark_key"] == "env_bark"
    assert hub.config["bark_url"] == "https://env_bark_url"
    assert hub.config["telegram_bot_token"] == "env_tg_token"
    assert hub.config["telegram_chat_id"] == "env_tg_chat"
    assert hub.config["socks_proxy"] == "socks5://127.0.0.1:1080"
    assert hub.config["request_timeout"] == 15
    assert hub.timeout == 15
    # Proxy set correctly in session
    assert hub.session.proxies == {
        "http": "socks5://127.0.0.1:1080",
        "https": "socks5://127.0.0.1:1080",
    }


def test_alerthub_init_dict_override():
    config = {
        "bark_key": "dict_bark",
        "bark_url": "https://dict_bark_url",
        "telegram_bot_token": "dict_tg_token",
        "telegram_chat_id": "dict_tg_chat",
        "request_timeout": 8,
    }
    hub = AlertHub(config=config)
    assert hub.config["bark_key"] == "dict_bark"
    assert hub.config["request_timeout"] == 8
    assert hub.timeout == 8


def test_alerthub_no_channels_warning(caplog):
    import logging
    config = {
        "bark_key": "",
        "telegram_bot_token": "",
    }
    with caplog.at_level(logging.WARNING):
        AlertHub(config=config)
    assert "no notification channels configured" in caplog.text


def test_alerthub_send_no_config():
    config = {
        "bark_key": "",
        "telegram_bot_token": "",
    }
    hub = AlertHub(config=config)
    with pytest.raises(AlerHubException) as excinfo:
        hub.send("test message")
    assert "Can't found config" in str(excinfo.value)


def test_send_bark_request_args(mocker):
    config = {
        "bark_key": "k1",
        "bark_url": "https://bark_url",
        "telegram_bot_token": "",
    }
    hub = AlertHub(config=config)
    
    mock_post = mocker.patch.object(hub.session, "post", return_value=create_mock_future())
    
    hub.send("hello", title="title1", level="active", url="http://link", group="g1")
    
    mock_post.assert_called_once_with(
        "https://bark_url/k1",
        json={
            "body": "hello",
            "title": "title1",
            "level": "active",
            "url": "http://link",
            "group": "g1",
        },
        timeout=hub.timeout,
    )


def test_send_telegram_request_args(mocker):
    config = {
        "bark_key": "",
        "telegram_bot_token": "token1",
        "telegram_chat_id": "chat1",
    }
    hub = AlertHub(config=config)
    
    mock_post = mocker.patch.object(hub.session, "post", return_value=create_mock_future())
    
    hub.send("hello", title="title1", url="http://link?a=1&b=2", group="g1")
    
    expected_text = "[g1] title1\nhello\nURL: <a href=\"http://link?a=1&b=2\" >Link</a>"
    mock_post.assert_called_once_with(
        "https://api.telegram.org/bottoken1/sendMessage",
        json={
            "text": expected_text,
            "chat_id": "chat1",
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        },
        timeout=hub.timeout,
    )


def test_send_timeout_handling(mocker):
    config = {
        "bark_key": "k1",
        "bark_url": "https://bark_url",
        "telegram_bot_token": "",
    }
    hub = AlertHub(config=config)
    
    # Mock future set with a timeout exception
    mock_post = mocker.patch.object(
        hub.session,
        "post",
        return_value=create_mock_future(exception=TimeoutError("Request timed out")),
    )
    
    with pytest.raises(AlerHubException) as excinfo:
        hub.send("hello")
    assert "Request timed out" in str(excinfo.value)


def test_send_mixed_success_failure(mocker):
    config = {
        "bark_key": "k1",
        "bark_url": "https://bark_url",
        "telegram_bot_token": "token1",
        "telegram_chat_id": "chat1",
    }
    hub = AlertHub(config=config)
    
    # Mock Bark succeeding and Telegram failing
    def side_effect(url, **kwargs):
        if "bark" in url:
            return create_mock_future(status_code=200, text="success_bark")
        else:
            return create_mock_future(status_code=500, text="fail_telegram", reason="Internal Error")
            
    mocker.patch.object(hub.session, "post", side_effect=side_effect)
    
    with pytest.raises(AlerHubException) as excinfo:
        hub.send("hello")
    
    assert "telegram" in str(excinfo.value)
    assert "500 Internal Error" in str(excinfo.value)


def test_get_error_reason_json():
    resp = Response()
    resp.status_code = 400
    import json
    resp._content = json.dumps({"message": "invalid key", "detail": "more info"}).encode()
    
    assert AlertHub._get_error_reason(resp) == "invalid key"
    
    resp._content = json.dumps({"error": "another err"}).encode()
    assert AlertHub._get_error_reason(resp) == "another err"
    
    resp._content = json.dumps({"custom": "something"}).encode()
    assert "something" in AlertHub._get_error_reason(resp)


def test_get_error_reason_text():
    resp = Response()
    resp.status_code = 500
    resp.reason = "Server Error"
    resp._content = b"  raw text error  "
    
    assert AlertHub._get_error_reason(resp) == "raw text error"
    
    resp._content = b""
    assert AlertHub._get_error_reason(resp) == "Server Error"


def test_close(mocker):
    hub = AlertHub()
    mock_close = mocker.patch.object(hub.session, "close")
    hub.close()
    mock_close.assert_called_once()
