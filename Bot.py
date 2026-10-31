

# KALSHI AI DEMO BOT
# Paper trading only - no real money trades

STARTING_BALANCE = 1000.00
MAX_RISK_PER_TRADE = 10.00
DAILY_STOP_LOSS = 100.00

balance = STARTING_BALANCE
daily_profit_loss = 0.00
trades = 0

def show_dashboard():
    print("===== KALSHI AI DEMO BOT =====")
    print(f"Starting balance: ${STARTING_BALANCE:.2f}")
    print(f"Current balance:  ${balance:.2f}")
    print(f"Daily P/L:        ${daily_profit_loss:.2f}")
    print(f"Trades:           {trades}")
    print("==============================")

def can_trade(risk):
    if daily_profit_loss <= -DAILY_STOP_LOSS:
        print("STOP: Daily loss limit reached.")
        return False

    if risk > MAX_RISK_PER_TRADE:
        print("STOP: Risk exceeds $10 per trade.")
        return False

    if risk <= 0:
        print("Invalid trade risk.")
        return False

    return True

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

if __name__ == "__main__":
    show_dashboard()
    print("Bot ready for demo trading.")
    print("No real orders will be placed.")
