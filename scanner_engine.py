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

    def fetch_data(self):
        holdings_symbols = list(self.config['my_holdings'].keys())
        symbols = list(set(self.config['universe'] + holdings_symbols + ['SPY']))
        data = yf.download(symbols, period="1y", auto_adjust=True, progress=False)
        if data.empty:
            raise ValueError("No market data downloaded from yfinance. Please check your internet connection.")
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
        if 'SPY' not in prices.columns:
            return "BULL", 0.0, 0.0, 0.0
            
        valid_spy = prices['SPY'].dropna()
        if len(valid_spy) < self.config['ma_period']:
            ma_period = max(5, len(valid_spy))
        else:
            ma_period = self.config['ma_period']
            
        spy_price = valid_spy.iloc[-1] if len(valid_spy) > 0 else 0.0
        spy_ma = valid_spy.rolling(window=ma_period).mean().iloc[-1] if len(valid_spy) > 0 else 0.0
        
        if spy_ma == 0:
            return "BULL", spy_price, 0.0, 0.0
            
        dist_pct = (spy_price / spy_ma - 1) * 100
        
        if dist_pct < -5:
            regime = "BEAR"
        elif dist_pct < 0:
            regime = "VOLATILE"
        else:
            regime = "BULL"
            
        # ATR Volatility check
        if atr is not None and 'SPY' in atr.columns:
            spy_atr = atr['SPY'].dropna()
            if len(spy_atr) > 20:
                recent_atr = spy_atr.iloc[-1]
                avg_atr = spy_atr.tail(20).mean()
                if recent_atr > avg_atr * 1.5:
                    regime = "VOLATILE"
            
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
                score = (ret6m * w6) + (ret3m * w3)
                
                ma_len = min(200, len(valid_prices))
                ma200 = valid_prices.rolling(window=ma_len).mean().iloc[-1]
                above_ma200 = curr > ma200
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
        """Returns a consolidated dictionary of all analysis results, including risk metrics and action plans."""
        prices, high, low = self.fetch_data()
        atr = self.calculate_atr(prices, high, low, self.config['atr_period'])
        regime, spy_price, spy_ma, dist = self.get_market_regime(prices, atr)
        scores = self.get_momentum_scores(prices)
        
        # Sort tickers by conviction (descending)
        sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['conviction'], reverse=True)
        
        # Determine number of targets based on regime
        n_target = 2 if regime == "BULL" else 1 if regime == "VOLATILE" else 0
        
        # Eligible candidates must be above 200 SMA
        eligible_candidates = [t for t, d in sorted_ranks if d['above_ma200']]
        top_targets = eligible_candidates[:n_target]
        
        # Correlation matrix (tail 60 days)
        returns = prices.pct_change().dropna()
        corr_matrix = returns.tail(60).corr()
        
        # Risk profile of top targets
        correlation = 0.0
        same_sector = False
        div_score = 100.0
        risk_tip = ""
        
        if len(top_targets) >= 2:
            t1, t2 = top_targets[0], top_targets[1]
            if t1 in corr_matrix.columns and t2 in corr_matrix.columns:
                correlation = float(corr_matrix.loc[t1, t2])
            same_sector = scores[t1]['sector'] == scores[t2]['sector']
            div_score = (1 - max(0, correlation)) * 100
            if same_sector:
                div_score *= 0.7
                
            if correlation > 0.7 or same_sector:
                # Find the next eligible ticker that is NOT in the top targets
                alternatives = [t for t in eligible_candidates if t not in top_targets]
                if alternatives:
                    alt_ticker = alternatives[0]
                    risk_tip = f"{t1} and {t2} are moving together (Correlation: {correlation:.2f}) and/or have sector overlap. If you want more safety, buy {alt_ticker} instead of {t2}."
        
        # Build portfolio items and analyze holds
        portfolio_items = []
        total_value = 0.0
        total_cost = 0.0
        to_sell = []
        
        for t, h in self.config['my_holdings'].items():
            if h['qty'] <= 0:
                continue
                
            curr_price = scores.get(t, {}).get('price')
            if curr_price is None or pd.isna(curr_price):
                curr_price = prices[t].dropna().iloc[-1] if (t in prices.columns and len(prices[t].dropna()) > 0) else h['avg_cost']
                
            val = h['qty'] * curr_price
            cost = h['qty'] * h['avg_cost']
            total_value += val
            total_cost += cost
            pnl_pct = (curr_price / h['avg_cost'] - 1) * 100
            
            # ATR Stop & Profit Protection
            curr_atr = atr[t].iloc[-1] if t in atr.columns else 0.0
            
            current_atr_mult = self.config['atr_mult']
            is_profit_protected = False
            
            if pnl_pct > 15.0:
                current_atr_mult = 1.5
                is_profit_protected = True
                
            stop_price = h['avg_cost'] - (current_atr_mult * curr_atr)
            
            if is_profit_protected:
                recent_high = prices[t].dropna().tail(20).max() if (t in prices.columns) else curr_price
                stop_price = max(stop_price, recent_high - (current_atr_mult * curr_atr))
                
            atr_stop_dist = ((curr_price - stop_price) / curr_price) * 100 if curr_price > 0 else 0.0
            
            status = "KEEP"
            reason = ""
            
            if regime == "BEAR":
                status = "SELL"
                reason = "Bear Market"
            elif curr_price < stop_price:
                status = "STOP"
                reason = f"{'Profit Protection' if is_profit_protected else 'Stop Loss'} (ATR Break)"
            elif t not in top_targets:
                status = "EXIT"
                reason = f"Out of Top {n_target}"
            elif t in scores and not scores[t]['above_ma200']:
                status = "EXIT"
                reason = "Below 200 SMA"
                
            if status in ["SELL", "EXIT", "STOP"]:
                to_sell.append({
                    'ticker': t,
                    'qty': h['qty'],
                    'reason': reason
                })
                
            portfolio_items.append({
                'ticker': t,
                'value': val,
                'cost': cost,
                'pnl_pct': pnl_pct,
                'atr_stop_dist': atr_stop_dist,
                'status': status,
                'reason': reason
            })
            
        # Build action plan orders
        buy_orders = []
        hold_orders = []
        
        if regime != "BEAR" and n_target > 0:
            target_total = max(total_value, self.config['initial_capital'])
            target_per_stock = target_total / n_target
            
            for ticker in top_targets:
                is_held = self.config['my_holdings'].get(ticker, {}).get('qty', 0) > 0
                curr_price = scores.get(ticker, {}).get('price', 0.0)
                if curr_price == 0.0:
                    curr_price = prices[ticker].dropna().iloc[-1] if (ticker in prices.columns and len(prices[ticker].dropna()) > 0) else 0.0
                
                curr_val = self.config['my_holdings'].get(ticker, {}).get('qty', 0) * curr_price if is_held else 0.0
                diff = target_per_stock - curr_val
                
                if not is_held:
                    buy_orders.append({
                        'ticker': ticker,
                        'type': 'NEW',
                        'amount': target_per_stock,
                        'shares': target_per_stock / curr_price if curr_price > 0 else 0.0,
                        'price': curr_price
                    })
                elif diff > max(5.0, target_per_stock * 0.10):
                    buy_orders.append({
                        'ticker': ticker,
                        'type': 'ADD',
                        'amount': diff,
                        'shares': diff / curr_price if curr_price > 0 else 0.0,
                        'price': curr_price
                    })
                else:
                    hold_orders.append({
                        'ticker': ticker,
                        'value': curr_val
                    })
                    
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
            "eligible_candidates": eligible_candidates,
            "correlation_matrix": corr_matrix,
            "top_correlation": correlation,
            "same_sector": same_sector,
            "diversification_score": div_score,
            "risk_tip": risk_tip,
            "portfolio_items": portfolio_items,
            "total_value": total_value,
            "total_cost": total_cost,
            "to_sell": to_sell,
            "buy_orders": buy_orders,
            "hold_orders": hold_orders,
            "timestamp": self.now.strftime('%Y-%m-%d %I:%M %p IST')
        }
