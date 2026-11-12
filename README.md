# Kalshi paper-trading bot

The bot uses Kalshi's public market data and a simulated $1,000 account. It needs Python 3.12 and uses only the standard library. It holds paper fills until Kalshi publishes a final outcome.

```sh
python Bot.py                         # scan, settle past fills, and simulate new fills
python Bot.py --scan-only             # scan without a ledger
python Bot.py --report-only           # show the local account report offline
python Bot.py --interval 60           # keep running on an always-on computer
python -m unittest discover -s tests -v
```

Local runs share `paper-state/ledger.json` by default. Use `--state` for a separate account and `--report` to write a Markdown report.

On GitHub, open **Actions → Kalshi Demo Bot → Run workflow** on **main**. The workflow runs the tests, restores the previous ledger from the `paper-ledger` branch, and publishes the new report in the run summary. The first successful manual run creates that branch. Pushes run the tests and a live scan without using the persistent paper account. GitHub runs on demand. Continuous operation uses the local `--interval` option.

## Risk and fill assumptions

- Balance is cash plus open contracts at their entry premium. Entry fees reduce it immediately. The bot protects 20% of the current balance in cash. The remaining 80%, rounded down to cents, sets the 3% per-fill and 10% aggregate open-exposure caps. Exposure includes entry premiums and fees.
- The daily loss limit is 10% of the start-of-day balance in America/Chicago. A new day uses the book balance before the first ledger activity. Settlements affect the day on which the bot processes them. The bot blocks any fill that would take worst-case equity below the daily floor and latches the stop for the day when book balance reaches the floor.
- The scan uses series metadata across all categories, explicitly checks BTC and ETH, and searches markets closing in the next 15 minutes for additional matches. Market duration and title provide fallbacks when a series lacks interval metadata.
- The baseline strategy selects the side with a 55–75¢ midpoint and a spread no wider than 4¢. It refreshes the order book before simulating a whole-contract buy at the best ask, limited by displayed size and risk. It skips fills in the last 45 seconds. This quote-based rule is a baseline for testing.
- Estimated taker fees use Kalshi's quadratic rate and the published series or event multiplier, rounded up to a cent. The ledger records the spread, fees, final payout and net P/L. Reports show book-value return, daily P/L, exposure and settled outcomes.

[Kalshi market API](https://docs.kalshi.com/api-reference/market/get-markets) · [Kalshi fees](https://kalshi.com/fee-schedule)
