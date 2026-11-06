"""US-listed common stocks from Nasdaq Trader symbol directories (free, no key).

nasdaqlisted.txt = Nasdaq; otherlisted.txt = NYSE, NYSE American, NYSE Arca, Cboe, IEX.
OTC stocks are not included.
"""
import re
from dataclasses import dataclass

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

OTHER_EXCHANGES = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}

# Non-common-stock instruments, identified by security name.
_EXCLUDE_NAME = re.compile(
    r"\b(warrants?|units?|rights?|preferred|preference|notes|debentures|subordinated|"
    r"trust certificates?|when issued|contingent value)\b|%",
    re.I,
)


@dataclass
class Security:
    symbol: str            # as listed, e.g. "BRK.B"
    name: str
    exchange: str
    financial_status: str = ""   # Nasdaq only: D=deficient, E=delinquent, ...

    @property
    def yahoo_symbol(self) -> str:
        return self.symbol.replace(".", "-")

    @property
    def sec_ticker(self) -> str:
        return self.symbol.replace(".", "-").upper()


def _rows(text: str):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0].split("|")
    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            continue
        parts = ln.split("|")
        if len(parts) != len(header):
            continue
        yield dict(zip(header, parts))


def _keep(symbol: str, name: str, etf: str, test: str) -> bool:
    if etf == "Y" or test == "Y":
        return False
    if not symbol or "$" in symbol or "=" in symbol or "^" in symbol:
        return False
    if _EXCLUDE_NAME.search(name):
        return False
    return True


def parse_nasdaq(text: str) -> list[Security]:
    out = []
    for r in _rows(text):
        sym, name = r["Symbol"].strip(), r["Security Name"].strip()
        if _keep(sym, name, r.get("ETF", ""), r.get("Test Issue", "")):
            out.append(Security(sym, name, "NASDAQ", r.get("Financial Status", "").strip()))
    return out


def parse_other(text: str) -> list[Security]:
    out = []
    for r in _rows(text):
        sym, name = r["ACT Symbol"].strip(), r["Security Name"].strip()
        if _keep(sym, name, r.get("ETF", ""), r.get("Test Issue", "")):
            out.append(Security(sym, name, OTHER_EXCHANGES.get(r.get("Exchange", ""), r.get("Exchange", ""))))
    return out


def load_universe(client) -> list[Security]:
    secs = parse_nasdaq(client.get_text(NASDAQ_URL)) + parse_other(client.get_text(OTHER_URL))
    seen, out = set(), []
    for s in secs:
        if s.symbol not in seen:
            seen.add(s.symbol)
            out.append(s)
    return out
