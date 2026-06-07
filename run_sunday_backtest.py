from backtest import backtest

# Run a dry backtest stepping on Sundays for the last 2 years
if __name__ == '__main__':
    # Customize these dates as needed
    start_date = '2024-06-01'
    end_date = '2026-06-06'
    starting_capital = 10000.0
    print(f"Running backtest {start_date} -> {end_date} (weekly Sundays)")
    backtest(start_date=start_date, end_date=end_date, starting_capital=starting_capital, freq='W-SUN')
