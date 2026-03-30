import logging
from typing import Any, Dict, List, Optional

from uvicorn.logging import DefaultFormatter
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.AlertHub import AlertHub, AlerHubException
from app.modules.json_utils import normalize_json_body

# modules
app = FastAPI()
alerthub = AlertHub()


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


class CustomAlert(BaseModel):
    body: str
    title: Optional[str] = None
    level: Optional[str] = None
    url: Optional[str] = None
    group: Optional[str] = None


def _build_alert_title(alert_group: AlertGroup, firing_count: int) -> str:
    if alert_group.status == "firing":
        title = f"[{alert_group.status.upper()}: {firing_count}]"
    else:
        title = f"[{alert_group.status.upper()}]"

    for label, value in alert_group.groupLabels.items():
        title += f" {label}:{value}"

    return title


def _format_alert_details(alert: Alert) -> str:
    graph_url = alert.generatorURL.replace('"', "%22")
    lines = [
        f"[{alert.labels['severity'].upper()}] {alert.annotations['summary']}",
        f'Graph:  <a href="{graph_url}" >Grafana URL</a>',
        "Details:",
    ]

    for label, value in alert.labels.items():
        if label in {"severity", "summary"}:
            continue
        lines.append(f"  - {label}: {value}")

    return "\n".join(lines)


def _build_alert_section(title: str, alerts: List[Alert]) -> str:
    if not alerts:
        return ""

    lines = [title]
    for alert in alerts:
        lines.append(_format_alert_details(alert))

    return "\n".join(lines) + "\n"


def _build_alert_message(firing_alerts: List[Alert], resolved_alerts: List[Alert]) -> str:
    return (
        _build_alert_section("Alerts Firing", firing_alerts)
        + _build_alert_section("Alerts Resolved", resolved_alerts)
    )


def _is_json_request(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return request.method in {"POST", "PUT", "PATCH"} and (
        "application/json" in content_type or "+json" in content_type
    )


@app.middleware("http")
async def repair_non_standard_json(request: Request, call_next):
    if not _is_json_request(request):
        return await call_next(request)

    body = await request.body()
    normalized_body, repaired = normalize_json_body(body)

    if repaired:
        logging.warning(
            "Recovered non-standard JSON payload on %s %s",
            request.method,
            request.url.path,
        )

    body_sent = False

    async def receive() -> Dict[str, Any]:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}

        body_sent = True
        return {
            "type": "http.request",
            "body": normalized_body,
            "more_body": False,
        }

    request = Request(request.scope, receive)
    return await call_next(request)


@app.exception_handler(AlerHubException)
async def alerhub_exception_handler(request: Request, exc: AlerHubException):
    logging.error(
        "AlerHubException on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "message": f"Oops! {exc}",
            "type": "AlerHubException",
            "result": "failed",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.warning(
        "422 Unprocessable Entity on %s %s: errors=%s body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        exc.body,
    )
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(StarletteHTTPException)
async def http_exception_logging_handler(request: Request, exc: StarletteHTTPException):
    level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    logging.log(
        level,
        "HTTP %s on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logging.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


@app.on_event("startup")
async def startup_event():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    console_formatter = DefaultFormatter("%(levelprefix)s %(message)s")
    handler.setFormatter(console_formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


@app.post("/alert")
def alert(request: Request, alert: CustomAlert) -> Any:
    return alerthub.send(**alert.model_dump())


@app.post("/alertmanager-webhook")
def alertmanager_webhook(request: Request, alert_group: AlertGroup) -> Dict[str, str]:
    try:
        firing_alerts = [alert for alert in alert_group.alerts if alert.status == "firing"]
        resolved_alerts = [alert for alert in alert_group.alerts if alert.status == "resolved"]
        title = _build_alert_title(alert_group, len(firing_alerts))
        url = f"{alert_group.externalURL}/#/alerts?receiver={alert_group.receiver}"
        alert_msg = _build_alert_message(firing_alerts, resolved_alerts)
        alerthub.send(alert_msg, title=title, group="Alertmanager", url=url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok"}
