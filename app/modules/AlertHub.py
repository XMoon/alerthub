from concurrent.futures import Future, as_completed
import logging
import os
from typing import Optional

from requests import Response
from requests.adapters import HTTPAdapter
from requests_futures.sessions import FuturesSession

# Create alerthub named logger
logger = logging.getLogger("alerthub")


class AlerHubException(Exception):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


class AlertHub:
    def __init__(self, config: Optional[dict] = None) -> None:
        if config is None:
            self.config = {
                # bark
                "bark_key": os.environ.get("BARK_KEY", ""),
                "bark_url": os.environ.get("BARK_URL", "https://api.day.app"),
                # telegram
                "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
                # proxy
                "socks_proxy": os.environ.get("SOCKS_PROXY", ""),
                # timeout
                "request_timeout": int(os.environ.get("REQUEST_TIMEOUT", 10)),
            }
        else:
            self.config = config

        self.timeout = int(self.config.get("request_timeout", 10))
        max_workers = 5
        self.session = FuturesSession(max_workers=max_workers)
        a = HTTPAdapter(
            max_retries=3, pool_connections=max_workers, pool_maxsize=max_workers
        )
        self.session.mount("http://", a)
        self.session.mount("https://", a)
        if self.config.get('socks_proxy'):
            self.session.proxies = {
                'http': self.config['socks_proxy'],
                'https': self.config['socks_proxy']
            }

        # Validate config at startup
        channels = []
        if self.config.get("bark_key"):
            channels.append("bark")
        if self.config.get("telegram_bot_token"):
            channels.append("telegram")
        if channels:
            logger.info("AlertHub initialized with channels: %s", ", ".join(channels))
        else:
            logger.warning("AlertHub: no notification channels configured")

    @staticmethod
    def _get_error_reason(resp: Response) -> str:
        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            for key in ("message", "detail", "error", "description"):
                value = payload.get(key)
                if value:
                    return str(value)
            return str(payload)

        if payload is not None:
            return str(payload)

        if resp.text:
            return resp.text.strip()

        return resp.reason or "unknown error"

    def send_bark(
        self,
        body: str,
        title: Optional[str] = None,
        level: Optional[str] = None,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Future:
        data = {
            "body": body,
        }
        if title:
            data["title"] = title
        if level:
            data["level"] = level
        if url:
            data["url"] = url
        if group:
            data["group"] = group
        logger.debug("[bark][data] %s", data)
        bark_url = f"{self.config['bark_url']}/{self.config['bark_key']}"
        return self.session.post(bark_url, json=data, timeout=self.timeout)

    def send_telegram(
        self,
        body: str,
        title: Optional[str] = None,
        level: Optional[str] = None,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Future:
        text = ""
        if title:
            text += f"[{group or 'UNKNOWN'}]"
            if level:
                text += f" [{level.upper()}]"
            text += f" {title}\n"
        elif level:
            text += f"[{level.upper()}]\n"
        text += body
        if url:
            url = url.replace('"', '%22')
            text += f"\nURL: <a href=\"{url}\" >Link</a>"
        data = {
            "text": text,
            "chat_id": self.config["telegram_chat_id"],
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }
        logger.debug("[telegram][data] %s", text)
        telegram_url = f"https://api.telegram.org/bot{self.config['telegram_bot_token']}/sendMessage"
        return self.session.post(telegram_url, json=data, timeout=self.timeout)

    def send(
        self,
        body: str,
        title: Optional[str] = None,
        level: Optional[str] = None,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> None:
        future_map: dict[Future, str] = {}
        if self.config.get("bark_key"):
            future_map[self.send_bark(body, title, level, url, group)] = "bark"
        if self.config.get("telegram_bot_token"):
            future_map[self.send_telegram(body, title, level, url, group)] = "telegram"
        if not future_map:
            raise AlerHubException("Can't found config, not alert sent!!")

        errors = []
        for future in as_completed(future_map):
            channel = future_map[future]
            try:
                response = future.result()
                if 200 <= response.status_code < 300:
                    logger.info("sent msg to %s : %s", channel, response.text)
                else:
                    reason = self._get_error_reason(response)
                    errors.append(f"{channel}: {response.status_code} {response.reason} - {reason}")
            except Exception as exc:
                errors.append(f"{channel}: {exc}")

        if errors:
            raise AlerHubException("Failed to send: " + "; ".join(errors))

    def close(self) -> None:
        self.session.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    alerthub = AlertHub()
    alerthub.send('test alert from alerthub', title='test alert', group='test')
