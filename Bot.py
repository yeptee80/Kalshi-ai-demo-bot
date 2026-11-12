"""Scan Kalshi's public data and run a local paper-trading simulation."""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError

from market_data import (
    best_levels, market_by_ticker, number, open_at, scan_short_markets,
    series_for_event, series_ticker, timestamp,
)
from paper_ledger import EXPOSURE_RATE, ONE, ZERO, locked_ledger

MIN_TIME_LEFT = timedelta(seconds=45)
MAX_SPREAD = Decimal("0.04")
MIN_MIDPOINT = Decimal("0.55")
MAX_MIDPOINT = Decimal("0.75")


def now_utc():
    return datetime.now(timezone.utc)


def category(market, catalog):
    return catalog.get(series_ticker(market), {}).get("category") or "Uncategorized"


def scan_report(markets, catalog, known):
    categories = Counter(category(market, catalog) for market in markets.values())
    counts = Counter(series_ticker(market) for market in markets.values())
    lines = ["### 15-minute scan",
             f"- {len(markets)} open markets across {len(counts)} active series",
             f"- {len(known)} identified 15-minute series in the scan"]
    lines.extend(f"- {name}: {count}" for name, count in sorted(categories.items()))
    lines.extend(f"- {ticker}: {counts[ticker]} open" for ticker in ("KXBTC15M", "KXETH15M"))
    lines.append("")
    lines.append("| Market | Category | Yes bid | Yes ask | Closes (UTC) |")
    lines.append("| --- | --- | ---: | ---: | --- |")
    for ticker, market in sorted(markets.items()):
        lines.append(f"| {ticker} | {category(market, catalog)} | "
                     f"{market.get('yes_bid_dollars', '–')} | "
                     f"{market.get('yes_ask_dollars', '–')} | {market['close_time']} |")
    return "\n".join(lines) + "\n"


def fee_multiplier(market, series, event, now):
    fee_type = event.get("fee_type_override") or series.get("fee_type")
    if fee_type not in {"quadratic", "quadratic_with_maker_fees",
                        "quadratic_with_combo_maker_fees"}:
        return None
    waiver = timestamp(market.get("fee_waiver_expiration_time"))
    if waiver and now < waiver:
        return ZERO
    override = event.get("fee_multiplier_override")
    multiplier = number(series.get("fee_multiplier") if override is None else override)
    return multiplier if multiplier is not None and multiplier >= ZERO else None


def candidate(quotes):
    for side, opposite in (("yes", "no"), ("no", "yes")):
        if side not in quotes or opposite not in quotes:
            return None
        bid, _ = quotes[side]
        other_bid, size = quotes[opposite]
        ask = ONE - other_bid
        midpoint = (bid + ask) / 2
        if ZERO <= ask - bid <= MAX_SPREAD and MIN_MIDPOINT <= midpoint <= MAX_MIDPOINT:
            return side, ask, bid, size
    return None


def quoted_levels(market):
    levels = {}
    for side in ("yes", "no"):
        bid = number(market.get(side + "_bid_dollars"))
        if bid is not None and 0 < bid < ONE:
            levels[side] = (bid, ONE)
    return levels


def trade_cycle(ledger, markets, catalog):
    candidates = []
    for ticker, market in markets.items():
        if ticker in ledger.trades or market.get("market_type") != "binary":
            continue
        quote = candidate(quoted_levels(market))
        if quote:
            _, ask, bid, _ = quote
            volume = number(market.get("volume_fp")) or ZERO
            candidates.append((ask - bid, -volume, ticker))

    notes = []
    for _, _, ticker in sorted(candidates):
        if ledger.apply_daily_stop(now_utc())["stopped"]:
            break
        if ledger.exposure >= ledger.available * EXPOSURE_RATE:
            break
        market = markets[ticker]
        now = now_utc()
        if not open_at(market, now) or timestamp(market["close_time"]) - now < MIN_TIME_LEFT:
            continue
        series, event = series_for_event(market, catalog)
        if series is None:
            continue
        quote = candidate(best_levels(ticker))
        now = now_utc()
        multiplier = fee_multiplier(market, series, event, now)
        if (quote is None or multiplier is None
                or timestamp(market["close_time"]) - now < MIN_TIME_LEFT):
            continue
        side, ask, bid, size = quote
        trade = ledger.buy({**market, "category": series.get("category") or "Uncategorized"},
                           side, ask, bid, size, multiplier, now)
        if trade:
            notes.append(f"- Opened {ticker} {side.upper()} x{trade['quantity']} at "
                         f"${ask} (simulated fee ${trade['fee']})")
    return notes


def settle_positions(ledger):
    notes = []
    for trade in ledger.positions:
        if timestamp(trade["close_time"]) > now_utc():
            continue
        market = market_by_ticker(trade["ticker"])
        settled = ledger.settle(market, now_utc())
        if settled:
            notes.append(f"- Settled {settled['ticker']} ({settled['result']}), "
                         f"net ${settled['net_pnl']}")
    return notes


def run_cycle(args):
    if args.scan_only:
        return scan_report(*scan_short_markets(now_utc()))

    with locked_ledger(args.state) as ledger:
        if args.report_only:
            return ledger.report(now_utc())
        ledger.day(now_utc())
        notes = settle_positions(ledger)
        markets, catalog, known = scan_short_markets(now_utc())
        notes.extend(trade_cycle(ledger, markets, catalog))
        report = ledger.report(now_utc()) + "\n"
        report += "### Activity\n"
        report += "\n".join(notes or ["- No paper fills or settlements this run."]) + "\n\n"
        return report + scan_report(markets, catalog, known)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scan-only", action="store_true", help="read public quotes only")
    mode.add_argument("--report-only", action="store_true", help="show the local ledger offline")
    parser.add_argument("--state", type=Path, default=Path("paper-state/ledger.json"))
    parser.add_argument("--report", type=Path, help="also write the report as Markdown")
    parser.add_argument("--interval", type=int, help="repeat every N seconds, at least 60")
    args = parser.parse_args()
    if args.interval is not None and (args.interval < 60 or args.report_only):
        parser.error("--interval requires a scan or paper-trading mode and at least 60 seconds")
    while True:
        try:
            report = run_cycle(args)
        except (URLError, TimeoutError) as error:
            if args.interval is None or (isinstance(error, HTTPError) and error.code < 500
                                         and error.code not in (408, 429)):
                raise
            print(f"Paper cycle failed ({error}). Retrying in {args.interval}s.",
                  file=sys.stderr, flush=True)
            sleep(args.interval)
            continue
        print(report, flush=True)
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        if args.interval is None:
            return
        sleep(args.interval)


if __name__ == "__main__":
    main()
