import logging
from uvicorn.logging import DefaultFormatter
from typing import Optional, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator

from app.modules.AlertHub import AlertHub, AlerHubException

# modules
app = FastAPI()
alerthub = AlertHub()


class Alert(BaseModel):
    body: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    level: Optional[str] = None
    url: Optional[str] = None
    group: Optional[str] = None

    @model_validator(mode="after")
    def require_body_or_text(self) -> "Alert":
        if self.body is None and self.text is None:
            raise ValueError("body or text is required")
        return self


@app.exception_handler(AlerHubException)
async def alerhub_exception_handler(request: Request, exc: AlerHubException):
    return JSONResponse(
        status_code=500,
        content={
            "message": f"Oops! {exc}",
            "type": "AlerHubException",
            "result": "failed",
        },
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
async def alert(alert: Alert) -> Any:
    body = alert.body if alert.body is not None else alert.text
    title = alert.title if alert.title is not None else alert.summary
    return alerthub.send(
        body=body,
        title=title,
        level=alert.level,
        url=alert.url,
        group=alert.group,
    )
