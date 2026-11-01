
import requests
from datetime import datetime, timezone

API = "https://api.elections.kalshi.com/trade-api/v2"

def get_data(path, params=None):
    r = requests.get(API + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def get_series():
    data = get_data("/series")
    return {
        s["ticker"]: s
        for s in data.get("series", [])
        if s.get("ticker")
    }

def get_events():
    events = []
    cursor = None

    for _ in range(15):
        params = {
            "status": "open",
            "limit": 200,
            "with_nested_markets": "true"
        }
        if cursor:
            params["cursor"] = cursor

        data = get_data("/events", params)
        events.extend(data.get("events", []))
        cursor = data.get("cursor")

        if not cursor:
            break

    return events

def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def hours_left(close_time):
    if not close_time:
        return None
    try:
        close = datetime.fromisoformat(
            close_time.replace("Z", "+00:00")
        )
        return (
            close - datetime.now(timezone.utc)
        ).total_seconds() / 3600
    except (ValueError, TypeError):
        return None

def classify_time(market, series):
    text = " ".join([
        str(market.get("ticker", "")),
        str(market.get("title", "")),
        str(market.get("subtitle", "")),
        str(series.get("frequency", ""))
    ]).upper()

    if any(x in text for x in ["15M", "15 MIN", "15-MIN", "15MIN"]):
        return "15-minute"

    if any(x in text for x in ["HOURLY", "1 HOUR", "1-HOUR", "1HR"]):
        return "hourly"

    hours = hours_left(market.get("close_time"))

    if hours is not None and 0 < hours <= 24:
        return "under 24 hours"

    if hours is not None and 24 < hours <= 72:
        return "1-3 days"

    return "other"

def main():
    print("KALSHI ALL-CATEGORY SCANNER")
    print("PUBLIC DATA ONLY - NO TRADES")

    try:
        series_map = get_series()
        events = get_events()

        categories = {}
        time_groups = {}
        candidates = []

        for event in events:
            series = series_map.get(
                event.get("series_ticker"), {}
            )

            category = (
                series.get("category")
                or event.get("category")
                or "Unclassified"
            )

            categories[category] = categories.get(category, 0) + 1

            for market in event.get("markets", []):
                group = classify_time(market, series)
                time_groups[group] = time_groups.get(group, 0) + 1

                yes_bid = num(market.get("yes_bid_dollars"))
                yes_ask = num(market.get("yes_ask_dollars"))
                no_bid = num(market.get("no_bid_dollars"))
                no_ask = num(market.get("no_ask_dollars"))
                volume = num(market.get("volume_24h_fp"))

                valid = (
                    0 < yes_ask < 1
                    and 0 < no_ask < 1
                    and 0 <= yes_bid <= yes_ask
                    and 0 <= no_bid <= no_ask
                )

                if valid and volume > 0:
                    candidates.append({
                        "category": category,
                        "group": group,
                        "title": market.get("title", ""),
                        "ticker": market.get("ticker", ""),
                        "yes": (yes_bid, yes_ask),
                        "no": (no_bid, no_ask),
                        "volume": volume
                    })

        print("\nOPEN EVENTS:", len(events))
        print("SERIES FOUND:", len(series_map))

        print("\nCATEGORY COUNTS")
        for name, count in sorted(
            categories.items(),
            key=lambda item: item[1],
            reverse=True
        ):
            print(name, ":", count)

        print("\nTIME GROUP COUNTS")
        for name, count in sorted(time_groups.items()):
            print(name, ":", count)

        candidates.sort(
            key=lambda item: item["volume"],
            reverse=True
        )

        print("\nUSABLE QUOTE CANDIDATES:", len(candidates))

        for item in candidates[:50]:
            print("\n--------------------")
            print("CATEGORY:", item["category"])
            print("TIME:", item["group"])
            print("TITLE:", item["title"])
            print("TICKER:", item["ticker"])
            print("YES BID/ASK:", item["yes"])
            print("NO BID/ASK:", item["no"])
            print("24H VOLUME:", item["volume"])

        print("\nSCAN COMPLETE - NO ORDERS PLACED")

    except requests.RequestException as error:
        print("CONNECTION ERROR:", error)
    except Exception as error:
        print("BOT ERROR:", error)

if __name__ == "__main__":
    main()
