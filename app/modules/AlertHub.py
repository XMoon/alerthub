import os
import logging
from typing import Optional
from requests.adapters import HTTPAdapter
from requests_futures.sessions import FuturesSession
from concurrent.futures import Future, as_completed

class AlerHubException(Exception):
    def __init__(self, name: str):
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
            }
        else:
            self.config = config
        max_workers = 5
        self.session = FuturesSession(max_workers=max_workers)
        a = HTTPAdapter(
            max_retries=3, pool_connections=max_workers, pool_maxsize=max_workers
        )
        self.session.mount("http://", a)
        self.session.mount("https://", a)
        if self.config['socks_proxy']:
            self.session.proxies = {'http': self.config['socks_proxy'],
                                    'https': self.config['socks_proxy']}

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
        logging.debug(f"[bark][data]{data}")
        bark_url = f"{self.config['bark_url']}/{self.config['bark_key']}"
        future = self.session.post(bark_url, json=data)
        future.alert_type = 'bark'
        return future

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
            text += f"[{group or 'UNKNOWN'}] {title}\n"
        text += body
        if url:
            url = url.replace('"','%22')
            text += f"\nURL: <a href=\"{url}\" >Link</a>"
        data = {
            "text": text,
            "chat_id": self.config["telegram_chat_id"],
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }
        logging.debug(f"[telegram][data]{text}")
        telegram_url = f"https://api.telegram.org/bot{self.config['telegram_bot_token']}/sendMessage"
        future = self.session.post(telegram_url, json=data)
        future.alert_type = 'telegram'
        return future

    def send(
        self,
        body: str,
        title: Optional[str] = None,
        level: Optional[str] = None,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> None:
        futures = []
        if self.config["bark_key"]:
            futures.append(self.send_bark(body, title, level, url, group))
        if self.config["telegram_bot_token"]:
            futures.append(self.send_telegram(body, title, level, url, group))
        if len(futures) == 0:
            raise AlerHubException("Can't found config, not alert sent!!")
        for future in as_completed(futures):
            resp = future.result()
            if resp.status_code >= 300 and resp.status_code < 200:
                msg = f"send msg to {future.alert_type} failed!!"
                logging.error(msg)
                raise AlerHubException(msg)
            else:
                logging.info(f"sent msg to {future.alert_type} : {resp.text}")

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    alerthub = AlertHub()
    alerthub.send('test alert from alerthub', title='test alert', group='test')
