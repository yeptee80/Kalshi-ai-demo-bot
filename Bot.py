
# KALSHI AI DEMO BOT
# Public market scanner - PAPER TRADING ONLY
# No real orders are placed.

import requests
import math
from datetime import datetime, timezone, timedelta

# ---------------- SETTINGS ----------------

API_BASE = "https://external-api.kalshi.com/trade-api/v2"

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00
RESERVE_PERCENT = 0.20
MAX_HOLD_HOURS = 72

SCAN_LIMIT = 200
MAX_PAGES = 3
MIN_VOLUME = 1
MAX_SPREAD = 0.15

balance = STARTING_BALANCE
daily_profit_loss = 0.00
trades = 0

# ---------------- DASHBOARD ----------------

def show_dashboard():
    print("\n===== KALSHI AI DEMO BOT =====")
    print(f"Starting balance: ${STARTING_BALANCE:.2f}")
    print(f"Current balance:  ${balance:.2f}")
    print(f"Daily P/L:        ${daily_profit_loss:.2f}")
    print(f"Trades:           {trades}")
    print("==============================")

def calculate_risk():
    reserve = balance * RESERVE_PERCENT
    available = max(0, balance - reserve)
    risk = min(MAX_RISK_PER_TRADE, available * 0.02)
    return reserve, available, risk

def show_risk():
    reserve, available, risk = calculate_risk()
    print("\n--- RISK MANAGEMENT ---")
    print(f"Protected reserve: ${reserve:.2f}")
    print(f"Available funds:   ${available:.2f}")
    print(f"Maximum trade risk: ${risk:.2f}")

def can_trade(risk):
    if daily_profit_loss <= -DAILY_STOP_LOSS:
        print("STOP: Daily loss limit reached.")
        return False

    if risk <= 0 or risk > calculate_risk()[2]:
        print("STOP: Risk limit exceeded.")
        return False

    return True

# ---------------- DEMO TRADE RECORDING ----------------

def demo_trade(profit_loss):
    global balance, daily_profit_loss, trades

    risk = MAX_RISK_PER_TRADE

    if not can_trade(risk):
        return

    balance += profit_loss
    daily_profit_loss += profit_loss
    trades += 1

    print("Simulated trade recorded.")
    show_dashboard()

# ---------------- MARKET DATA ----------------

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def price_value(market, dollar_field, cent_field):
    value = market.get(dollar_field)

    if value is not None:
        return number(value)

    value = market.get(cent_field)

    if value is not None:
        return number(value) / 100

    return None

def get_open_markets():
    markets = []
    cursor = None

    print("\nConnecting to Kalshi market data...")

    for page in range(MAX_PAGES):
        params = {
            "limit": SCAN_LIMIT,
            "status": "open"
        }

        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(
                f"{API_BASE}/markets",
                params=params,
                timeout=20
            )
            response.raise_for_status()
            data = response.json()

        except requests.RequestException as error:
            print(f"Market data error: {error}")
            break

        batch = data.get("markets", [])
        markets.extend(batch)

        cursor = data.get("cursor")

        print(f"Page {page + 1}: found {len(batch)} markets")

        if not cursor or not batch:
            break

    return markets

# ---------------- OPPORTUNITY SCANNER ----------------

def hours_until_close(market):
    close_time = market.get("close_time")

    if not close_time:
        return None

    try:
        close = datetime.fromisoformat(
            close_time.replace("Z", "+00:00")
        )

        if close.tzinfo is None:
            close = close.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        return (close - now).total_seconds() / 3600

    except (ValueError, TypeError):
        return None

def score_market(market):
    hours = hours_until_close(market)

    if hours is None or hours <= 0:
        return None

    if hours > MAX_HOLD_HOURS:
        return None

    yes_bid = price_value(
        market, "yes_bid_dollars", "yes_bid"
    )

    yes_ask = price_value(
        market, "yes_ask_dollars", "yes_ask"
    )

    if yes_bid is None or yes_ask is None:
        return None

    if yes_ask <= 0 or yes_ask >= 1:
        return None

    spread = yes_ask - yes_bid

    if spread < 0 or spread > MAX_SPREAD:
        return None

    volume = number(
        market.get("volume_24h_fp",
        market.get("volume_24h", 0))
    )

    liquidity = number(
        market.get("liquidity_dollars", 0)
    )

    if volume < MIN_VOLUME and liquidity <= 0:
        return None

    # Activity and execution-quality score.
    # This is NOT a prediction of winning probability.

    volume_score = min(35, math.log1p(volume) * 5)
    liquidity_score = min(35, math.log1p(liquidity) * 5)
    spread_score = max(0, 30 * (1 - spread / MAX_SPREAD))

    score = volume_score + liquidity_score + spread_score

    return {
        "ticker": market.get("ticker", "Unknown"),
        "title": market.get("title", "Untitled"),
        "category": market.get("category", "Other"),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "spread": spread,
        "volume": volume,
        "liquidity": liquidity,
        "hours": hours,
        "score": score
    }

def scan_markets():
    markets = get_open_markets()
    opportunities = []

    print(f"\nMarkets downloaded: {len(markets)}")

    for market in markets:
        result = score_market(market)

        if result:
            opportunities.append(result)

    opportunities.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    print("\n===== TOP MARKET OPPORTUNITIES =====")

    if not opportunities:
        print("No markets currently meet our filters.")
        print("The bot will not force a trade.")
        return []

    for index, item in enumerate(opportunities[:15], 1):
        print(f"\n#{index} {item['title']}")
        print(f"Ticker: {item['ticker']}")
        print(f"Category: {item['category']}")
        print(f"YES bid/ask: ${item['yes_bid']:.3f} / ${item['yes_ask']:.3f}")
        print(f"Spread: ${item['spread']:.3f}")
        print(f"24h volume: {item['volume']}")
        print(f"Liquidity: ${item['liquidity']:.2f}")
        print(f"Hours to close: {item['hours']:.1f}")
        print(f"Activity score: {item['score']:.1f}/100")

    return opportunities

# ---------------- BOT START ----------------

if __name__ == "__main__":
    show_dashboard()
    show_risk()

    print("\nBot ready for demo market scanning.")
    print("Scanning all available market categories.")
    print("Maximum market time horizon: 72 hours.")
    print("Short-term opportunities are prioritized.")
    print("No real orders will be placed.")

    opportunities = scan_markets()

    print("\n===== SCAN COMPLETE =====")
    print(f"Qualified markets: {len(opportunities)}")
    print("Paper trading only.")
