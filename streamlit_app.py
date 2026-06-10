import json
from datetime import datetime

import pandas as pd
import streamlit as st

from scanner_engine import ScannerEngine


# ==========================================================
# 🎨 PAGE CONFIG & PREMIUM STYLING
# ==========================================================
st.set_page_config(page_title='Adaptive Momentum Dashboard', layout='wide', page_icon='⚡')

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 700; color: #00ffc8; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #00ffc8; color: black; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1e2130; border-radius: 4px 4px 0px; padding: 10px; }
    .stTabs [aria-selected="true"] { background-color: #00ffc8; color: black; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_analysis(scan_date, config_json):
    engine = ScannerEngine()
    engine.config = json.loads(config_json)
    return engine.get_analysis(end_date=scan_date)


def create_engine():
    if 'engine' not in st.session_state:
        st.session_state.engine = ScannerEngine()
    return st.session_state.engine


def holdings_to_dataframe(holdings):
    return pd.DataFrame(
        [
            {
                'Ticker': ticker,
                'Qty': values.get('qty', 0.0),
                'Avg Cost': values.get('avg_cost', 0.0),
                'Entry Date': values.get('entry_date', ''),
            }
            for ticker, values in holdings.items()
        ]
    )


engine = create_engine()
selected_date = st.sidebar.date_input('Analysis Date', datetime.now().date())
if selected_date.strftime('%A') != 'Sunday':
    st.sidebar.warning('Best used for Sunday weekly review. Select a Sunday for the intended process.')

config_json = json.dumps(engine.config, sort_keys=True)

with st.spinner('Analyzing Market Data...'):
    try:
        data = load_analysis(selected_date, config_json)
    except Exception as exc:
        st.error(f'Unable to fetch market data: {exc}')
        st.stop()

st.title('⚡ Adaptive Momentum Scanner')
st.caption(f'Last Scanned: {data["timestamp"]} — Scan Date: {selected_date}')


tab1, tab2, tab3 = st.tabs(['📊 DASHBOARD', '🏆 RANKINGS', '⚙️ SETTINGS'])

with tab1:
    m1, m2, m3 = st.columns(3)
    m1.metric('SPY Price', f'${data["spy_price"]:.2f}')
    m2.metric('Market Regime', data['regime'], delta=f'{data["dist"]:+.2f}%')

    total_val = 0.0
    total_cost = 0.0
    for ticker, holding in engine.config['my_holdings'].items():
        if holding.get('qty', 0) <= 0:
            continue

        price = data['scores'].get(ticker, {}).get('price')
        if price is None or pd.isna(price):
            if ticker in data['prices'].columns and len(data['prices'][ticker].dropna()) > 0:
                price = data['prices'][ticker].dropna().iloc[-1]
            else:
                price = holding.get('avg_cost', 0.0)

        total_val += holding['qty'] * price
        total_cost += holding['qty'] * holding['avg_cost']

    pnl_pct = (total_val / total_cost - 1) * 100 if total_cost > 0 else 0.0
    m3.metric('Portfolio Value', f'${total_val:.2f}', delta=f'{pnl_pct:+.1f}%')

    if data['regime'] == 'VOLATILE':
        st.warning('⚠️ High volatility detected. Consider tighter sizing until the trend confirms.')

    st.markdown('---')
    n_target = data.get('n_target', 0)
    top_targets = data.get('top_targets', [])

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.subheader('💼 Your Portfolio')
        portfolio_items = []
        for item in data['portfolio_items']:
            portfolio_items.append(
                {
                    'Ticker': item['ticker'],
                    'Value': f'${item["value"]:.2f}',
                    'P&L %': f'{item["pnl_pct"]:+.1f}%',
                    'Stop Loss (ATR)': f'-{item["atr_stop_dist"]:.1f}%',
                    'Status': item['status'],
                }
            )

        if portfolio_items:
            st.table(pd.DataFrame(portfolio_items))
        else:
            st.info('No holdings found. Add them in Settings.')

        if len(top_targets) >= 2:
            st.markdown('---')
            st.subheader('🛡️ Risk & Diversification Profile')
            t1, t2 = top_targets[0], top_targets[1]
            corr_impact = '🔴 HIGH' if data['top_correlation'] > 0.7 else '🟢 LOW'
            sector_impact = '🔴 MATCH' if data['same_sector'] else '🟢 NO'
            st.table(
                pd.DataFrame(
                    [
                        {'Metric': 'Correlation', 'Value': f'{data["top_correlation"]:.2f}', 'Impact': corr_impact},
                        {'Metric': 'Sector Overlap', 'Value': f'{data["scores"][t1]["sector"]} | {data["scores"][t2]["sector"]}', 'Impact': sector_impact},
                        {'Metric': 'Diversification Score', 'Value': f'{data["diversification_score"]:.0f}/100', 'Impact': ''},
                    ]
                )
            )

    with col_right:
        st.subheader('🎯 Action Plan')
        if data['regime'] == 'BEAR':
            st.error('🚨 SELL EVERYTHING - Market in BEAR Regime')
        else:
            if data['to_sell']:
                for item in data['to_sell']:
                    st.error(f'🔴 SELL ALL **{item["ticker"]}** ({item["reason"]})')
                st.caption('Use the cash from your sells to fund the BUY orders below.')

            for item in data['buy_orders']:
                label = 'New Entry' if item['type'] == 'NEW' else 'Add'
                st.success(f'🟢 BUY ({label}) **{item["ticker"]}**: ${item["amount"]:.2f} (~{item["shares"]:.4f} shares at ${item["price"]:.2f})')

            for item in data['hold_orders']:
                st.info(f'🔵 HOLD **{item["ticker"]}** (Val: ${item["value"]:.2f})')

            if data.get('risk_tip'):
                st.warning(f'⚠️ {data["risk_tip"]}')

with tab2:
    st.subheader('🏆 Momentum Rankings')
    rank_data = []
    for ticker, d in data['sorted_ranks']:
        rank_data.append(
            {
                'Ticker': ticker,
                'Sector': d['sector'],
                'Price': f'${d["price"]:.2f}',
                'Score': f'{d["score"]:.1f}',
                '3M Return': f'{d["ret3m"]:+.1f}%',
                '6M Return': f'{d["ret6m"]:+.1f}%',
                'Above 200 SMA': '✅ Yes' if d['above_ma200'] else '❌ No',
            }
        )
    st.dataframe(pd.DataFrame(rank_data).set_index('Ticker'), width=1000)

with tab3:
    st.subheader('⚙️ Portfolio & Settings')
    st.write('Edit holdings and strategy constants below. Click Save to update config.json.')

    holdings_df = holdings_to_dataframe(engine.config.get('my_holdings', {}))
    edited_holdings = st.data_editor(holdings_df, num_rows='dynamic')

    if st.button('💾 SAVE HOLDINGS'):
        new_holdings = {}
        for _, row in edited_holdings.iterrows():
            if row.get('Ticker'):
                new_holdings[row['Ticker'].upper()] = {
                    'qty': float(row.get('Qty', 0.0)),
                    'avg_cost': float(row.get('Avg Cost', 0.0)),
                    'entry_date': row.get('Entry Date') or datetime.now().strftime('%Y-%m-%d'),
                }
        engine.config['my_holdings'] = new_holdings
        engine.save_config()
        st.success('Holdings updated successfully!')
        st.cache_data.clear()
        st.experimental_rerun()

    st.markdown('---')
    st.write('Strategy Constants')
    c1, c2 = st.columns(2)
    new_cap = c1.number_input('Initial Capital ($)', value=float(engine.config.get('initial_capital', 300.0)))
    new_atr = c2.number_input('ATR Multiplier', value=float(engine.config.get('atr_mult', 2.5)))

    c3, c4 = st.columns(2)
    new_bull = c3.number_input('Max Positions (Bull)', value=int(engine.config.get('max_positions_bull', 3)), min_value=1, max_value=10)
    new_volatile = c4.number_input('Max Positions (Volatile)', value=int(engine.config.get('max_positions_volatile', 2)), min_value=1, max_value=10)

    c5, c6 = st.columns(2)
    new_min_return = c5.number_input('Min Momentum Return (%)', value=float(engine.config.get('momentum_min_return', 5.0)))
    new_min_score = c6.number_input('Min Score', value=float(engine.config.get('min_score', 0.0)))

    c7, c8 = st.columns(2)
    new_confirm = c7.number_input('Regime Confirmation Days', value=int(engine.config.get('regime_confirmation_days', 10)), min_value=1, max_value=30)
    new_max_pct = c8.number_input('Max Position % of Portfolio', value=float(engine.config.get('max_position_pct', 0.33)), min_value=0.05, max_value=1.0, step=0.01)

    c9, c10 = st.columns(2)
    new_risk_pct = c9.number_input('Risk Per Trade %', value=float(engine.config.get('risk_per_trade_pct', 0.02)), min_value=0.005, max_value=0.10, step=0.005)

    if st.button('💾 SAVE CONSTANTS'):
        engine.config['initial_capital'] = new_cap
        engine.config['atr_mult'] = new_atr
        engine.config['max_positions_bull'] = new_bull
        engine.config['max_positions_volatile'] = new_volatile
        engine.config['momentum_min_return'] = new_min_return
        engine.config['min_score'] = new_min_score
        engine.config['regime_confirmation_days'] = new_confirm
        engine.config['max_position_pct'] = new_max_pct
        engine.config['risk_per_trade_pct'] = new_risk_pct
        engine.save_config()
        st.success('Constants updated successfully!')
        st.cache_data.clear()
        st.experimental_rerun()
