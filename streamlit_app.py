import streamlit as st
import pandas as pd
from scanner_engine import ScannerEngine
import json

# ==========================================================
# 🎨 PAGE CONFIG & PREMIUM STYLING
# ==========================================================
st.set_page_config(page_title="Adaptive Momentum Dashboard", layout="wide", page_icon="⚡")

# Custom CSS for a professional look
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 700; color: #00ffc8; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #00ffc8; color: black; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1e2130; border-radius: 4px 4px 0px 0px; padding: 10px; }
    .stTabs [aria-selected="true"] { background-color: #00ffc8; color: black; }
    </style>
    """, unsafe_allow_html=True)

# Initialize Engine
if 'engine' not in st.session_state:
    st.session_state.engine = ScannerEngine()

engine = st.session_state.engine

# Ensure stale cache cleared on first run (handles schema changes like missing n_target)
if 'cache_cleared' not in st.session_state:
    st.cache_data.clear()
    st.session_state.cache_cleared = True

# ==========================================================
# 🏗️ DATA FETCHING
# ==========================================================
@st.cache_data(ttl=3600)
def get_analysis_results():
    return engine.get_analysis()

with st.spinner("Analyzing Market Data..."):
    data = get_analysis_results()

# ==========================================================
# 🏗️ UI LAYOUT
# ==========================================================

st.title("⚡ Adaptive Momentum Scanner")
st.caption(f"Last Scanned: {data['timestamp']}")

tab1, tab2, tab3 = st.tabs(["📊 DASHBOARD", "🏆 RANKINGS", "⚙️ SETTINGS"])

with tab1:
    # Market Status Metrics
    m1, m2, m3 = st.columns(3)
    reg_color = "normal" if data['regime'] == "BULL" else "inverse"
    m1.metric("SPY Price", f"${data['spy_price']:.2f}")
    m2.metric("Market Regime", data['regime'], delta=f"{data['dist']:+.2f}%", delta_color=reg_color)
    
    # Portfolio Summary
    total_val = 0.0
    total_cost = 0.0
    for t, h in engine.config['my_holdings'].items():
        if h['qty'] <= 0: continue
        curr_p = data['scores'].get(t, {}).get('price')
        if curr_p is None or pd.isna(curr_p):
            curr_p = data['prices'][t].dropna().iloc[-1] if (t in data['prices'].columns and len(data['prices'][t].dropna()) > 0) else h['avg_cost']
        total_val += h['qty'] * curr_p
        total_cost += h['qty'] * h['avg_cost']
    
    pnl_pct = (total_val / total_cost - 1) * 100 if total_cost > 0 else 0
    m3.metric("Portfolio Value", f"${total_val:.2f}", delta=f"{pnl_pct:+.1f}%")

    if data['regime'] == "VOLATILE":
        st.warning("⚠️ **High Volatility Detected** (ATR Spike or below MA). Reduced position sizing is recommended.")

    st.markdown("---")
    
     # Strategy Logic (Pre-calculated in engine)
    # Safely retrieve n_target, default to 0 if not present (e.g., stale cache)
    n_target = data.get('n_target', 0)
    top_targets = data.get('top_targets', [])
    
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("💼 Your Portfolio")
        port_items = []
        for item in data['portfolio_items']:
            status_map = {
                "KEEP": "✅ KEEP",
                "SELL": "🔴 SELL",
                "STOP": "🚨 STOP",
                "EXIT": "🟠 EXIT"
            }
            port_items.append({
                "Ticker": item['ticker'],
                "Value": f"${item['value']:.2f}",
                "P&L %": f"{item['pnl_pct']:+.1f}%",
                "Stop Loss (ATR)": f"-{item['atr_stop_dist']:.1f}%",
                "Status": status_map.get(item['status'], item['status'])
            })
        
        if port_items:
            st.table(pd.DataFrame(port_items))
        else:
            st.info("No holdings found. Add them in Settings.")

        # 🛡️ Risk & Diversification Profile
        if len(top_targets) >= 2:
            st.markdown("---")
            st.subheader("🛡️ Risk & Diversification Profile")
            t1, t2 = top_targets[0], top_targets[1]
            
            corr_impact = "🔴 HIGH" if data['top_correlation'] > 0.7 else "🟢 LOW"
            sector_impact = "🔴 MATCH" if data['same_sector'] else "🟢 NO"
            
            risk_profile_items = [
                {"Metric": "Correlation", "Value": f"{data['top_correlation']:.2f}", "Impact": corr_impact},
                {"Metric": "Sector Overlap", "Value": f"{data['scores'][t1]['sector']} | {data['scores'][t2]['sector']}", "Impact": sector_impact},
                {"Metric": "Diversification Score", "Value": f"{data['diversification_score']:.0f}/100", "Impact": ""}
            ]
            st.table(pd.DataFrame(risk_profile_items))

    with col_right:
        st.subheader("🎯 Action Plan")
        
        if data['regime'] == "BEAR":
            st.error("🚨 SELL EVERYTHING - Market in BEAR Regime")
        else:
            # Check Sells
            if data['to_sell']:
                for s in data['to_sell']:
                    st.error(f"🔴 SELL ALL **{s['ticker']}** ({s['reason']})")
                st.caption("Use the cash from your sells to fund the BUY orders below.")
            
            # Check Buys
            for b in data['buy_orders']:
                buy_label = "New Entry" if b['type'] == 'NEW' else "Add"
                st.success(f"🟢 BUY ({buy_label}) **{b['ticker']}**: ${b['amount']:.2f} (~{b['shares']:.4f} shares)")
            
            # Check Holds
            for h in data['hold_orders']:
                st.info(f"🔵 HOLD **{h['ticker']}** (Val: ${h['value']:.2f})")
                
            if data['risk_tip']:
                st.warning(f"⚠️ {data['risk_tip']}")

with tab2:
    st.subheader("🏆 Momentum Rankings")
    rank_list = []
    for ticker, d in data['sorted_ranks']:
        rank_list.append({
            "Ticker": ticker,
            "Sector": d['sector'],
            "Price": f"${d['price']:.2f}",
            "Score": f"{d['score']:.1f}%",
            "Conviction": f"{d['conviction']:.1f}",
            "Above 200 SMA": "✅ Yes" if d['above_ma200'] else "❌ No"
        })
    rank_df = pd.DataFrame(rank_list).set_index("Ticker")
    st.dataframe(rank_df, width=1000)

with tab3:
    st.subheader("⚙️ Portfolio & Settings")
    
    # Edit Holdings
    st.write("Edit your holdings here. Click 'Save' to update config.json.")
    
    # Convert dict to DataFrame for editing
    h_list = [{"Ticker": t, "Qty": h['qty'], "Avg Cost": h['avg_cost']} for t, h in engine.config['my_holdings'].items()]
    edited_df = st.data_editor(pd.DataFrame(h_list), num_rows="dynamic")
    
    if st.button("💾 SAVE HOLDINGS"):
        new_holdings = {}
        for _, row in edited_df.iterrows():
            if row['Ticker']:
                new_holdings[row['Ticker'].upper()] = {"qty": float(row['Qty']), "avg_cost": float(row['Avg Cost'])}
        
        engine.config['my_holdings'] = new_holdings
        engine.save_config()
        st.success("Configuration updated successfully!")
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.write("Strategy Constants")
    c1, c2 = st.columns(2)
    new_cap = c1.number_input("Initial Capital ($)", value=float(engine.config['initial_capital']))
    new_atr = c2.number_input("ATR Multiplier", value=float(engine.config['atr_mult']))
    
    if st.button("💾 SAVE CONSTANTS"):
        engine.config['initial_capital'] = new_cap
        engine.config['atr_mult'] = new_atr
        engine.save_config()
        st.success("Constants updated!")
        st.rerun()
