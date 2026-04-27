#!/usr/bin/env python3
"""
SCANNER ENGINE – The logic behind the Adaptive Momentum Strategy.
Separated from the UI to support both CLI and Mobile apps.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import json
import os

class ScannerEngine:
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
                "universe": ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"],
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

    def fetch_data(self):
        symbols = self.config['universe'] + ['SPY']
        data = yf.download(symbols, period="1y", auto_adjust=True, progress=False)
        return data['Close'].ffill(), data['High'].ffill(), data['Low'].ffill()

    def calculate_atr(self, close, high, low, period=14):
        tr = pd.DataFrame(index=close.index)
        for t in self.config['universe']:
            if t in close.columns:
                h_l = high[t] - low[t]
                h_pc = abs(high[t] - close[t].shift(1))
                l_pc = abs(low[t] - close[t].shift(1))
                tr[t] = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    def get_market_regime(self, prices):
        spy_price = prices['SPY'].iloc[-1]
        spy_ma = prices['SPY'].rolling(window=self.config['ma_period']).mean().iloc[-1]
        
        if pd.isna(spy_ma):
            return "BULL", spy_price, 0.0, 0.0
            
        dist_pct = (spy_price / spy_ma - 1) * 100
        
        if dist_pct < -5:
            regime = "BEAR"
        elif dist_pct < 0:
            regime = "VOLATILE"
        else:
            regime = "BULL"
            
        return regime, spy_price, spy_ma, dist_pct

    def get_momentum_scores(self, prices):
        w6, w3 = 0.6, 0.4
        sectors = {
            "NVDA": "Semiconductors", "SMH": "Semiconductors", "QQQ": "Index (Tech)",
            "CAT": "Industrials", "XLE": "Energy", "GLD": "Gold", "MSFT": "Software"
        }
        
        scores = {}
        for t in self.config['universe']:
            if t in prices.columns:
                curr = prices[t].iloc[-1]
                p3m = prices[t].iloc[-min(63, len(prices)-1)]
                p6m = prices[t].iloc[-min(126, len(prices)-1)]
                
                ret3m = (curr / p3m - 1) * 100 if p3m > 0 else 0
                ret6m = (curr / p6m - 1) * 100 if p6m > 0 else 0
                score = (ret6m * w6) + (ret3m * w3)
                
                ma200 = prices[t].rolling(window=200).mean().iloc[-1]
                above_ma200 = curr > ma200 if not pd.isna(ma200) else True
                conviction = score * 1.2 if above_ma200 else score * 0.5
                
                scores[t] = {
                    'score': score,
                    'price': curr,
                    'conviction': conviction,
                    'above_ma200': above_ma200,
                    'sector': sectors.get(t, "Other")
                }
        return scores

    def get_analysis(self):
        """Returns a consolidated dictionary of all analysis results."""
        prices, high, low = self.fetch_data()
        atr = self.calculate_atr(prices, high, low, self.config['atr_period'])
        regime, spy_price, spy_ma, dist = self.get_market_regime(prices)
        scores = self.get_momentum_scores(prices)
        
        return {
            "prices": prices,
            "atr": atr,
            "regime": regime,
            "spy_price": spy_price,
            "spy_ma": spy_ma,
            "dist": dist,
            "scores": scores,
            "timestamp": self.now.strftime('%Y-%m-%d %I:%M %p IST')
        }
