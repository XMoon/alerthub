from typing import Any, Dict, List
from pydantic import BaseModel


class Alert(BaseModel):
    status: str
    labels: Dict[str, Any]
    annotations: Dict[str, Any]
    startsAt: str
    endsAt: str
    generatorURL: str


class AlertGroup(BaseModel):
    version: str
    groupKey: str
    truncatedAlerts: int
    status: str
    receiver: str
    groupLabels: Dict[str, Any]
    commonLabels: Dict[str, Any]
    commonAnnotations: Dict[str, Any]
    externalURL: str
    alerts: List[Alert]


def build_alert_title(alert_group: AlertGroup, firing_count: int) -> str:
    if alert_group.status == "firing":
        title = f"[{alert_group.status.upper()}: {firing_count}]"
    else:
        title = f"[{alert_group.status.upper()}]"

    for label, value in alert_group.groupLabels.items():
        title += f" {label}:{value}"

    return title


def format_alert_details(alert: Alert) -> str:
    graph_url = alert.generatorURL.replace('"', "%22")
    severity = alert.labels.get('severity', 'unknown').upper()
    summary = alert.annotations.get('summary', 'No summary')
    lines = [
        f"[{severity}] {summary}",
        f'Graph:  <a href="{graph_url}" >Grafana URL</a>',
        "Details:",
    ]

    for label, value in alert.labels.items():
        if label in {"severity", "summary"}:
            continue
        lines.append(f"  - {label}: {value}")

    return "\n".join(lines)


def build_alert_section(title: str, alerts: List[Alert]) -> str:
    if not alerts:
        return ""

    lines = [title]
    for alert in alerts:
        lines.append(format_alert_details(alert))

    return "\n".join(lines) + "\n"


def build_alert_message(firing_alerts: List[Alert], resolved_alerts: List[Alert]) -> str:
    return (
        build_alert_section("Alerts Firing", firing_alerts)
        + build_alert_section("Alerts Resolved", resolved_alerts)
    )
