
import requests
from datetime import datetime, timezone

# KALSHI MARKET SCANNER
# DEMO / PUBLIC DATA ONLY
# DOES NOT PLACE TRADES

API = "https://api.elections.kalshi.com/trade-api/v2"

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00
RESERVE_PERCENT = 0.20

MAX_HOLD_HOURS = 72
MAX_PAGES = 10
PAGE_SIZE = 1000


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return None


def get_markets():
    all_markets = []
    cursor = None

    print("Connecting to Kalshi...")
    
    for page in range(MAX_PAGES):
        params = {
            "status": "open",
            "limit": PAGE_SIZE
        }

        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            API + "/markets",
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        page_markets = data.get("markets", [])
        all_markets.extend(page_markets)

        print(
            "Page",
            page + 1,
            "- received",
            len(page_markets),
            "markets"
        )

        cursor = data.get("cursor")

        if not cursor:
            break

    return all_markets


def is_short_term(market):
    text = (
        str(market.get("ticker", "")) + " " +
        str(market.get("title", ""))
    ).upper()

    terms = [
        "15M", "15-MIN", "15 MIN",
        "FIFTEEN MINUTE"
    ]

    return any(term in text for term in terms)


def get_price(market, field):
    dollars = market.get(field + "_dollars")

    if dollars is not None:
        try:
            return float(dollars)
        except (ValueError, TypeError):
            pass

    cents = market.get(field)

    if cents is not None:
        try:
            return float(cents) / 100
        except (ValueError, TypeError):
            pass

    return None


def main():
    print("\n===== KALSHI DEMO SCANNER =====")
    print("Starting demo balance: $", STARTING_BALANCE)
    print("Maximum risk per trade: $", MAX_RISK_PER_TRADE)
    print("Daily loss limit: $", DAILY_STOP_LOSS)
    print("Profit reserve target:", RESERVE_PERCENT * 100, "%")
    print("Maximum research window:", MAX_HOLD_HOURS, "hours")
    print("\nScanning markets...\n")

    try:
        markets = get_markets()

        print("\nTOTAL MARKETS RECEIVED:", len(markets))

        if not markets:
            print("No markets returned by Kalshi.")
            return

        now = datetime.now(timezone.utc)

        within_window = []
        beyond_window = 0
        missing_dates = 0
        short_term_count = 0
        other_status = 0

        for market in markets:
            status = market.get("status", "")

            if status not in ("open", "active"):
                other_status += 1
                continue

            if is_short_term(market):
                short_term_count += 1

            close_text = (
                market.get("close_time")
                or market.get("expiration_time")
            )

            close_date = parse_date(close_text)

            if close_date is None:
                missing_dates += 1
                continue

            if close_date.tzinfo is None:
                close_date = close_date.replace(
                    tzinfo=timezone.utc
                )

            hours_left = (
                close_date - now
            ).total_seconds() / 3600

            if hours_left <= 0:
                continue

            if hours_left <= MAX_HOLD_HOURS:
                within_window.append(
                    (hours_left, market)
                )
            else:
                beyond_window += 1

        within_window.sort(key=lambda item: item[0])

        print("\n===== DIAGNOSTIC RESULTS =====")
        print("Markets received:", len(markets))
        print("Markets closing within 72 hours:", len(within_window))
        print("Markets closing later:", beyond_window)
        print("Markets missing closing dates:", missing_dates)
        print("15-minute style markets found:", short_term_count)
        print("Other statuses:", other_status)

        print("\n===== SAMPLE MARKET DATA =====")

        sample = markets[0]
        print("Sample ticker:", sample.get("ticker"))
        print("Sample status:", sample.get("status"))
        print("Sample close time:", sample.get("close_time"))
        print("Sample expiration:", sample.get("expiration_time"))

        print("\n===== NEAREST CLOSING MARKETS =====")

        # Show nearest closing markets, including those
        # beyond 72 hours, for diagnosis.
        candidates = []

        for market in markets:
            close_text = (
                market.get("close_time")
                or market.get("expiration_time")
            )

            close_date = parse_date(close_text)

            if close_date is None:
                continue

            if close_date.tzinfo is None:
                close_date = close_date.replace(
                    tzinfo=timezone.utc
                )

            hours = (
                close_date - now
            ).total_seconds() / 3600

            if hours > 0 and market.get("status") in ("open", "active"):
                candidates.append((hours, market))

        candidates.sort(key=lambda item: item[0])

        for hours, market in candidates[:20]:
            print("\n-------------------------")
            print("Title:", market.get("title"))
            print("Ticker:", market.get("ticker"))
            print("Hours until close:", round(hours, 2))
            print("Status:", market.get("status"))
            print("YES bid:", get_price(market, "yes_bid"))
            print("YES ask:", get_price(market, "yes_ask"))

            if is_short_term(market):
                print("SHORT-TERM MARKET")

        if not candidates:
            print("No usable future closing dates found.")

        print("\n===== SCAN COMPLETE =====")
        print("Research only. No trades placed.")
        print("No real money used.")

    except requests.RequestException as error:
        print("\nKALSHI CONNECTION ERROR:")
        print(error)

    except Exception as error:
        print("\nBOT ERROR:")
        print(error)


if __name__ == "__main__":
    main()
