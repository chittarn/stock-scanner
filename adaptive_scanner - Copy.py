#!/usr/bin/env python3
"""
ADAPTIVE MOMENTUM SCANNER – Crystal Clear Buy/Sell Signals
- Bull: Top 2 stocks (50% each)
- Volatile: Top 1 stock (100%)
- Bear: 100% Cash
- Always 7% stop loss
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# ==========================================================
# 🔧 USER CONFIGURATION – UPDATE THIS SECTION
# ==========================================================

UNIVERSE = ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"]
STOP_LOSS_PCT = 7.0
MOMENTUM_WINDOW = 63
MA_PERIOD = 200

# 👇 UPDATE YOUR HOLDINGS HERE 👇
# Format: "TICKER": {"qty": shares, "avg_cost": purchase_price}
MY_HOLDINGS = {
    "NVDA": {"qty": 0.7596353, "avg_cost": 162.35},
    "MSFT": {"qty": 0.0,      "avg_cost": 0.0},
    "QQQ":  {"qty": 0.06518589, "avg_cost": 613.63},
    "AMZN": {"qty": 0.0, "avg_cost": 0.0},
    "SMH":  {"qty": 0.04550342, "avg_cost": 439.53},
    "CAT":  {"qty": 0.14455407, "avg_cost": 818.59},
    "XLE":  {"qty": 0.0,      "avg_cost": 0.0},
}

# ==========================================================
# ⚙️ CORE LOGIC (DO NOT MODIFY)
# ==========================================================

def fetch_data():
    print("📥 Fetching market data...")
    data = yf.download(UNIVERSE + ['SPY'], period="8mo", auto_adjust=True, progress=False)
    return data['Close'].ffill()

def get_market_regime(prices):
    spy_price = prices['SPY'].iloc[-1]
    spy_ma = prices['SPY'].rolling(window=MA_PERIOD).mean().iloc[-1]
    if pd.isna(spy_ma):
        return "BULL", spy_price, spy_ma, 0.0
    dist_pct = (spy_price / spy_ma - 1) * 100
    if dist_pct < -5:
        return "BEAR", spy_price, spy_ma, dist_pct
    elif dist_pct < 0:
        return "VOLATILE", spy_price, spy_ma, dist_pct
    else:
        return "BULL", spy_price, spy_ma, dist_pct

def get_top_stocks(prices, n):
    spy_ret = (prices['SPY'].iloc[-1] / prices['SPY'].iloc[-MOMENTUM_WINDOW] - 1) * 100
    alphas = {}
    for t in UNIVERSE:
        if t in prices.columns:
            curr = prices[t].iloc[-1]
            past = prices[t].iloc[-min(MOMENTUM_WINDOW, len(prices)-1)]
            ret_3m = (curr / past - 1) * 100 if past > 0 else 0
            alphas[t] = {'alpha': ret_3m - spy_ret, 'price': curr}
    sorted_tickers = sorted(alphas.items(), key=lambda x: x[1]['alpha'], reverse=True)
    return [t for t, _ in sorted_tickers[:n]], alphas

def main():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    print("\n" + "="*80)
    print("🔄 ADAPTIVE MOMENTUM SCANNER – YOUR WEEKLY ACTION PLAN")
    print("="*80)
    print(f"📅 {now.strftime('%Y-%m-%d %I:%M %p IST')}")
    
    prices = fetch_data()
    regime, spy_price, spy_ma, dist = get_market_regime(prices)
    
    # --- MARKET REGIME ---
    print("\n" + "-"*80)
    print("📊 MARKET REGIME")
    print("-"*80)
    print(f" SPY Price:        ${spy_price:.2f}")
    print(f" SPY 200‑day MA:   ${spy_ma:.2f}")
    print(f" Distance from MA: {dist:+.1f}%")
    
    if regime == "BULL":
        print("\n 🟢 BULL MARKET – Hold TOP 2 stocks (diversified)")
        n_target = 2
    elif regime == "VOLATILE":
        print("\n 🟡 VOLATILE MARKET – Hold TOP 1 stock (concentrated)")
        n_target = 1
    else:
        print("\n 🔴 BEAR MARKET – 100% CASH (sell everything)")
        n_target = 0
    
    # --- TOP STOCKS ---
    top_tickers = []
    alphas = {}
    if n_target > 0:
        top_tickers, alphas = get_top_stocks(prices, n_target)
        print("\n" + "-"*80)
        print(f"📈 TOP {n_target} STOCKS BY 3‑MONTH ALPHA")
        print("-"*80)
        for i, t in enumerate(top_tickers, 1):
            a = alphas[t]['alpha']
            p = alphas[t]['price']
            print(f" {'🥇' if i==1 else '🥈'} {t:<6} Alpha {a:>+6.1f}%  |  Price ${p:.2f}")
    
    # --- FULL RANKINGS (for context) ---
    if n_target > 0:
        print("\n" + "-"*80)
        print("📋 FULL MOMENTUM RANKINGS (for reference)")
        print("-"*80)
        all_sorted = sorted(alphas.items(), key=lambda x: x[1]['alpha'], reverse=True)
        for i, (t, d) in enumerate(all_sorted, 1):
            owned = "📦" if MY_HOLDINGS.get(t, {}).get('qty', 0) > 0 else "  "
            color = "\033[92m" if d['alpha'] > 0 else "\033[91m"
            print(f" {i:2}. {t:<6} {owned} {color}{d['alpha']:>+6.1f}%\033[0m  ${d['price']:.2f}")
    
    # --- CURRENT PORTFOLIO VALUATION ---
    print("\n" + "-"*80)
    print("💼 YOUR CURRENT PORTFOLIO")
    print("-"*80)
    print(f"{'Ticker':<8} {'Shares':>10} {'Avg Cost':>10} {'Current':>10} {'Value':>12} {'P&L':>10} {'P&L%':>8}")
    print("-"*80)
    
    total_value = 0.0
    total_cost = 0.0
    positions = []
    for t, h in MY_HOLDINGS.items():
        if h['qty'] > 0 and t in prices.columns:
            price = prices[t].iloc[-1]
            val = h['qty'] * price
            cost = h['qty'] * h['avg_cost']
            pnl = val - cost
            pnl_pct = (price / h['avg_cost'] - 1) * 100
            total_value += val
            total_cost += cost
            positions.append({'ticker': t, 'qty': h['qty'], 'price': price, 'val': val,
                              'cost': cost, 'pnl': pnl, 'pnl_pct': pnl_pct})
            color = "\033[92m" if pnl >= 0 else "\033[91m"
            print(f" {t:<8} {h['qty']:>10.4f} ${h['avg_cost']:>9.2f} ${price:>9.2f} ${val:>11.2f} {color}${pnl:>+9.2f}\033[0m {color}{pnl_pct:>+7.1f}%\033[0m")
    
    if total_cost > 0:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_value / total_cost - 1) * 100
        color = "\033[92m" if total_pnl >= 0 else "\033[91m"
        print("-"*80)
        print(f" {'TOTAL':<8} {'':>10} {'':>10} {'':>10} ${total_value:>11.2f} {color}${total_pnl:>+9.2f}\033[0m {color}{total_pnl_pct:>+7.1f}%\033[0m")
    else:
        total_value = 0.0
    
    # --- STOP LOSS CHECK ---
    stops = [p for p in positions if p['pnl_pct'] <= -STOP_LOSS_PCT]
    
    # --- BUILD ACTION PLAN ---
    held_tickers = [p['ticker'] for p in positions]
    to_sell = []
    
    if regime == "BEAR":
        # Sell everything
        to_sell = [{'ticker': p['ticker'], 'qty': p['qty'], 'reason': 'BEAR MARKET PROTECTION'} for p in positions]
    else:
        # Sell stops first
        for p in stops:
            to_sell.append({'ticker': p['ticker'], 'qty': p['qty'], 'reason': f'STOP LOSS ({p["pnl_pct"]:.1f}%)'})
        # Sell non‑target (but not stops twice)
        for t in held_tickers:
            if t not in top_tickers and t not in [s['ticker'] for s in to_sell]:
                alpha_val = alphas[t]['alpha'] if t in alphas else 0.0
                to_sell.append({'ticker': t, 'qty': MY_HOLDINGS[t]['qty'],
                                'reason': f'No longer Top {n_target} (Alpha {alpha_val:+.1f}%)'})
    
    # --- CALCULATE CASH PROCEEDS ---
    cash_from_sales = 0.0
    for s in to_sell:
        price = prices[s['ticker']].iloc[-1]
        cash_from_sales += s['qty'] * price
    
    # Existing cash (uninvested) – we assume zero unless you keep some cash aside
    existing_cash = 0.0
    total_available_cash = existing_cash + cash_from_sales
    
    # Target total portfolio value (current value minus sold positions + cash)
    # Actually simpler: new portfolio value will be total_value + existing_cash (since we replace sold positions with cash)
    portfolio_value_after_sales = total_value + existing_cash  # cash from sales is already included in total_value? Wait: total_value includes the value of stocks we plan to sell. After selling, we still have the same total value but in cash.
    # More straightforward: The new target portfolio value is the current total_value (since we are just reallocating).
    target_total = total_value  # because we aren't adding or withdrawing cash
    
    # --- DISPLAY ACTION PLAN ---
    print("\n" + "="*80)
    print("🎯 YOUR ACTION PLAN FOR THIS WEEK")
    print("="*80)
    
    if not to_sell and not stops and regime != "BEAR":
        # Check if we need to rebalance existing positions
        current_target_vals = {t: next((p['val'] for p in positions if p['ticker'] == t), 0.0) for t in top_tickers}
        target_per_stock = target_total / n_target if n_target > 0 else 0
        need_rebalance = any(abs(current_target_vals[t] - target_per_stock) > 1.0 for t in top_tickers)
        
        if not need_rebalance:
            print("\n✅ HOLD STEADY – Your portfolio already matches the optimal allocation.")
            print("   No trades needed. Scan again next Sunday.")
        else:
            # Show rebalancing buys even without sells
            print("\n📊 PORTFOLIO REBALANCING NEEDED")
            print("-"*80)
            print(f" Target allocation: ${target_per_stock:.2f} per stock ({100/n_target:.0f}% each)")
            print()
            print(f"{'Ticker':<8} {'Current Value':>14} {'Target Value':>14} {'Action':>10} {'Amount':>12}")
            print("-"*80)
            for t in top_tickers:
                curr_val = current_target_vals[t]
                diff = target_per_stock - curr_val
                if diff > 1.0:
                    action = "BUY"
                    amt = diff
                elif diff < -1.0:
                    action = "TRIM"  # Should not happen with Top2 strategy
                    amt = -diff
                else:
                    action = "HOLD"
                    amt = 0.0
                print(f" {t:<8} ${curr_val:>13.2f} ${target_per_stock:>13.2f} {action:>10} ${amt:>11.2f}")
            
            # Show exact shares
            print("\n📋 Suggested Orders:")
            for t in top_tickers:
                curr_val = current_target_vals[t]
                diff = target_per_stock - curr_val
                if diff > 1.0:
                    price = prices[t].iloc[-1]
                    shares = diff / price
                    print(f"   • BUY {t}: ${diff:.2f} → {shares:.4f} shares at ${price:.2f}")
    else:
        # --- SELL SECTION ---
        if to_sell:
            print("\n📤 SELL ORDERS (execute these first)")
            print("-"*80)
            print(f"{'Ticker':<8} {'Quantity':>12} {'Price':>10} {'Proceeds':>12} {'Reason'}")
            print("-"*80)
            for s in to_sell:
                price = prices[s['ticker']].iloc[-1]
                proceeds = s['qty'] * price
                print(f" {s['ticker']:<8} {s['qty']:>12.4f} ${price:>9.2f} ${proceeds:>11.2f}  {s['reason']}")
            print("-"*80)
            print(f" 💵 Total cash from sales: ${cash_from_sales:.2f}")
        
        # --- BUY / REBALANCE SECTION (always show if not BEAR) ---
        if regime != "BEAR" and n_target > 0:
            # After sales, what are the remaining target positions?
            remaining_positions = [p for p in positions if p['ticker'] not in [s['ticker'] for s in to_sell]]
            # Current values of target stocks after sales
            current_target_vals = {}
            for t in top_tickers:
                pos = next((p for p in remaining_positions if p['ticker'] == t), None)
                current_target_vals[t] = pos['val'] if pos else 0.0
            
            target_per_stock = target_total / n_target
            
            print("\n📥 REBALANCING / BUY ORDERS")
            print("-"*80)
            print(f" Target allocation: ${target_per_stock:.2f} per stock ({100/n_target:.0f}% each)")
            print(f" Total portfolio value: ${target_total:.2f}")
            print()
            print(f"{'Ticker':<8} {'Current Value':>14} {'Target Value':>14} {'Action':>10} {'Amount':>12}")
            print("-"*80)
            
            for t in top_tickers:
                curr_val = current_target_vals[t]
                diff = target_per_stock - curr_val
                if abs(diff) < 1.0:
                    action = "HOLD"
                    amt = 0.0
                elif diff > 0:
                    action = "BUY"
                    amt = diff
                else:
                    action = "TRIM"  # shouldn't happen if we sold non-targets
                    amt = -diff
                print(f" {t:<8} ${curr_val:>13.2f} ${target_per_stock:>13.2f} {action:>10} ${amt:>11.2f}")
            
            # Show exact shares to buy
            print("\n📋 Suggested Buy Orders (fractional shares supported):")
            for t in top_tickers:
                curr_val = current_target_vals[t]
                diff = target_per_stock - curr_val
                if diff > 1.0:
                    price = prices[t].iloc[-1]
                    shares = diff / price
                    print(f"   • {t}: buy ${diff:.2f} → {shares:.4f} shares at ${price:.2f}")
            
            # Cash summary
            total_buy_amount = sum(max(0, target_per_stock - current_target_vals[t]) for t in top_tickers)
            print(f"\n 💵 Total cash needed for buys: ${total_buy_amount:.2f}")
            print(f" 💵 Cash available from sales: ${cash_from_sales:.2f}")
            if cash_from_sales < total_buy_amount:
                print(f" ⚠️  Shortfall: ${total_buy_amount - cash_from_sales:.2f} – you may need to add fresh capital or adjust allocation.")
    
    # --- STOP LOSS ALERTS ---
    if stops:
        print("\n" + "="*80)
        print("🚨 URGENT: STOP LOSS TRIGGERED!")
        print("="*80)
        for p in stops:
            print(f"   ⛔ SELL {p['ticker']} immediately – down {p['pnl_pct']:.1f}% (limit {STOP_LOSS_PCT}%)")
    
    # --- PORTFOLIO PROJECTION ---
    if regime != "BEAR" and n_target > 0:
        print("\n" + "-"*80)
        print("📊 EXPECTED PORTFOLIO AFTER REBALANCING")
        print("-"*80)
        final_positions = {}
        for t in top_tickers:
            final_positions[t] = target_per_stock if n_target > 0 else 0
        print(f" Number of positions: {len(final_positions)} (was {len(positions)})")
        for t, val in final_positions.items():
            pct = (val / target_total) * 100
            print(f"   {t}: ${val:.2f} ({pct:.1f}%)")
        print(f" Total portfolio value: ~${target_total:.2f}")
    
    print("\n" + "="*80)
    print("⏰ Next scan: Sunday after 8:00 PM IST")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()