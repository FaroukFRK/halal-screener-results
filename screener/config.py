"""Thresholds and settings. Change screening rules here, not in the code that applies them."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    # Universe
    max_price: float = 5.0            # "penny stock" = last close below this (USD)
    min_price: float = 0.0001         # drop zero/garbage quotes

    # AAOIFI-style financial ratios (Shariah Standard No. 21). All are "must be below".
    max_debt_ratio: float = 0.30      # interest-bearing debt / market cap
    max_cash_ratio: float = 0.30      # cash + interest-bearing securities / market cap
    max_income_ratio: float = 0.05    # interest (non-permissible) income / total income

    # Data freshness: older filings get REVIEW instead of PASS
    max_filing_age_days: int = 550

    # Politeness / rate limits
    sec_min_interval: float = 0.12    # SEC allows max 10 requests/second
    yahoo_min_interval: float = 1.0     # Yahoo returns HTTP 429 when faster


SETTINGS = Settings()


def sec_user_agent() -> str:
    """SEC requires a User-Agent that names you and gives a contact email.

    Set it once, e.g.  export SEC_USER_AGENT="Your Name your@email.com"
    See https://www.sec.gov/os/accessing-edgar-data
    """
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise RuntimeError(
            'SEC_USER_AGENT is not set. SEC requires "Name email@domain" '
            '(https://www.sec.gov/os/accessing-edgar-data). Example:\n'
            '  export SEC_USER_AGENT="Jane Doe jane@example.com"'
        )
    return ua


GENERIC_USER_AGENT = "halal-penny-screener/0.1 (+https://github.com/FaroukFRK/halal-screener-results)"
