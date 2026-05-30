from contextlib import asynccontextmanager
import logging
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.AlertHub import AlertHub, AlerHubException
from app.formatters import AlertGroup, build_alert_message, build_alert_title

# Create alerthub named logger
logger = logging.getLogger("alerthub")
logger.propagate = False


class CustomAlert(BaseModel):
    body: str
    title: Optional[str] = None
    level: Optional[str] = None
    url: Optional[str] = None
    group: Optional[str] = None


class AlertResponse(BaseModel):
    status: str = "ok"


def _setup_logging():
    """Configure alerthub named logger with appropriate formatter.
    
    Tries to import Uvicorn's DefaultFormatter to maintain color consistency in local dev,
    but falls back gracefully to a standard Formatter if Uvicorn is not available or used.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        try:
            from uvicorn.logging import DefaultFormatter
            console_formatter = DefaultFormatter("%(levelprefix)s %(message)s")
        except ImportError:
            console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(console_formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    app.state.alerthub = AlertHub()
    yield
    app.state.alerthub.close()


app = FastAPI(lifespan=lifespan)


def get_alerthub(request: Request) -> AlertHub:
    return request.app.state.alerthub


@app.exception_handler(AlerHubException)
async def alerhub_exception_handler(request: Request, exc: AlerHubException):
    logger.error(
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
    logger.warning(
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
    logger.log(
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
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/alert", response_model=AlertResponse)
def alert(alert: CustomAlert, hub: AlertHub = Depends(get_alerthub)) -> AlertResponse:
    hub.send(**alert.model_dump())
    return AlertResponse()


@app.post("/alertmanager-webhook", response_model=AlertResponse)
def alertmanager_webhook(
    alert_group: AlertGroup,
    hub: AlertHub = Depends(get_alerthub)
) -> AlertResponse:
    firing_alerts = [a for a in alert_group.alerts if a.status == "firing"]
    resolved_alerts = [a for a in alert_group.alerts if a.status == "resolved"]
    title = build_alert_title(alert_group, len(firing_alerts))
    url = f"{alert_group.externalURL}/#/alerts?receiver={alert_group.receiver}"
    alert_msg = build_alert_message(firing_alerts, resolved_alerts)
    hub.send(alert_msg, title=title, group="Alertmanager", url=url)
    return AlertResponse()
