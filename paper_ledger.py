"""A fee-aware simulated balance, position ledger and risk controls."""

import json
import os
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from zoneinfo import ZoneInfo

from market_data import number

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
STARTING_BALANCE = Decimal("1000.00")
RESERVE_RATE = Decimal("0.20")
TRADE_RATE = Decimal("0.03")
EXPOSURE_RATE = Decimal("0.10")
DAILY_LOSS_RATE = Decimal("0.10")
TRADING_ZONE = ZoneInfo("America/Chicago")


def trading_fee(price, quantity, multiplier):
    fee = Decimal("0.07") * multiplier * quantity * price * (ONE - price)
    return fee.quantize(CENT, rounding=ROUND_CEILING)


def cost_at(price, quantity, multiplier):
    premium = price * quantity
    fee = trading_fee(price, quantity, multiplier)
    return premium, fee


class Ledger:
    def __init__(self, data=None):
        if data is None:
            data = {"version": 1, "cash": str(STARTING_BALANCE), "days": {}, "trades": {}}
        if data["version"] != 1:
            raise ValueError("Unsupported paper ledger version")
        self.data = data
        self.trades = data["trades"]

    @property
    def cash(self):
        return Decimal(self.data["cash"])

    @cash.setter
    def cash(self, amount):
        self.data["cash"] = str(amount)

    @property
    def positions(self):
        return [trade for trade in self.trades.values() if trade["payout"] is None]

    @property
    def balance(self):
        return self.cash + sum(Decimal(trade["premium"]) for trade in self.positions)

    @property
    def exposure(self):
        return sum((Decimal(trade["premium"]) + Decimal(trade["fee"])
                    for trade in self.positions), ZERO)

    @property
    def reserve(self):
        return (self.balance * RESERVE_RATE).quantize(CENT, rounding=ROUND_CEILING)

    @property
    def available(self):
        return self.balance - self.reserve

    def day(self, now):
        day = now.astimezone(TRADING_ZONE).date().isoformat()
        return self.data["days"].setdefault(day, {"start": str(self.balance), "stopped": False})

    def apply_daily_stop(self, now):
        day = self.day(now)
        start = Decimal(day["start"])
        if self.balance <= start * (ONE - DAILY_LOSS_RATE):
            day["stopped"] = True
        return day

    def buy(self, market, side, price, bid, size, multiplier, now):
        ticker = market["ticker"]
        if (ticker in self.trades or side not in {"yes", "no"}
                or not 0 < bid <= price < ONE or size < ONE or multiplier < ZERO):
            return None

        day = self.apply_daily_stop(now)
        if day["stopped"]:
            return None
        daily_floor = Decimal(day["start"]) * (ONE - DAILY_LOSS_RATE)
        budget = min(self.available * TRADE_RATE,
                     self.available * EXPOSURE_RATE - self.exposure,
                     self.cash - self.reserve,
                     self.cash - daily_floor)
        if budget < price:
            return None

        # Find the largest whole-contract fill that fits after its fee is charged.
        low, high = 0, int(min(size, budget / price))
        while low < high:
            quantity = (low + high + 1) // 2
            premium, fee = cost_at(price, quantity, multiplier)
            post_fee_balance = self.balance - fee
            reserve = (post_fee_balance * RESERVE_RATE).quantize(CENT, rounding=ROUND_CEILING)
            available = post_fee_balance - reserve
            if (premium + fee <= budget
                    and self.cash - premium - fee >= reserve
                    and self.exposure + premium + fee <= available * EXPOSURE_RATE):
                low = quantity
            else:
                high = quantity - 1
        if not low:
            return None

        premium, fee = cost_at(price, low, multiplier)
        trade = {
            "ticker": ticker,
            "category": market["category"],
            "side": side,
            "quantity": low,
            "entry_ask": str(price),
            "entry_bid": str(bid),
            "entry_spread": str(price - bid),
            "premium": str(premium),
            "fee": str(fee),
            "fee_multiplier": str(multiplier),
            "opened_at": now.isoformat(),
            "close_time": market["close_time"],
            "payout": None,
        }
        self.cash -= premium + fee
        self.trades[ticker] = trade
        self.apply_daily_stop(now)
        return trade

    def settle(self, market, now):
        trade = self.trades.get(market["ticker"])
        if (not trade or trade["payout"] is not None
                or market.get("status") not in {"finalized", "settled"}):
            return None
        result = market.get("result")
        if result in {"yes", "no"}:
            payout = Decimal(result == trade["side"]) * trade["quantity"]
        elif result in {"scalar", "void"}:
            value = number(market.get("settlement_value_dollars"))
            if value is None or not ZERO <= value <= ONE:
                return None
            payout = (value if trade["side"] == "yes" else ONE - value) * trade["quantity"]
        else:
            return None

        self.day(now)
        self.cash += payout
        trade.update(result=result, payout=str(payout), settled_at=now.isoformat(),
                     exchange_settlement_at=market.get("settlement_ts"),
                     net_pnl=str(payout - Decimal(trade["premium"]) - Decimal(trade["fee"])))
        self.apply_daily_stop(now)
        return trade

    def report(self, now):
        day = self.apply_daily_stop(now)
        settled = [Decimal(trade["net_pnl"]) for trade in self.trades.values()
                   if trade["payout"] is not None]
        wins = sum(amount > ZERO for amount in settled)
        losses = sum(amount < ZERO for amount in settled)
        win_rate = f"{wins / len(settled):.1%}" if settled else "—"
        fees = sum(Decimal(trade["fee"]) for trade in self.trades.values())
        start = Decimal(day["start"])
        day_net = self.balance - start
        floor = start * (ONE - DAILY_LOSS_RATE)
        return "\n".join([
            "## Kalshi paper trading",
            f"- Balance at cost: ${self.balance:,.2f} | Cash: ${self.cash:,.2f}",
            f"- Protected reserve: ${self.reserve:,.2f} | Available funds: ${self.available:,.2f}",
            f"- Per-trade cap: ${self.available * TRADE_RATE:,.2f} | "
            f"Open exposure: ${self.exposure:,.2f} / ${self.available * EXPOSURE_RATE:,.2f}",
            f"- Chicago day start: ${start:,.2f} | Day P/L: ${day_net:+,.2f} | "
            f"Daily loss limit: ${start * DAILY_LOSS_RATE:,.2f}",
            f"- Daily stop: {'triggered' if day['stopped'] else 'clear'} | "
            f"Remaining worst-case daily risk budget: ${max(ZERO, self.cash - floor):,.2f}",
            f"- Open: {len(self.positions)} | Settled: {len(settled)} | "
            f"Wins: {wins} | Losses: {losses} | Flat: {len(settled) - wins - losses} | "
            f"Win rate: {win_rate}",
            f"- Settled net P/L: ${sum(settled):+,.2f} | All fees: ${fees:,.2f} | "
            f"Account return: {(self.balance / STARTING_BALANCE - ONE):+.2%}",
        ]) + "\n"


@contextmanager
def locked_ledger(path):
    # SQLite provides an interprocess lock. The ledger itself is portable JSON.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path) + ".lock", timeout=1)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        ledger = Ledger(json.loads(path.read_text()) if path.exists() else None)
        yield ledger
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temp:
            pending = Path(temp.name)
            try:
                json.dump(ledger.data, temp, indent=2, allow_nan=False)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
                os.replace(pending, path)
            finally:
                pending.unlink(missing_ok=True)
