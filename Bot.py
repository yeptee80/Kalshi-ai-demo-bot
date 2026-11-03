
import requests
import time
from datetime import datetime, timezone

API = "https://api.elections.kalshi.com/trade-api/v2"

SERIES_TO_SCAN = [
    "KXBTC15M",
    "KXETH15M",
]

def get_data(path, params=None):
    for attempt in range(6):
        try:
            response = requests.get(
                API + path,
                params=params,
                timeout=30
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else min(2 ** (attempt + 1), 32)
                except ValueError:
                    wait = min(2 ** (attempt + 1), 32)
                wait = max(1, min(wait, 60))
                print(f"Rate limited. Waiting {wait} seconds...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as error:
            if attempt == 5:
                raise
            wait = min(2 ** (attempt + 1), 32)
            print(f"Request error: {error}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError("Kalshi API retries exhausted")

def get_markets(params, max_pages=10):
    markets = []
    cursor = None

    for page in range(max_pages):
        query = dict(params)
        query["limit"] = 200

        if cursor:
            query["cursor"] = cursor

        data = get_data("/markets", query)
        batch = data.get("markets", [])
        markets.extend(batch)

        print(f"Page {page + 1}: {len(batch)} markets")

        cursor = data.get("cursor")
        if not cursor:
            break

        time.sleep(0.5)

    return markets

def price(market, field):
    try:
        return float(market.get(field) or 0)
    except (ValueError, TypeError):
        return 0.0

def show_market(market):
    print("\nMARKET:", market.get("ticker"))
    print("TITLE:", market.get("title"))
    print("CLOSES:", market.get("close_time"))

    for field in [
        "yes_bid_dollars",
        "yes_ask_dollars",
        "no_bid_dollars",
        "no_ask_dollars",
        "volume_24h_fp"
    ]:
        print(field, ":", market.get(field))

def scan_short_markets():
    print("\n=== SHORT-TERM CRYPTO SCANNER ===")

    for series in SERIES_TO_SCAN:
        print("\nSCANNING:", series)

        try:
            markets = get_markets(
                {
                    "series_ticker": series,
                    "status": "open"
                },
                max_pages=10
            )

            print("OPEN MARKETS FOUND:", len(markets))

            for market in markets[:10]:
                show_market(market)

        except (requests.RequestException, RuntimeError) as error:
            print("SERIES ERROR:", series, error)

def scan_all_markets():
    print("\n=== GENERAL MARKET SCANNER ===")

    markets = []
    try:
        markets = get_markets(
            {"status": "open"},
            max_pages=50
        )
    except (requests.RequestException, RuntimeError) as error:
        print("General scan stopped early:", error)

    print("MARKETS SCANNED:", len(markets))

    candidates = []

    for market in markets:
        yes_bid = price(market, "yes_bid_dollars")
        yes_ask = price(market, "yes_ask_dollars")
        volume = price(market, "volume_24h_fp")

        if 0 < yes_bid <= yes_ask < 1 and volume > 0:
            candidates.append(market)

    candidates.sort(
        key=lambda m: price(m, "volume_24h_fp"),
        reverse=True
    )

    print("USABLE QUOTE CANDIDATES:", len(candidates))

    for market in candidates[:20]:
        show_market(market)

def main():
    print("KALSHI AI DEMO SCANNER V3")
    print("TIME:", datetime.now(timezone.utc))
    print("PAPER RESEARCH ONLY - NO REAL TRADES")

    scan_short_markets()
    scan_all_markets()

    print("\nSCAN COMPLETE - NO ORDERS PLACED")

if __name__ == "__main__":
    main()
  
