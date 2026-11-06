"""Small HTTP client: retries, per-client throttle, JSON helper."""
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Client:
    def __init__(self, user_agent: str, min_interval: float = 0.0, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        retry = Retry(total=6, backoff_factor=3.0, backoff_max=120, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, timeout=self.timeout, **kwargs)
        finally:
            self._last = time.monotonic()
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, **kwargs):
        return self.get(url, **kwargs).json()

    def get_text(self, url: str, **kwargs) -> str:
        return self.get(url, **kwargs).text
