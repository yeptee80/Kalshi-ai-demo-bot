
import requests
from datetime import datetime, timezone

API = "https://api.elections.kalshi.com/trade-api/v2"

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00
RESERVE_PERCENT = 0.20

MAX_HOLD_HOURS = 72
MAX_SPREAD = 0.10
MAX_PAGES = 10

def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def get_markets():
    markets = []
    cursor = None

    for page in range(MAX_PAGES):
        params = {"status": "open", "limit": 1000}

        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            API + "/markets",
            params=params,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")

        print("Downloaded page", page + 1)

        if not cursor:
            break

    return markets

def short_term(market):
    text = " ".join([
        str(market.get("ticker", "")),
        str(market.get("event_ticker", "")),
        str(market.get("title", "")),
        str(market.get("subtitle", ""))
    ]).upper()

    patterns = [
        "15M", "15 MIN", "15-MIN",
        "FIFTEEN MIN", "1H", "1HR",
        "HOURLY"
    ]

    return any(pattern in text for pattern in patterns)

def analyze(market, now):
    if market.get("status") != "active":
        return None, "inactive"

    close_text = market.get("close_time")

    if not close_text:
        return None, "no closing time"

    try:
        close = datetime.fromisoformat(
            close_text.replace("Z", "+00:00")
        )

        if close.tzinfo is None:
            close = close.replace(tzinfo=timezone.utc)

        hours = (close - now).total_seconds() / 3600

    except (ValueError, TypeError):
        return None, "bad date"

    if hours <= 0 or hours > MAX_HOLD_HOURS:
        return None, "outside time window"

    yes_bid = num(market.get("yes_bid_dollars"))
    yes_ask = num(market.get("yes_ask_dollars"))
    no_bid = num(market.get("no_bid_dollars"))
    no_ask = num(market.get("no_ask_dollars"))

    volume = num(market.get("volume_24h_fp"))

    yes_spread = yes_ask - yes_bid
    no_spread = no_ask - no_bid

    yes_valid = (
        0 < yes_bid < 1
        and 0 < yes_ask < 1
        and yes_ask >= yes_bid
        and yes_spread <= MAX_SPREAD
    )

    no_valid = (
        0 < no_bid < 1
        and 0 < no_ask < 1
        and no_ask >= no_bid
        and no_spread <= MAX_SPREAD
    )

    if not yes_valid and not no_valid:
        return None, "no usable two-sided quotes"

    if volume <= 0:
        return None, "no recent volume"

    best_spread = min(
        yes_spread if yes_valid else 999,
        no_spread if no_valid else 999
    )

    score = 100 - (best_spread * 500)
    score += min(volume, 1000) / 100

    if short_term(market):
        score += 20

    if hours <= 6:
        score += 10

    return {
        "ticker": market.get("ticker", ""),
        "event": market.get("event_ticker", ""),
        "title": market.get("title", ""),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "volume": volume,
        "spread": best_spread,
        "hours": hours,
        "short": short_term(market),
        "score": score
    }, "qualified"

def main():
    print("\n===== KALSHI OPPORTUNITY SCANNER =====")
    print("Demo balance: $", STARTING_BALANCE)
    print("Maximum risk per trade: $", MAX_RISK_PER_TRADE)
    print("Daily loss limit: $", DAILY_STOP_LOSS)
    print("Reserve target:", RESERVE_PERCENT * 100, "%")
    print("Demo mode only. No orders placed.\n")

    try:
        markets = get_markets()
        now = datetime.now(timezone.utc)

        qualified = []
        rejected = {}
        short_count = 0

        for market in markets:
            if short_term(market):
                short_count += 1

            result, reason = analyze(market, now)

            if result:
                qualified.append(result)
            else:
                rejected[reason] = rejected.get(reason, 0) + 1

        qualified.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        print("\n===== SCAN RESULTS =====")
        print("Markets downloaded:", len(markets))
        print("Short-term keyword matches:", short_count)
        print("Tradeable research candidates:", len(qualified))

        print("\n===== FILTER RESULTS =====")

        for reason, count in rejected.items():
            print(reason + ":", count)

        print("\n===== TOP OPPORTUNITIES =====")

        for item in qualified[:20]:
            print("\n------------------------")
            print("TITLE:", item["title"])
            print("TICKER:", item["ticker"])
            print("EVENT:", item["event"])
            print("YES BID:", item["yes_bid"])
            print("YES ASK:", item["yes_ask"])
            print("NO BID:", item["no_bid"])
            print("NO ASK:", item["no_ask"])
            print("SPREAD:", round(item["spread"], 4))
            print("24H VOLUME:", item["volume"])
            print("HOURS LEFT:", round(item["hours"], 2))
            print("15M/HOURLY KEYWORD:", item["short"])
            print("RESEARCH SCORE:", round(item["score"], 2))

        print("\n===== SCAN COMPLETE =====")
        print("Scores rank market activity and quote quality.")
        print("They do not predict winning outcomes.")
        print("No trades were placed.")

    except requests.RequestException as error:
        print("CONNECTION ERROR:", error)
    except Exception as error:
        print("BOT ERROR:", error)

if __name__ == "__main__":
    main()
