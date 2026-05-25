#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

UNIVERSE = ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"]
MA_PERIOD = 200
ATR_PERIOD = 14
ATR_MULT = 2.5
FX_FEE = 0.003
MIN_TRADE = 5.0
W6 = 0.6
W3 = 0.4

class ComparativeBacktest:
    def __init__(self, start_date, sort_by='score'):
        self.start = start_date
        buffer_start = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=300)
        self.data_start = buffer_start.strftime('%Y-%m-%d')
        self.data_end = datetime.now().strftime('%Y-%m-%d')
        self.display_start = pd.to_datetime(start_date)
        self.sort_by = sort_by
        
        self.capital = 300.0
        self.cash = 300.0
        self.holdings = {}
        self.trades = []
        self.history = []

    def fetch_data(self):
        symbols = UNIVERSE + ['SPY']
        data = yf.download(symbols, start=self.data_start, end=self.data_end, auto_adjust=True, progress=False)
        self.prices = data['Close'].ffill()
        self.high = data['High'].ffill()
        self.low = data['Low'].ffill()
        self.spy_ma = self.prices['SPY'].rolling(window=MA_PERIOD).mean()
        self.mas = self.prices.rolling(window=MA_PERIOD).mean()

    def get_regime(self, date):
        spy_price = self.prices['SPY'].loc[date]
        ma = self.spy_ma.loc[date]
        if pd.isna(ma): return 'BULL'
        dist = (spy_price / ma - 1) * 100
        if dist < -5: return 'BEAR'
        elif dist < 0: return 'VOLATILE'
        return 'BULL'

    def get_rankings(self, date):
        idx = self.prices.index.get_loc(date)
        p3m_idx = max(0, idx - 63)
        p6m_idx = max(0, idx - 126)
        
        scores = {}
        for t in UNIVERSE:
            if t in self.prices.columns:
                curr = self.prices[t].loc[date]
                p3m = self.prices[t].iloc[p3m_idx]
                p6m = self.prices[t].iloc[p6m_idx]
                
                ret3m = (curr / p3m - 1) * 100 if p3m > 0 else 0
                ret6m = (curr / p6m - 1) * 100 if p6m > 0 else 0
                score = (ret6m * W6) + (ret3m * W3)
                
                ma = self.mas[t].loc[date]
                above_ma = curr > ma if not pd.isna(ma) else True
                
                # conviction
                conviction = score * 1.2 if above_ma else score * 0.5
                
                scores[t] = {'score': score, 'above_ma': above_ma, 'conviction': conviction}
        
        if self.sort_by == 'conviction':
            sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['conviction'], reverse=True)
        else:
            sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
            
        return sorted_ranks

    def portfolio_value(self, date):
        val = self.cash
        for t, h in self.holdings.items():
            val += h['shares'] * self.prices[t].loc[date]
        return val

    def sell(self, date, ticker, reason):
        if ticker not in self.holdings: return
        price = self.prices[ticker].loc[date]
        shares = self.holdings[ticker]['shares']
        gross = shares * price
        fee = gross * FX_FEE
        net = gross - fee
        cost = self.holdings[ticker]['cost']
        pnl = net - (shares * cost)
        
        self.cash += net
        del self.holdings[ticker]
        self.trades.append({
            'date': date, 'action': 'SELL', 'ticker': ticker, 'pnl': pnl,
            'pnl_pct': (net / (shares * cost) - 1) * 100 if cost > 0 else 0,
            'reason': reason
        })

    def buy(self, date, ticker, amount):
        if amount < MIN_TRADE: return
        price = self.prices[ticker].loc[date]
        fee = amount * FX_FEE
        net = amount - fee
        shares = net / price
        
        if ticker not in self.holdings:
            self.holdings[ticker] = {'shares': 0.0, 'cost': 0.0}
        
        h = self.holdings[ticker]
        total_shares = h['shares'] + shares
        h['cost'] = ((h['shares'] * h['cost']) + (shares * price)) / total_shares if total_shares > 0 else price
        h['shares'] = total_shares
        self.cash -= amount

    def rebalance(self, date):
        regime = self.get_regime(date)
        if regime == 'BEAR':
            for t in list(self.holdings.keys()):
                self.sell(date, t, 'BEAR_MARKET')
            return

        n_target = 2 if regime == 'BULL' else 1
        rankings = self.get_rankings(date)
        top_2 = [r[0] for r in rankings[:2]]
        top_4 = [r[0] for r in rankings[:4]]
        
        # 1. Stop Loss Check
        for t in list(self.holdings.keys()):
            price = self.prices[t].loc[date]
            cost = self.holdings[t]['cost']
            if (price / cost - 1) < -0.10: 
                self.sell(date, t, 'STOP_LOSS')

        # 2. Hysteresis Sell
        for t in list(self.holdings.keys()):
            if t not in top_4:
                self.sell(date, t, 'RANK_EXIT')
            else:
                ma = self.mas[t].loc[date]
                if self.prices[t].loc[date] < ma:
                    self.sell(date, t, 'BELOW_SMA')

        # 3. New Buys
        total_val = self.portfolio_value(date)
        target_per_stock = total_val / n_target
        
        for i, (t, d) in enumerate(rankings[:n_target]):
            if d['above_ma']:
                curr_shares = self.holdings.get(t, {}).get('shares', 0)
                curr_val = curr_shares * self.prices[t].loc[date]
                diff = target_per_stock - curr_val
                if diff > MIN_TRADE:
                    self.buy(date, t, diff)

    def run(self):
        self.fetch_data()
        dates = self.prices.index
        fridays = dates[dates.dayofweek == 4]
        
        for date in dates:
            val = self.portfolio_value(date)
            if date >= self.display_start:
                self.history.append({'date': date, 'portfolio': val})
            if date in fridays and date >= self.display_start:
                self.rebalance(date)
        
        return self.history[-1]['portfolio']

print("Running Backtest comparison...")
start_dt = '2022-01-01'

bt_score = ComparativeBacktest(start_dt, sort_by='score')
final_score = bt_score.run()

bt_conv = ComparativeBacktest(start_dt, sort_by='conviction')
final_conv = bt_conv.run()

print(f"Final Value sorted by Score: ${final_score:.2f} (Total Return: {((final_score/300.0)-1)*100:.1f}%)")
print(f"Final Value sorted by Conviction: ${final_conv:.2f} (Total Return: {((final_conv/300.0)-1)*100:.1f}%)")
