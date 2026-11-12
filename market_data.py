"""Public, read-only Kalshi market data."""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

API = "https://external-api.kalshi.com/trade-api/v2"
REQUIRED_SERIES = ("KXBTC15M", "KXETH15M")
FIFTEEN_MINUTES = timedelta(minutes=15)
INTERVAL = re.compile(r"\b(?:15|fifteen)[ _-]*(?:minutes?|mins?|m)\b", re.I)
OPEN = {"active", "open"}


def get_data(path, params=None):
    url = API + path + ("?" + urlencode(params) if params else "")
    for attempt in range(4):
        delay = 2 ** attempt
        try:
            with urlopen(url, timeout=15) as response:
                return json.load(response, parse_float=Decimal)
        except HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                raise
            try:
                delay = float(error.headers.get("Retry-After", delay))
            except ValueError:
                pass
            delay = max(1, min(delay, 30))
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
        print(f"Retrying Kalshi GET {path} in {delay:g}s", flush=True)
        time.sleep(delay)


def get_markets(**params):
    query = {**params, "limit": 1000}
    seen_cursors = set()
    while True:
        data = get_data("/markets", query)
        yield from data["markets"]
        cursor = data.get("cursor")
        if not cursor:
            return
        if cursor in seen_cursors:
            raise RuntimeError("Kalshi returned a repeated markets cursor")
        seen_cursors.add(cursor)
        query["cursor"] = cursor


def timestamp(value):
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed
        except (ValueError, TypeError):
            pass
    return None


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def series_ticker(market):
    return (market.get("event_ticker") or market["ticker"]).split("-", 1)[0]


def is_short_series(series):
    return (series["ticker"].upper().endswith("15M")
            or any(INTERVAL.search(series.get(field) or "")
                   for field in ("frequency", "title")))


def is_short_market(market, known):
    opened = timestamp(market.get("open_time"))
    closes = timestamp(market.get("close_time"))
    return (series_ticker(market) in known
            or bool(opened and closes and closes - opened == FIFTEEN_MINUTES)
            or bool(INTERVAL.search(market.get("title") or "")))


def open_at(market, now):
    opens = timestamp(market.get("open_time"))
    closes = timestamp(market.get("close_time"))
    return market.get("status") in OPEN and opens and closes and opens <= now < closes


def scan_short_markets(now):
    catalog = {series["ticker"]: series for series in get_data("/series")["series"]}
    known = set(REQUIRED_SERIES)
    known.update(ticker for ticker, series in catalog.items() if is_short_series(series))

    # Close-time filters are incompatible with status=open. Check status locally.
    queries = [
        {"min_close_ts": int(now.timestamp()),
         "max_close_ts": int((now + FIFTEEN_MINUTES).timestamp()) + 1},
        *({"series_ticker": ticker, "status": "open"} for ticker in sorted(known)),
    ]
    markets = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for batch in pool.map(lambda query: list(get_markets(**query)), queries):
            for market in batch:
                if open_at(market, now) and is_short_market(market, known):
                    markets[market["ticker"]] = market
    return markets, catalog, known


def market_by_ticker(ticker):
    path = "/markets/" + quote(ticker, safe="")
    try:
        return get_data(path)["market"]
    except HTTPError as error:
        if error.code != 404:
            raise
    return get_data("/historical" + path)["market"]


def series_for_event(market, catalog):
    event_ticker = market.get("event_ticker")
    if not event_ticker:
        return None, {}
    event = get_data("/events/" + quote(event_ticker, safe=""))["event"]
    ticker = event.get("series_ticker") or series_ticker(market)
    series = catalog.get(ticker)
    if series is None:
        return None, event
    return series, event


def best_levels(ticker):
    path = "/markets/" + quote(ticker, safe="") + "/orderbook"
    book = get_data(path, {"depth": 1})["orderbook_fp"]
    levels = {}
    for side in ("yes", "no"):
        rows = book.get(side + "_dollars") or []
        if rows:
            price, size = map(number, rows[-1])
            if price is not None and 0 < price < 1 and size is not None and size >= 1:
                levels[side] = (price, size)
    return levels
