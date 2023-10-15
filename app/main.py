import logging
from typing import List, Dict, Any, Optional
import urllib.parse

from uvicorn.logging import DefaultFormatter
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.AlertHub import AlertHub, AlerHubException

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
def alert(request: Request, alert: CustomAlert) -> Any:
    return alerthub.send(alert.model_dump())

@app.post("/alertmanager-webhook")
def alertmanager_webhook(request: Request, alert_group: AlertGroup) -> Dict[str, str]:
    try:
        firing_alerts = [alert for alert in alert_group.alerts if alert.status == "firing"]
        resolved_alerts = [alert for alert in alert_group.alerts if alert.status == "resolved"]
        # title
        if alert_group.status == "firing":
            title =  f"[{alert_group.status.upper()}: {len(firing_alerts)}]"
        else:
            title =  f"[{alert_group.status.upper()}]"
        for grouplable in alert_group.groupLabels:
            title += " " + grouplable + ":" + alert_group.groupLabels[grouplable]
        # url 
        url = f"{alert_group.externalURL}/#/alerts?receiver={alert_group.receiver}"
        # alerts
        alert_msg = ""
        if firing_alerts:
            alert_msg += "Alerts Firing\n"
            for alert in firing_alerts:
                alert_msg += f"[{alert.labels['severity'].upper()}] { alert.annotations['summary'] }\n"
                alert_msg += f"Graph:  <a href=\"{alert.generatorURL.replace('"','%22')}\" >Grafana URL</a>\n"
                alert_msg += f"Details:\n"
                for label in alert.labels:
                    if label not in ['severity', 'summary']:
                        alert_msg += f"  - {label}: {alert.labels[label]}\n"
        if resolved_alerts:
            alert_msg += "Alerts Resolved\n"
            for alert in resolved_alerts:
                alert_msg += f"[{alert.labels['severity'].upper()}] { alert.annotations['summary'] }\n"
                alert_msg += f"Graph:  <a href=\"{alert.generatorURL.replace('"','%22')}\" >Grafana URL</a>\n"
                alert_msg += f"Details:\n"
                for label in alert.labels:
                    if label not in ['severity', 'summary']:
                        alert_msg += f"  - {label}: {alert.labels[label]}\n"
        alerthub.send(alert_msg, title=title, group="Alertmanager", url=url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}