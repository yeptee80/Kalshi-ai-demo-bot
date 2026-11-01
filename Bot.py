
import requests

API = "https://api.elections.kalshi.com/trade-api/v2"

def get_markets():
    markets = []
    cursor = None

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

def is_short_term(market):
    ticker = str(market.get("ticker", "")).upper()
    title = str(market.get("title", "")).upper()
    subtitle = str(market.get("subtitle", "")).upper()

    text = ticker + " " + title + " " + subtitle

    terms = [
        "15M", "15-MIN", "15 MIN",
        "FIFTEEN MIN", "1H", "1HR", "HOURLY"
    ]

    return any(term in text for term in terms)

def main():
    print("KALSHI SHORT-TERM MARKET INVESTIGATION")

    try:
        markets = get_markets()

        short_markets = [
            market for market in markets
            if is_short_term(market)
        ]

        print("TOTAL MARKETS:", len(markets))
        print("SHORT-TERM MATCHES:", len(short_markets))

        print("\n===== SHORT-TERM MARKET DETAILS =====")

        for market in short_markets[:65]:
            print("\n------------------------------")
            print("TITLE:", market.get("title"))
            print("SUBTITLE:", market.get("subtitle"))
            print("YES DESCRIPTION:", market.get("yes_sub_title"))
            print("NO DESCRIPTION:", market.get("no_sub_title"))
            print("TICKER:", market.get("ticker"))
            print("EVENT:", market.get("event_ticker"))
            print("STATUS:", market.get("status"))
            print("CLOSE:", market.get("close_time"))

            print("YES BID:", market.get("yes_bid_dollars"))
            print("YES ASK:", market.get("yes_ask_dollars"))
            print("NO BID:", market.get("no_bid_dollars"))
            print("NO ASK:", market.get("no_ask_dollars"))

            print("LAST PRICE:", market.get("last_price_dollars"))
            print("24H VOLUME:", market.get("volume_24h_fp"))
            print("TOTAL VOLUME:", market.get("volume_fp"))
            print("OPEN INTEREST:", market.get("open_interest_fp"))

            print("RULES:", str(
                market.get("rules_primary", "")
            )[:250])

        print("\n===== INVESTIGATION COMPLETE =====")
        print("No trades placed. Public data only.")

    except requests.RequestException as error:
        print("CONNECTION ERROR:", error)
    except Exception as error:
        print("BOT ERROR:", error)

if __name__ == "__main__":
    main()
