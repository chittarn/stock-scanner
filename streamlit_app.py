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
        total_val += h['qty'] * data['prices'][t].iloc[-1]
        total_cost += h['qty'] * h['avg_cost']
    
    pnl_pct = (total_val / total_cost - 1) * 100 if total_cost > 0 else 0
    m3.metric("Portfolio Value", f"${total_val:.2f}", delta=f"{pnl_pct:+.1f}%")

    st.markdown("---")
    
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("💼 Your Portfolio")
        port_items = []
        for t, h in engine.config['my_holdings'].items():
            if h['qty'] <= 0: continue
            curr_p = data['prices'][t].iloc[-1]
            val = h['qty'] * curr_p
            pnl = (curr_p / h['avg_cost'] - 1) * 100
            port_items.append({"Ticker": t, "Shares": h['qty'], "Value": round(val, 2), "P&L %": round(pnl, 2)})
        
        if port_items:
            st.table(pd.DataFrame(port_items))
        else:
            st.info("No holdings found. Add them in Settings.")

    with col_right:
        st.subheader("🎯 Action Plan")
        n_target = 2 if data['regime'] == "BULL" else 1 if data['regime'] == "VOLATILE" else 0
        sorted_tickers = sorted(data['scores'].items(), key=lambda x: x[1]['score'], reverse=True)
        top_4 = [t for t, _ in sorted_tickers[:4]]
        
        if data['regime'] == "BEAR":
            st.error("🚨 SELL EVERYTHING - Market in BEAR Regime")
        else:
            # Check Sells
            to_sell = []
            for t, h in engine.config['my_holdings'].items():
                if h['qty'] <= 0: continue
                pnl = (data['prices'][t].iloc[-1] / h['avg_cost'] - 1) * 100
                
                if pnl < -7: 
                    to_sell.append(t)
                    st.error(f"🔴 SELL ALL {t} (Stop Loss: {pnl:.1f}%)")
                elif t not in top_4: 
                    to_sell.append(t)
                    st.warning(f"🟠 SELL ALL {t} (Dropped Rank)")
                elif not data['scores'][t]['above_ma200']:
                    to_sell.append(t)
                    st.warning(f"🟠 SELL ALL {t} (Below 200 SMA)")
            
            if to_sell:
                st.caption("Use the cash from your sells to fund the BUY orders below.")
            
            # Check Buys
            target_per = max(total_val, engine.config['initial_capital']) / n_target if n_target > 0 else 0
            buy_candidates = [t for t in sorted_tickers if t[0] not in to_sell][:n_target]
            
            for t_rank in buy_candidates:
                ticker = t_rank[0]
                is_held = ticker in engine.config['my_holdings'] and engine.config['my_holdings'][ticker].get('qty', 0) > 0
                curr_val = engine.config['my_holdings'][ticker].get('qty', 0) * data['prices'][ticker].iloc[-1] if is_held else 0
                diff = target_per - curr_val
                
                if not is_held:
                    st.success(f"🟢 BUY (New Entry) **{ticker}**: ${target_per:.2f}")
                elif diff > max(5.0, target_per * 0.10):
                    st.success(f"🟢 BUY (Add) **{ticker}**: ${diff:.2f}")
                elif is_held:
                    st.info(f"🔵 HOLD **{ticker}** (Val: ${curr_val:.2f})")

with tab2:
    st.subheader("🏆 Momentum Rankings")
    rank_df = pd.DataFrame.from_dict(data['scores'], orient='index').sort_values("score", ascending=False)
    st.dataframe(rank_df[['score', 'price', 'sector', 'above_ma200']], width=1000)

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
