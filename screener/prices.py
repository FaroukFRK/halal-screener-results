"""Prices from Yahoo Finance's public chart endpoints (free, no key, unofficial)."""
from statistics import mean

SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SPARK_BATCH = 20  # Yahoo rejects larger batches with HTTP 400


def _last(values):
    for v in reversed(values or []):
        if v is not None:
            return float(v)
    return None


def parse_spark(data: dict) -> dict[str, float]:
    out = {}
    for sym, payload in (data or {}).items():
        if isinstance(payload, dict):
            price = _last(payload.get("close"))
            if price is not None:
                out[sym] = price
    return out


def last_closes(client, symbols: list[str], log=lambda *_: None) -> dict[str, float]:
    """Last daily close for many symbols, 20 per request."""
    out = {}
    for i in range(0, len(symbols), SPARK_BATCH):
        batch = symbols[i:i + SPARK_BATCH]
        try:
            data = client.get_json(SPARK_URL, params={"symbols": ",".join(batch), "range": "5d", "interval": "1d"})
        except Exception as e:  # one bad batch must not kill the run; retry symbols one by one
            log(f"  spark batch failed ({e}); retrying singly")
            data = {}
            for s in batch:
                try:
                    data.update(client.get_json(SPARK_URL, params={"symbols": s, "range": "5d", "interval": "1d"}))
                except Exception:
                    pass
        out.update(parse_spark(data))
        if (i // SPARK_BATCH) % 50 == 0:
            log(f"  prices: {min(i + SPARK_BATCH, len(symbols))}/{len(symbols)}")
    return out


def parse_chart(data: dict) -> dict:
    """Last close and 20-day average volume from a chart response."""
    res = ((data or {}).get("chart") or {}).get("result") or []
    if not res:
        return {}
    r = res[0]
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes, vols = quote.get("close") or [], quote.get("volume") or []
    recent_vols = [v for v in vols[-20:] if v is not None]
    price = _last(closes) or (r.get("meta") or {}).get("regularMarketPrice")
    return {
        "price": float(price) if price is not None else None,
        "avg_volume_20d": round(mean(recent_vols)) if recent_vols else None,
    }


def chart_detail(client, symbol: str) -> dict:
    data = client.get_json(CHART_URL.format(symbol=symbol), params={"range": "1mo", "interval": "1d"})
    return parse_chart(data)
