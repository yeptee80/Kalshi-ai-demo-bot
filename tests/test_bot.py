import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import Bot
import market_data
from paper_ledger import Ledger, locked_ledger, trading_fee

NOW = datetime(2026, 11, 12, 5, 55, tzinfo=timezone.utc)


def market(ticker="KXBTC15M-ROUND", *, minutes=15, status="active"):
    opens = NOW - timedelta(minutes=5)
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0] + "-ROUND",
        "status": status,
        "category": "Crypto",
        "open_time": opens.isoformat(),
        "close_time": (opens + timedelta(minutes=minutes)).isoformat(),
    }


class LedgerTests(unittest.TestCase):
    def buy(self, ledger, ticker, price="0.60", size=1000, now=NOW):
        return ledger.buy(market(ticker), "yes", D(price), D(price) - D("0.01"),
                          D(size), D("1"), now)

    def test_fee_rounds_up_and_respects_multiplier(self):
        self.assertEqual(trading_fee(D("0.5"), 1, D(1)), D("0.02"))
        self.assertEqual(trading_fee(D("0.5"), 100, D(1)), D("1.75"))
        self.assertEqual(trading_fee(D("0.5"), 100, D("0.5")), D("0.88"))
        self.assertEqual(trading_fee(D("0.5"), 100, D(0)), D("0"))

    def test_reserve_and_fee_inclusive_trade_and_aggregate_caps(self):
        ledger = Ledger()
        self.assertEqual(ledger.reserve, D(200))
        self.assertEqual(ledger.available, D(800))
        first = self.buy(ledger, "ONE")
        self.assertEqual(first["quantity"], 38)
        self.assertLessEqual(D(first["premium"]) + D(first["fee"]), D(24))
        for i in range(20):
            self.buy(ledger, f"M-{i}")
            self.assertLessEqual(ledger.exposure, ledger.available * D(".10"))
            self.assertGreaterEqual(ledger.cash, ledger.reserve)
        self.assertGreater(ledger.exposure, D(79))
        self.assertIsNone(self.buy(ledger, "ONE"))

    def test_visible_whole_contract_depth_and_final_settlement(self):
        ledger = Ledger()
        trade = self.buy(ledger, "ONE", size="2.75")
        self.assertEqual(trade["quantity"], 2)
        self.assertEqual(ledger.cash, D("998.76"))
        self.assertEqual(ledger.balance, D("999.96"))
        self.assertIsNone(ledger.settle({"ticker": "ONE", "status": "determined",
                                        "result": "yes"}, NOW))
        result = {"ticker": "ONE", "status": "finalized", "result": "yes"}
        self.assertEqual(ledger.settle(result, NOW)["net_pnl"], "0.76")
        self.assertEqual(ledger.cash, D("1000.76"))
        self.assertEqual(ledger.exposure, D(0))
        self.assertIsNone(ledger.settle(result, NOW))
        self.assertIn("Wins: 1", ledger.report(NOW))

    def test_negative_outcome_includes_fee_and_lowers_caps(self):
        ledger = Ledger()
        self.buy(ledger, "ONE", size=2)
        outcome = {"ticker": "ONE", "status": "finalized", "result": "no"}
        self.assertEqual(ledger.settle(outcome, NOW)["net_pnl"], "-1.24")
        self.assertEqual(ledger.balance, D("998.76"))
        self.assertEqual(ledger.reserve, D("199.76"))
        self.assertLess(ledger.available * D(".03"), D(24))

    def test_scalar_payout_for_no_side(self):
        ledger = Ledger()
        ledger.buy(market("ONE"), "no", D(".50"), D(".49"), D(2), D(1), NOW)
        result = {"ticker": "ONE", "status": "finalized", "result": "scalar",
                  "settlement_value_dollars": ".30"}
        self.assertEqual(D(ledger.settle(result, NOW)["net_pnl"]), D(".36"))

    def test_daily_risk_counts_positions_and_resets_at_chicago_midnight(self):
        ledger = Ledger()
        for index in range(12):
            ticker = f"M-{index}"
            self.buy(ledger, ticker)
            self.assertGreaterEqual(ledger.cash, D(900))
            ledger.settle({"ticker": ticker, "status": "finalized", "result": "no"}, NOW)
        self.assertGreaterEqual(ledger.balance, D(900))
        self.assertLess(ledger.balance, D(901))
        self.assertIsNone(self.buy(ledger, "LAST", price="0.99"))
        self.assertEqual(D(ledger.day(NOW)["start"]), D(1000))
        tomorrow = NOW + timedelta(minutes=5)
        self.assertEqual(D(ledger.day(tomorrow)["start"]), ledger.balance)
        self.assertIsNotNone(self.buy(ledger, "TOMORROW", now=tomorrow))

    def test_stop_latches_through_same_day_recovery(self):
        ledger = Ledger()
        ledger.day(NOW)
        ledger.cash = D(900)
        self.assertTrue(ledger.apply_daily_stop(NOW)["stopped"])
        ledger.cash = D(920)
        self.assertIsNone(self.buy(ledger, "ONE"))
        self.assertIsNotNone(self.buy(ledger, "ONE", now=NOW + timedelta(minutes=5)))

    def test_persistence_and_failed_transaction(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "ledger.json")
            with locked_ledger(path) as ledger:
                self.buy(ledger, "ONE", size=1)
            with self.assertRaisesRegex(ValueError, "rollback"):
                with locked_ledger(path) as ledger:
                    self.buy(ledger, "TWO")
                    raise ValueError("rollback")
            with locked_ledger(path) as ledger:
                self.assertEqual(set(ledger.trades), {"ONE"})
            self.assertEqual(json.loads(path.read_text())["version"], 1)


