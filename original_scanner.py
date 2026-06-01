#!/usr/bin/env python3
"""
Original Momentum‑Only Scanner Engine – a baseline version without the adaptive SMA filter or regime fallback.
It mirrors the logic prior to the adaptive enhancements, providing a pure momentum signal.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import json
import os

class OriginalScannerEngine:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.load_config()
        self.ist = pytz.timezone('Asia/Kolkata')
        self.now = datetime.now(self.ist)

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        else:
            # Fallback defaults
            self.config = {
                "universe": ["QQQ", "NVDA", "AMZN", "CAT", "BRK-B", "XLF", "JPM", "XLV", "LLY", "XLE", "WMT", "LMT", "GLD"],
                "initial_capital": 300.0,
                "ma_period": 200,
                "atr_period": 14,
                "atr_mult": 2.5,
                "my_holdings": {}
            }

    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def update_holding(self, ticker, qty, avg_cost):
        self.config['my_holdings'][ticker] = {"qty": float(qty), "avg_cost": float(avg_cost)}
        self.save_config()

    def delete_holding(self, ticker):
        if ticker in self.config['my_holdings']:
            del self.config['my_holdings'][ticker]
            self.save_config()

    def fetch_data(self, end_date: datetime.date = None):
        holdings_symbols = list(self.config['my_holdings'].keys())
        symbols = list(set(self.config['universe'] + holdings_symbols + ['SPY']))
        if end_date is None:
            data = yf.download(symbols, period="max", auto_adjust=True, progress=False)
        else:
            start_dt = end_date - timedelta(days=365)
            start_str = start_dt.strftime('%Y-%m-%d')
            end_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
            data = yf.download(symbols, start=start_str, end=end_str, auto_adjust=True, progress=False)
        if data.empty:
            raise ValueError("No market data downloaded from yfinance.")
        close = data['Close'].ffill().bfill()
        high = data['High'].ffill().bfill()
        low = data['Low'].ffill().bfill()
        return close, high, low

    def calculate_atr(self, close, high, low, period=14):
        tr = pd.DataFrame(index=close.index)
        all_symbols = list(set(self.config['universe'] + list(self.config['my_holdings'].keys())))
        for t in all_symbols:
            if t in close.columns:
                h_l = high[t] - low[t]
                h_pc = abs(high[t] - close[t].shift(1))
                l_pc = abs(low[t] - close[t].shift(1))
                tr[t] = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().ffill().bfill()
        return atr

    def get_market_regime(self, prices, atr=None):
        # Simple regime based on SPY price vs its moving average (no fallback to VOLATILE)
        if 'SPY' not in prices.columns:
            return "BULL", 0.0, 0.0, 0.0
        valid_spy = prices['SPY'].dropna()
        ma_period = max(5, len(valid_spy)) if len(valid_spy) < self.config['ma_period'] else self.config['ma_period']
        spy_price = valid_spy.iloc[-1] if len(valid_spy) > 0 else 0.0
        spy_ma = valid_spy.rolling(window=ma_period).mean().iloc[-1] if len(valid_spy) > 0 else 0.0
        if spy_ma == 0:
            return "BULL", spy_price, 0.0, 0.0
        dist_pct = (spy_price / spy_ma - 1) * 100
        regime = "BULL" if spy_price >= spy_ma else "BEAR"
        return regime, spy_price, spy_ma, dist_pct

    def get_momentum_scores(self, prices):
        w6, w3 = 0.6, 0.4
        sectors = {
            "QQQ": "Index (Tech)", "NVDA": "Semiconductors", "AMZN": "Consumer Disc",
            "CAT": "Industrials", "BRK-B": "Financials", "XLF": "Financials",
            "JPM": "Financials", "XLV": "Healthcare", "LLY": "Healthcare",
            "XLE": "Energy", "WMT": "Consumer Staples", "LMT": "Defense",
            "GLD": "Gold", "MSFT": "Software", "GOOGL": "Communication", "AMD": "Semiconductors"
        }
        scores = {}
        for t in self.config['universe']:
            if t in prices.columns:
                valid_prices = prices[t].dropna()
                if len(valid_prices) < 10:
                    continue
                curr = valid_prices.iloc[-1]
                p3m = valid_prices.iloc[-min(63, len(valid_prices)-1)]
                p6m = valid_prices.iloc[-min(126, len(valid_prices)-1)]
                ret3m = (curr / p3m - 1) * 100 if p3m > 0 else 0
                ret6m = (curr / p6m - 1) * 100 if p6m > 0 else 0
                returns = valid_prices.tail(60).pct_change().dropna()
                vol = returns.std() * np.sqrt(252) if not returns.empty else 0.01
                vol = max(vol, 0.01)
                raw_score = (ret6m * w6) + (ret3m * w3)
                score = raw_score / vol
                scores[t] = {
                    'score': score,
                    'price': curr,
                    'sector': sectors.get(t, "Other")
                }
        return scores

    def get_analysis(self, end_date: datetime.date = None):
        """Run a full analysis for a specific market date (no SMA filter)."""
        prices, high, low = self.fetch_data(end_date=end_date)
        atr = self.calculate_atr(prices, high, low, self.config['atr_period'])
        regime, spy_price, spy_ma, dist = self.get_market_regime(prices, atr)
        scores = self.get_momentum_scores(prices)
        # Sort tickers by conviction (descending)
        sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
        n_target = 2 if regime == "BULL" else 1 if regime == "VOLATILE" else 0
        # Original version did NOT filter by 200‑day SMA, so all sorted tickers are eligible
        top_targets = [t for t, _ in sorted_ranks[:n_target]]
        return {
            "prices": prices,
            "atr": atr,
            "regime": regime,
            "spy_price": spy_price,
            "spy_ma": spy_ma,
            "dist": dist,
            "scores": scores,
            "sorted_ranks": sorted_ranks,
            "n_target": n_target,
            "top_targets": top_targets,
            "timestamp": self.now.strftime('%Y-%m-%d %I:%M %p IST')
        }

if __name__ == "__main__":
    # Example usage similar to the adaptive version
    engine = OriginalScannerEngine()
    # Run a sample analysis for today
    analysis = engine.get_analysis()
    print(f"Regime: {analysis['regime']}, top targets: {analysis['top_targets']}")
