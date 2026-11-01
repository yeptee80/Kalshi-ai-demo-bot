
import requests
from datetime import datetime, timezone

# KALSHI DEMO MARKET SCANNER
# Public market data only. No real orders.

API = "https://api.elections.kalshi.com/trade-api/v2"

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00
RESERVE_PERCENT = 0.20
MAX_HOLD_HOURS = 72

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def price(market, field):
    dollars = market.get(field + "_dollars")
    if dollars is not None:
        return number(dollars)

    # Older API format used cents
    cents = market.get(field)
    if cents is not None:
        return number(cents) / 100

    return None

def get_markets():
    markets = []
    cursor = None

    print("Connecting to Kalshi market data...")

    for page in range(3):
        params = {
            "status": "open",
            "limit": 200,
            "with_nested_markets": "true"
        }

        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            API + "/events",
            params=params,
            timeout=25
        )
        response.raise_for_status()

        data = response.json()

        for event in data.get("events", []):
            for market in event.get("markets", []):
                market["_event_title"] = event.get("title", "")
                market["_category"] = event.get("category", "Unknown")
                markets.append(market)

        cursor = data.get("cursor")
        if not cursor:
            break

    # Fallback if the events endpoint returns no markets
    if not markets:
        response = requests.get(
            API + "/markets",
            params={"status": "open", "limit": 1000},
            timeout=25
        )
        response.raise_for_status()
        markets = response.json().get("markets", [])

    return markets

def analyze_market(market):
    if market.get("status") not in ("open", "active"):
        return None

    close_text = market.get("close_time")
    if not close_text:
        return None

    try:
        close_time = datetime.fromisoformat(
            close_text.replace("Z", "+00:00")
        )
        hours_left = (
            close_time - datetime.now(timezone.utc)
        ).total_seconds() / 3600
    except (ValueError, TypeError):
        return None

    if hours_left <= 0 or hours_left > MAX_HOLD_HOURS:
        return None

    ticker = market.get("ticker", "")
    title = market.get("title", "")
    event_title = market.get("_event_title", "")
    category = market.get("_category", "Unknown")

    bid = price(market, "yes_bid")
    ask = price(market, "yes_ask")

    spread = None
    if bid is not None and ask is not None and ask >= bid:
        spread = ask - bid

    volume = number(
        market.get("volume_fp", market.get("volume", 0))
    )

    short_term = (
        "15M" in ticker.upper()
        or "15 MINUTE" in title.upper()
        or "15-MINUTE" in title.upper()
        or "15 MINUTE" in event_title.upper()
    )

    # Ranking is based on activity and available price information.
    # It is NOT a prediction of the outcome.
    score = 0

    score += min(volume / 100, 30)

    if spread is not None:
        if spread <= 0.05:
            score += 30
        elif spread <= 0.10:
            score += 20
        elif spread <= 0.20:
            score += 10
    else:
        score -= 5

    if short_term:
        score += 20

    if hours_left <= 1:
        score += 15
    elif hours_left <= 6:
        score += 10
    elif hours_left <= 24:
        score += 5

    return {
        "ticker": ticker,
        "title": title or event_title,
        "category": category,
        "hours": hours_left,
        "volume": volume,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "short": short_term,
        "score": score
    }

def main():
    print("\n===== KALSHI DEMO SCANNER =====")
    print(f"Demo starting balance: ${STARTING_BALANCE:.2f}")
    print(f"Maximum risk per trade: ${MAX_RISK_PER_TRADE:.2f}")
    print(f"Daily stop loss: ${DAILY_STOP_LOSS:.2f}")
    print(f"Reserve target: {RESERVE_PERCENT:.0%}")
    print("Maximum market closing window: 72 hours")
    print("Scanning all available categories...\n")

    try:
        markets = get_markets()
        print(f"Markets received: {len(markets)}")
if markets:
    print("SAMPLE STATUS:", markets[0].get("status"))
    print("SAMPLE CLOSE:", markets[0].get("close_time"))
    print("SAMPLE FIELDS:", list(markets[0].keys()))
        results = []

        for market in markets:
            result = analyze_market(market)
            if result:
                results.append(result)

        results.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        print(f"Markets within 72 hours: {len(results)}")
        print("\n===== TOP MARKET WATCHLIST =====")

        if not results:
            print("No markets passed the time filter.")
            return

        for item in results[:20]:
            print("\n------------------------------")
            print(item["title"])
            print("Category:", item["category"])
            print("Ticker:", item["ticker"])
            print(f"Hours until close: {item['hours']:.2f}")
            print(f"24-hour volume: {item['volume']:.0f}")

            if item["bid"] is not None:
                print(f"YES bid: ${item['bid']:.4f}")
            if item["ask"] is not None:
                print(f"YES ask: ${item['ask']:.4f}")
            if item["spread"] is not None:
                print(f"Spread: ${item['spread']:.4f}")

            if item["short"]:
                print("SHORT-TERM MARKET: YES")

            print(f"Research score: {item['score']:.1f}")

        print("\n===== SCAN COMPLETE =====")
        print("These are research candidates, not guaranteed trades.")
        print("No orders were placed. Demo mode only.")

    except requests.RequestException as error:
        print("Market data connection error:", error)
    except Exception as error:
        print("Scanner error:", error)

if __name__ == "__main__":
    main()