class ScannerTests(unittest.TestCase):
    def test_global_and_series_scans_deduplicate_and_filter(self):
        btc = market("KXBTC15M-ROUND")
        eth = market("KXETH15M-ROUND")
        commodity = market("GOLD-ROUND", minutes=60)
        sports = market("SPORTS-ROUND")
        ordinary = market("HOURLY-ROUND", minutes=60)
        closed = market("KXBTC15M-CLOSED", status="closed")

        def get_data(path, params=None):
            if path == "/series":
                return {"series": [{"ticker": "GOLD", "frequency": "fifteen_min",
                                    "category": "Commodities"}]}
            ticker = params.get("series_ticker")
            if ticker:
                return {"markets": {"GOLD": [commodity], "KXBTC15M": [btc, closed],
                                    "KXETH15M": [eth]}[ticker]}
            self.assertNotIn("status", params)
            return {"markets": [btc, sports, ordinary], "cursor": ""}

        with patch.object(market_data, "get_data", side_effect=get_data):
            markets, catalog, known = market_data.scan_short_markets(NOW)
        self.assertEqual(set(markets), {m["ticker"] for m in (btc, eth, commodity, sports)})
        self.assertEqual(known, {"KXBTC15M", "KXETH15M", "GOLD"})
        self.assertIn("Commodities: 1", Bot.scan_report(markets, catalog, known))

    def test_cursor_pagination_and_repeated_cursor_failure(self):
        with patch.object(market_data, "get_data",
                          side_effect=[{"markets": [1], "cursor": "x"},
                                       {"markets": [2], "cursor": ""}]) as get:
            self.assertEqual(list(market_data.get_markets(status="open")), [1, 2])
            self.assertEqual(get.call_args.args[1]["cursor"], "x")
        with patch.object(market_data, "get_data", return_value={"markets": [], "cursor": "x"}):
            with self.assertRaisesRegex(RuntimeError, "repeated"):
                list(market_data.get_markets())

    def test_fee_override_and_missing_fee_schedule(self):
        series = {"fee_type": "quadratic", "fee_multiplier": 1}
        self.assertEqual(Bot.fee_multiplier({}, series, {"fee_multiplier_override": 0}, NOW), D(0))
        self.assertIsNone(Bot.fee_multiplier({}, series, {"fee_type_override": "unknown"}, NOW))

    def test_trade_cycle_uses_refreshed_ask_and_order_book_depth(self):
        source = market()
        source.update(market_type="binary", yes_bid_dollars=".58", no_bid_dollars=".40")
        levels = {"yes": (D(".60"), D(500)), "no": (D(".38"), D("3.50"))}
        series = {"category": "Crypto", "fee_type": "quadratic", "fee_multiplier": 1}
        ledger = Ledger()
        with (patch.object(Bot, "now_utc", return_value=NOW),
              patch.object(Bot, "series_for_event", return_value=(series, {})),
              patch.object(Bot, "best_levels", return_value=levels)):
            notes = Bot.trade_cycle(ledger, {source["ticker"]: source}, {})
        trade = ledger.trades[source["ticker"]]
        self.assertEqual(trade["entry_ask"], "0.62")
        self.assertEqual(trade["quantity"], 3)
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
