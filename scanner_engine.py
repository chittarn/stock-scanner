#!/usr/bin/env python3
"""
SCANNER ENGINE – The logic behind the Adaptive Momentum Strategy.
Separated from the UI to support both CLI and Mobile apps.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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
        defaults = {
            "universe": ["QQQ", "NVDA", "AMZN", "CAT", "BRK-B", "XLF", "JPM", "XLV", "LLY", "XLE", "WMT", "LMT", "GLD"],
            "initial_capital": 300.0,
            "ma_period": 200,
            "atr_period": 14,
            "atr_mult": 2.5,
            "max_positions_bull": 3,
            "max_positions_volatile": 2,
            "momentum_min_return": 5.0,
            "min_score": 0.0,
            "regime_confirmation_days": 10,
            "max_sector_positions": 1,
            "max_position_pct": 0.33,
            "risk_per_trade_pct": 0.02,
            "my_holdings": {}
        }

        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            for key, value in defaults.items():
                self.config.setdefault(key, value)
        else:
            self.config = defaults

    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def update_holding(self, ticker, qty, avg_cost, entry_date=None):
        existing = self.config['my_holdings'].get(ticker, {})
        holding = {"qty": float(qty), "avg_cost": float(avg_cost)}
        # Preserve or set entry_date for trailing stop calculation
        if entry_date:
            holding["entry_date"] = entry_date
        elif 'entry_date' in existing:
            holding["entry_date"] = existing["entry_date"]
        else:
            holding["entry_date"] = datetime.now().strftime('%Y-%m-%d')
        self.config['my_holdings'][ticker] = holding
        self.save_config()

    def delete_holding(self, ticker):
        if ticker in self.config['my_holdings']:
            del self.config['my_holdings'][ticker]
            self.save_config()

    def fetch_data(self, end_date: datetime.date = None):
        holdings_symbols = list(self.config['my_holdings'].keys())
        symbols = list(set(self.config['universe'] + holdings_symbols + ['SPY']))
        # Determine download range
        if end_date is None:
            # Default: use max available data up to now
            data = yf.download(symbols, period="max", auto_adjust=True, progress=False, threads=False)
        else:
            # Fetch one year of history ending at the specified date
            start_dt = end_date - timedelta(days=365)
            # yfinance expects strings in YYYY-MM-DD format
            start_str = start_dt.strftime('%Y-%m-%d')
            end_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
            data = yf.download(symbols, start=start_str, end=end_str, auto_adjust=True, progress=False, threads=False)
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

    def get_target_allocation(self, ticker, price, atr_value, target_total, regime="BULL"):
        if price <= 0 or atr_value <= 0 or target_total <= 0:
            return 0.0

        risk_pct = float(self.config.get('risk_per_trade_pct', 0.02))
        if regime == "VOLATILE":
            risk_pct *= 0.75
        elif regime == "BEAR":
            risk_pct *= 0.50

        risk_amount = risk_pct * target_total
        stop_distance = float(self.config.get('atr_mult', 2.5)) * atr_value
        if stop_distance <= 0:
            return 0.0

        max_shares_by_risk = risk_amount / stop_distance
        max_amount_by_risk = max_shares_by_risk * price
        max_amount_by_pct = float(self.config.get('max_position_pct', 0.33)) * target_total
        return min(max_amount_by_risk, max_amount_by_pct)

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
        spy_ma50 = valid_spy.rolling(window=min(50, len(valid_spy))).mean().iloc[-1] if len(valid_spy) > 0 else 0.0

        if spy_ma == 0:
            return "BULL", spy_price, 0.0, 0.0

        dist_pct = (spy_price / spy_ma - 1) * 100
        regime = "BULL"

        ma_series = valid_spy.rolling(window=ma_period).mean()
        confirm_days = min(self.config['regime_confirmation_days'], len(valid_spy))
        if spy_price < spy_ma:
            if confirm_days > 1:
                recent_below_ma = valid_spy.tail(confirm_days) < ma_series.tail(confirm_days)
                regime = "BEAR" if recent_below_ma.all() else "VOLATILE"
            else:
                regime = "VOLATILE"
        else:
            if confirm_days > 1:
                recent_above_ma = valid_spy.tail(confirm_days) > ma_series.tail(confirm_days)
                if not recent_above_ma.all() or spy_price < spy_ma50:
                    regime = "VOLATILE"
            elif spy_price < spy_ma50:
                regime = "VOLATILE"

        if atr is not None and 'SPY' in atr.columns:
            spy_atr = atr['SPY'].dropna()
            if len(spy_atr) > 20:
                recent_atr = spy_atr.iloc[-1]
                avg_atr = spy_atr.tail(20).mean()
                if recent_atr > avg_atr * 1.5 and regime == "BULL":
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
                p3m = valid_prices.iloc[-min(63, len(valid_prices) - 1)]
                p6m = valid_prices.iloc[-min(126, len(valid_prices) - 1)]

                ret3m = (curr / p3m - 1) * 100 if p3m > 0 else 0
                ret6m = (curr / p6m - 1) * 100 if p6m > 0 else 0

                returns = valid_prices.tail(60).pct_change().dropna()
                vol = returns.std() * np.sqrt(252) if not returns.empty else 0.01
                vol = max(vol, 0.01)

                raw_score = (ret6m * w6) + (ret3m * w3)
                score = raw_score / vol

                ma_len = min(200, len(valid_prices))
                ma200 = valid_prices.rolling(window=ma_len).mean().iloc[-1]
                above_ma200 = curr > ma200
                momentum_ok = ret3m >= self.config['momentum_min_return'] and ret6m >= self.config['momentum_min_return']

                scores[t] = {
                    'score': score,
                    'price': curr,
                    'ret3m': ret3m,
                    'ret6m': ret6m,
                    'momentum_ok': momentum_ok,
                    'above_ma200': above_ma200,
                    'ma200': ma200,
                    'sector': sectors.get(t, "Other")
                }
        return scores

    def get_analysis(self, end_date: datetime.date = None):
        """Run the full scanner analysis for a specific market date.
        If end_date is provided, the engine will fetch data up to that date to avoid look‑ahead bias.
        """
        prices, high, low = self.fetch_data(end_date=end_date)
        atr = self.calculate_atr(prices, high, low, self.config['atr_period'])
        regime, spy_price, spy_ma, dist = self.get_market_regime(prices, atr)
        scores = self.get_momentum_scores(prices)
        timestamp = datetime.now(self.ist).strftime('%Y-%m-%d %I:%M %p IST')
        
        # Sort tickers by score (descending)
        sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)

        n_target = 0
        if regime == "BULL":
            n_target = self.config['max_positions_bull']
        elif regime == "VOLATILE":
            n_target = self.config['max_positions_volatile']

        eligible_candidates = [
            t for t, d in sorted_ranks
            if d['above_ma200'] and d['momentum_ok'] and d['score'] >= self.config['min_score']
        ]
        top_targets = []
        used_sectors = set()
        max_sector_positions = max(1, int(self.config.get('max_sector_positions', 1)))
        sector_counts = {}
        for t in eligible_candidates:
            sector = scores[t]['sector']
            sector_counts[sector] = sector_counts.get(sector, 0)
            if sector_counts[sector] >= max_sector_positions:
                continue
            top_targets.append(t)
            sector_counts[sector] += 1
            used_sectors.add(sector)
            if len(top_targets) >= n_target:
                break

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
        keepable_holdings = []

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

            curr_atr = atr[t].iloc[-1] if t in atr.columns else 0.0
            current_atr_mult = self.config['atr_mult']
            is_profit_protected = False
            if pnl_pct > 15.0:
                current_atr_mult = 1.5
                is_profit_protected = True

            entry_date_str = h.get('entry_date')
            if entry_date_str and t in prices.columns:
                try:
                    entry_dt = pd.to_datetime(entry_date_str)
                    prices_since_entry = prices[t].loc[entry_dt:].dropna()
                    recent_high = prices_since_entry.max() if len(prices_since_entry) > 0 else curr_price
                except (ValueError, KeyError, TypeError):
                    recent_high = prices[t].dropna().tail(252).max() if (t in prices.columns) else curr_price
            else:
                recent_high = prices[t].dropna().tail(252).max() if (t in prices.columns) else curr_price

            highest_price = max(recent_high, h['avg_cost'])
            stop_price = highest_price - (current_atr_mult * curr_atr)
            atr_stop_dist = ((curr_price - stop_price) / curr_price) * 100 if curr_price > 0 else 0.0

            status = "KEEP"
            reason = ""

            below_200 = False
            weak_momentum = False
            if t in scores:
                below_200 = not scores[t]['above_ma200']
                weak_momentum = not scores[t]['momentum_ok']

            if regime == "BEAR":
                status = "SELL"
                reason = "Bear Market"
            elif curr_price < stop_price:
                status = "STOP"
                reason = f"{'Profit Protection' if is_profit_protected else 'Stop Loss'} (ATR Break)"
            elif below_200 or weak_momentum:
                status = "EXIT"
                reason = "Trend Weakness"
            else:
                keepable_holdings.append({'ticker': t, 'value': val})

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

        stopped_tickers = {item['ticker'] for item in portfolio_items if item['status'] in ["SELL", "STOP", "EXIT"]}
        buy_orders = []
        hold_orders = []

        if regime != "BEAR" and n_target > 0:
            target_total = max(total_value, self.config['initial_capital'])
            active_candidates = [t for t in top_targets if t not in stopped_tickers]

            target_amounts = {}
            for ticker in active_candidates:
                curr_price = scores.get(ticker, {}).get('price', 0.0)
                if curr_price == 0.0 and ticker in prices.columns and len(prices[ticker].dropna()) > 0:
                    curr_price = prices[ticker].dropna().iloc[-1]

                curr_atr = atr[ticker].iloc[-1] if ticker in atr.columns else 0.0
                target_amounts[ticker] = self.get_target_allocation(ticker, curr_price, curr_atr, target_total, regime)

            total_target_amount = sum(target_amounts.values())
            if total_target_amount > 0 and total_target_amount > target_total:
                scale = target_total / total_target_amount
                for ticker in target_amounts:
                    target_amounts[ticker] *= scale

            # If current holdings are not among the active targets, sell them to fund new allocations
            for ticker, h in self.config['my_holdings'].items():
                if ticker not in active_candidates and ticker not in stopped_tickers:
                    curr_price = scores.get(ticker, {}).get('price', 0.0)
                    if curr_price == 0.0 and ticker in prices.columns and len(prices[ticker].dropna()) > 0:
                        curr_price = prices[ticker].dropna().iloc[-1]
                    if h['qty'] > 0:
                        to_sell.append({
                            'ticker': ticker,
                            'qty': h['qty'],
                            'reason': 'Rebalance: not a top target'
                        })

            for ticker in active_candidates:
                desired_amount = target_amounts.get(ticker, 0.0)
                if desired_amount <= 0:
                    continue

                curr_price = scores.get(ticker, {}).get('price', 0.0)
                if curr_price == 0.0 and ticker in prices.columns and len(prices[ticker].dropna()) > 0:
                    curr_price = prices[ticker].dropna().iloc[-1]

                is_held = self.config['my_holdings'].get(ticker, {}).get('qty', 0) > 0
                curr_val = self.config['my_holdings'].get(ticker, {}).get('qty', 0) * curr_price if is_held else 0.0
                diff = desired_amount - curr_val

                if not is_held and desired_amount > 0:
                    buy_orders.append({
                        'ticker': ticker,
                        'type': 'NEW',
                        'amount': desired_amount,
                        'shares': desired_amount / curr_price if curr_price > 0 else 0.0,
                        'price': curr_price
                    })
                elif is_held and diff > max(5.0, desired_amount * 0.10):
                    buy_orders.append({
                        'ticker': ticker,
                        'type': 'ADD',
                        'amount': diff,
                        'shares': diff / curr_price if curr_price > 0 else 0.0,
                        'price': curr_price
                    })
                elif is_held and diff < -max(5.0, curr_val * 0.10):
                    sell_qty = -diff / curr_price if curr_price > 0 else 0.0
                    to_sell.append({
                        'ticker': ticker,
                        'qty': sell_qty,
                        'reason': 'Rebalance: reduce position to fund new target'
                    })
                elif is_held and ticker not in stopped_tickers:
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
            "timestamp": timestamp
        }
