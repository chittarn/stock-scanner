# Stock Scanner (Adaptive Momentum)

A compact adaptive momentum scanner and backtesting toolkit.

## Overview
- Scanner logic in `scanner_engine.py`.
- Console CLI in `adaptive_scanner.py` (subcommands: `scan`, `holdings`, `add-holding`, `remove-holding`, `config`, `web`).
- Web UI via Streamlit: `streamlit_app.py`.
- Config in `config.json`.

## Requirements
- Python 3.10+
- See `requirements.txt` (recommended to use a venv).

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Usage

CLI scan (force run any day):

```bash
python3 adaptive_scanner.py scan --force
```

Save JSON output:

```bash
python3 adaptive_scanner.py scan --json --output scan.json
```

Show holdings:

```bash
python3 adaptive_scanner.py holdings
```

Add holding:

```bash
python3 adaptive_scanner.py add-holding TICKER QTY AVG_COST --entry-date YYYY-MM-DD
```

Run web UI (Streamlit):

```bash
streamlit run streamlit_app.py
```

## Config
- Modify `config.json` for universe, risk settings, and `my_holdings`.
- `initial_capital`, `max_positions_bull`, `risk_per_trade_pct`, and `atr_mult` control sizing and stops.

## Development notes
- `scanner_engine.py` does data fetch via `yfinance` and computes ATR, momentum scores, and generates buy/sell/hold recommendations.
- Tests are minimal — run `python3 -m py_compile adaptive_scanner.py` to verify syntax quickly.

## Suggested cleanup (proposed)
The following files look like artifacts or legacy items; confirm if you want them removed:

- `original_scanner.py`  (older CLI)
- `run_scanner.bat`      (Windows batch file)
- `output.txt`          (log/artifact)
- `backtest_results.json`
- `weekly_trade_logs.json`
- `scratch/` directory (contains helper scripts)

If you confirm, I'll remove those files, commit, and push to `https://github.com/chittarn/stock-scanner.git`.

## License
Add your preferred license file if needed.
