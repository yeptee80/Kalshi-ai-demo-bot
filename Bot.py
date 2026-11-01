
import requests
from datetime import datetime, timezone

API = "https://api.elections.kalshi.com/trade-api/v2"

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00
RESERVE_PERCENT = 0.20

def get_markets():
    markets = []
    cursor = None

    print("Connecting to Kalshi...")

    for page in range(10):
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

        if not cursor:
            break

    return markets

def dollars(market, field):
    value = market.get(field + "_dollars")
    if value is not None:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None

def main():
    print("\n===== KALSHI MARKET DETAILS =====")
    print("Demo balance: $", STARTING_BALANCE)
    print("Maximum risk per trade: $", MAX_RISK_PER_TRADE)
    print("Daily loss limit: $", DAILY_STOP_LOSS)
    print("Reserve target:", RESERVE_PERCENT * 100, "%")

    try:
        markets = get_markets()
        print("\nTOTAL MARKETS:", len(markets))

        now = datetime.now(timezone.utc)
        candidates = []

        for market in markets:
            close_text = market.get("close_time")
            if not close_text:
                continue

            try:
                close_date = datetime.fromisoformat(
                    close_text.replace("Z", "+00:00")
                )
                hours = (
                    close_date - now
                ).total_seconds() / 3600
            except (ValueError, TypeError):
                continue

            if 0 < hours <= 72:
                candidates.append((hours, market))

        candidates.sort(key=lambda item: item[0])

        print("Markets closing within 72 hours:", len(candidates))
        print("\n===== FIRST 30 MARKETS =====")

        for hours, market in candidates[:30]:
            print("\n------------------------------")
            print("TITLE:", market.get("title"))
            print("SUBTITLE:", market.get("subtitle"))
            print("YES DESCRIPTION:", market.get("yes_sub_title"))
            print("NO DESCRIPTION:", market.get("no_sub_title"))
            print("MARKET TICKER:", market.get("ticker"))
            print("EVENT TICKER:", market.get("event_ticker"))
            print("CATEGORY:", market.get("category"))
            print("STATUS:", market.get("status"))
            print("HOURS UNTIL CLOSE:", round(hours, 2))

            print("YES BID:", dollars(market, "yes_bid"))
            print("YES ASK:", dollars(market, "yes_ask"))
            print("NO BID:", dollars(market, "no_bid"))
            print("NO ASK:", dollars(market, "no_ask"))
            print("LAST PRICE:", dollars(market, "last_price"))

            print("VOLUME:", market.get("volume_fp"))
            print("24H VOLUME:", market.get("volume_24h_fp"))
            print("OPEN INTEREST:", market.get("open_interest_fp"))

        print("\n===== SCAN COMPLETE =====")
        print("Research only. No orders placed.")

    except requests.RequestException as error:
        print("CONNECTION ERROR:", error)
    except Exception as error:
        print("BOT ERROR:", error)

if __name__ == "__main__":
    main()
