import pytest
from app.modules.AlertHub import AlerHubException


def test_get_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_post_alert_success(client, mocker):
    mock_send = mocker.patch.object(client.app.state.alerthub, "send")
    
    payload = {
        "body": "Test alert body",
        "title": "Test Title",
        "level": "warning",
        "url": "http://example.com",
        "group": "group1"
    }
    response = client.post("/alert", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    mock_send.assert_called_once_with(
        body="Test alert body",
        title="Test Title",
        level="warning",
        url="http://example.com",
        group="group1"
    )


def test_post_alert_missing_body(client):
    # body is a required field in CustomAlert
    payload = {
        "title": "Test Title"
    }
    response = client.post("/alert", json=payload)
    assert response.status_code == 422


def test_post_alert_send_error(client, mocker):
    mock_send = mocker.patch.object(client.app.state.alerthub, "send", side_effect=AlerHubException("bark: connection error"))
    
    payload = {"body": "Test alert body"}
    response = client.post("/alert", json=payload)
    
    assert response.status_code == 500
    json_data = response.json()
    assert json_data["result"] == "failed"
    assert json_data["type"] == "AlerHubException"
    assert "bark: connection error" in json_data["message"]


def test_post_alertmanager_webhook_success(client, mocker):
    mock_send = mocker.patch.object(client.app.state.alerthub, "send")
    
    payload = {
        "version": "4",
        "groupKey": "testKey",
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "bark",
        "groupLabels": {"job": "prometheus-test"},
        "commonLabels": {},
        "commonAnnotations": {},
        "externalURL": "http://prometheus",
        "alerts": [
            {
                "status": "firing",
                "labels": {"severity": "critical", "env": "prod"},
                "annotations": {"summary": "Disk Space Low"},
                "startsAt": "2026-05-30T12:00:00Z",
                "endsAt": "2026-05-30T13:00:00Z",
                "generatorURL": "http://grafana"
            }
        ]
    }
    
    response = client.post("/alertmanager-webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Check if send was called with the properly formatted message
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    body = args[0] if args else kwargs.get("body")
    assert "Alerts Firing" in body
    assert "[CRITICAL] Disk Space Low" in body
    assert kwargs.get("title") == "[FIRING: 1] job:prometheus-test"
    assert kwargs["group"] == "Alertmanager"
    assert kwargs["url"] == "http://prometheus/#/alerts?receiver=bark"


def test_post_alertmanager_webhook_validation_error(client):
    # Invalid JSON missing critical fields
    payload = {
        "status": "firing",
        "alerts": []
    }
    response = client.post("/alertmanager-webhook", json=payload)
    assert response.status_code == 422


def test_not_found(client):
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404
