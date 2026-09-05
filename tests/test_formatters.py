from app.formatters import (
    Alert,
    AlertGroup,
    build_alert_title,
    format_alert_details,
    build_alert_message,
)


def test_build_alert_title_firing():
    group = AlertGroup(
        version="4",
        groupKey="key",
        truncatedAlerts=0,
        status="firing",
        receiver="bark",
        groupLabels={"job": "prometheus", "alertname": "HighCPU"},
        commonLabels={},
        commonAnnotations={},
        externalURL="http://prometheus",
        alerts=[],
    )
    title = build_alert_title(group, 3)
    assert "[FIRING: 3]" in title
    assert "job:prometheus" in title
    assert "alertname:HighCPU" in title


def test_build_alert_title_resolved():
    group = AlertGroup(
        version="4",
        groupKey="key",
        truncatedAlerts=0,
        status="resolved",
        receiver="bark",
        groupLabels={"job": "prometheus"},
        commonLabels={},
        commonAnnotations={},
        externalURL="http://prometheus",
        alerts=[],
    )
    title = build_alert_title(group, 0)
    assert "[RESOLVED]" in title
    assert "job:prometheus" in title


def test_format_alert_details_full():
    alert = Alert(
        status="firing",
        labels={"severity": "critical", "env": "prod", "instance": "server1"},
        annotations={"summary": "CPU usage high", "description": "CPU > 90%"},
        startsAt="2026-05-30T12:00:00Z",
        endsAt="2026-05-30T13:00:00Z",
        generatorURL='http://grafana/graph?var="test"',
    )
    details = format_alert_details(alert)
    assert "[CRITICAL] CPU usage high" in details
    assert 'Graph:  <a href="http://grafana/graph?var=%22test%22" >Grafana URL</a>' in details
    assert "Details:" in details
    assert "- env: prod" in details
    assert "- instance: server1" in details
    # severity and summary should be excluded from Details list
    assert "- severity:" not in details
    assert "- summary:" not in details


def test_format_alert_details_missing_fields():
    # Test fallback behavior when labels/annotations lack severity/summary
    alert = Alert(
        status="firing",
        labels={"env": "prod"},
        annotations={},
        startsAt="2026-05-30T12:00:00Z",
        endsAt="2026-05-30T13:00:00Z",
        generatorURL="http://grafana",
    )
    details = format_alert_details(alert)
    assert "[UNKNOWN] No summary" in details
    assert "- env: prod" in details


def test_build_alert_message_empty():
    msg = build_alert_message([], [])
    assert msg == ""


def test_build_alert_message_mixed():
    firing = [
        Alert(
            status="firing",
            labels={"severity": "warning"},
            annotations={"summary": "Warn 1"},
            startsAt="2026",
            endsAt="2026",
            generatorURL="http://grafana",
        )
    ]
    resolved = [
        Alert(
            status="resolved",
            labels={"severity": "info"},
            annotations={"summary": "Resolved 1"},
            startsAt="2026",
            endsAt="2026",
            generatorURL="http://grafana",
        )
    ]
    msg = build_alert_message(firing, resolved)
    assert "Alerts Firing" in msg
    assert "[WARNING] Warn 1" in msg
    assert "Alerts Resolved" in msg
    assert "[INFO] Resolved 1" in msg
