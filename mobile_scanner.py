import flet as ft
from scanner_engine import ScannerEngine
import threading
import traceback

class AdaptiveScannerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.engine = ScannerEngine()
        self.data = None
        
        # UI Components
        self.loading_screen = ft.Container(
            content=ft.Column([
                ft.ProgressRing(color="cyan"),
                ft.Text("Fetching Market Data...", color="cyan", size=20)
            ], alignment="center", horizontal_alignment="center"),
            expand=True,
            bgcolor="#0F172A",
            visible=True
        )
        
        self.main_screen = ft.Container(
            content=ft.Column(scroll="auto", expand=True),
            expand=True,
            bgcolor="#0F172A",
            visible=False,
            padding=20
        )
        
        self.setup_page()
        self.page.add(self.loading_screen, self.main_screen)
        self.refresh_data()

    def setup_page(self):
        self.page.title = "Adaptive Momentum Scanner"
        self.page.theme_mode = "dark"
        self.page.bgcolor = "#0F172A"
        self.page.window_width = 400
        self.page.window_height = 800
        
        self.page.navigation_bar = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon="dashboard", label="Market"),
                ft.NavigationBarDestination(icon="leaderboard", label="Rankings"),
                ft.NavigationBarDestination(icon="account_balance_wallet", label="Portfolio"),
                ft.NavigationBarDestination(icon="settings", label="Settings"),
            ],
            on_change=self.handle_nav_change,
            bgcolor="#1E293B",
        )

    def refresh_data(self):
        def task():
            try:
                self.loading_screen.visible = True
                self.main_screen.visible = False
                self.page.update()
                
                self.data = self.engine.get_analysis()
                self.show_dashboard()
                
                self.loading_screen.visible = False
                self.main_screen.visible = True
                self.page.update()
            except Exception as e:
                print(f"Data Refresh Error: {e}")
                traceback.print_exc()

        threading.Thread(target=task, daemon=True).start()

    def handle_nav_change(self, e):
        idx = e.control.selected_index
        if idx == 0: self.show_dashboard()
        elif idx == 1: self.show_rankings()
        elif idx == 2: self.show_portfolio()
        elif idx == 3: self.show_settings()
        self.page.update()

    def show_dashboard(self):
        regime = self.data['regime']
        color = "green" if regime == "BULL" else "orange" if regime == "VOLATILE" else "red"
        
        self.main_screen.content.controls = [
            ft.Text("Market Overview", size=28, weight="bold"),
            ft.Container(
                content=ft.Column([
                    ft.Text(regime, size=42, weight="black", color=color),
                    ft.Text("Current Market Regime", size=16, color="white60"),
                    ft.Divider(height=20, color="transparent"),
                    ft.Row([
                        ft.Column([ft.Text(f"${self.data['spy_price']:.2f}", size=20, weight="bold"), ft.Text("SPY Price", size=12, color="white60")], horizontal_alignment="center"),
                        ft.Column([ft.Text(f"{self.data['dist']:+.2f}%", size=20, weight="bold"), ft.Text("Dist to MA", size=12, color="white60")], horizontal_alignment="center"),
                    ], alignment="spaceAround")
                ], horizontal_alignment="center"),
                padding=30, bgcolor="#1E293B", border_radius=20, border=ft.Border.all(1, color), margin=ft.Margin(0, 20, 0, 0)
            ),
            ft.Row([
                ft.Text("Action Plan", size=22, weight="bold"),
                ft.Container(content=ft.Icon("refresh"), on_click=lambda _: self.refresh_data(), padding=10)
            ], alignment="spaceBetween"),
            self.get_action_plan_ui()
        ]
        self.page.update()

    def get_action_plan_ui(self):
        actions = []
        n_target = 2 if self.data['regime'] == "BULL" else 1 if self.data['regime'] == "VOLATILE" else 0
        sorted_tickers = sorted(self.data['scores'].items(), key=lambda x: x[1]['score'], reverse=True)
        top_4 = [t for t, _ in sorted_tickers[:4]]
        
        to_sell = []
        for t, h in self.engine.config['my_holdings'].items():
            if h['qty'] <= 0: continue
            curr_price = self.data['prices'][t].iloc[-1]
            pnl_pct = (curr_price / h['avg_cost'] - 1) * 100
            
            reason = ""
            if self.data['regime'] == "BEAR": reason = "Bear Market"
            elif pnl_pct < -7: reason = "Stop Loss"
            elif t not in top_4: reason = "Dropped from Top 4"
            elif not self.data['scores'][t]['above_ma200']: reason = "Below 200 SMA"
            if reason: to_sell.append((t, reason))

        if self.data['regime'] == "BEAR":
            actions.append(self.action_item("SELL EVERYTHING", "Market is in Bear Regime", "red"))
        else:
            for t, r in to_sell: actions.append(self.action_item(f"SELL {t}", r, "red"))
            for t_rank in sorted_tickers[:n_target]:
                ticker = t_rank[0]
                is_held = self.engine.config['my_holdings'].get(ticker, {}).get('qty', 0) > 0
                if not is_held: actions.append(self.action_item(f"BUY {ticker}", "Top momentum ranking", "green"))
                else: actions.append(self.action_item(f"HOLD {ticker}", "Currently in top target", "cyan"))

        if not actions: actions.append(ft.Text("No actions needed.", color="white60"))
        return ft.Column(actions)

    def action_item(self, title, subtitle, color):
        return ft.Container(
            content=ft.ListTile(
                leading=ft.Icon("trending_up" if "BUY" in title else "trending_down" if "SELL" in title else "pause", color=color),
                title=ft.Text(title, weight="bold", color=color),
                subtitle=ft.Text(subtitle, size=12, color="white60"),
            ),
            bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 0, 0, 10)
        )

    def show_rankings(self):
        sorted_tickers = sorted(self.data['scores'].items(), key=lambda x: x[1]['score'], reverse=True)
        items = [ft.Text("Momentum Rankings", size=28, weight="bold")]
        for i, (t, d) in enumerate(sorted_tickers, 1):
            color = "green" if i <= 2 else "orange" if i <= 4 else "white60"
            items.append(ft.Container(
                content=ft.Row([
                    ft.Text(str(i), size=18, weight="bold", width=30),
                    ft.Column([ft.Text(t, size=18, weight="bold"), ft.Text(d['sector'], size=12, color="white60")], expand=True),
                    ft.Column([ft.Text(f"{d['conviction']:.1f}", size=18, weight="bold", color=color, text_align="right"), ft.Text("Score", size=12, color="white60", text_align="right")]),
                ]),
                padding=15, bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 0, 0, 10)
            ))
        self.main_screen.content.controls = items
        self.page.update()

    def show_portfolio(self):
        items = [
            ft.Row([
                ft.Text("Your Portfolio", size=28, weight="bold"),
                ft.Container(content=ft.Icon("add_circle", color="cyan"), on_click=lambda _: self.edit_holding_dialog(), padding=10)
            ], alignment="spaceBetween"),
        ]
        total_val = 0
        for t, h in self.engine.config['my_holdings'].items():
            if h['qty'] <= 0: continue
            curr_price = self.data['prices'][t].iloc[-1]
            val = h['qty'] * curr_price
            total_val += val
            pnl = (curr_price / h['avg_cost'] - 1) * 100
            pnl_color = "green" if pnl >= 0 else "red"
            items.append(ft.Container(
                content=ft.Row([
                    ft.Column([ft.Text(t, size=20, weight="bold"), ft.Text(f"{h['qty']:.4f} shares", size=12, color="white60")], expand=True),
                    ft.Column([ft.Text(f"${val:.2f}", size=18, weight="bold", text_align="right"), ft.Text(f"{pnl:+.1f}%", size=14, weight="bold", color=pnl_color, text_align="right")]),
                    ft.PopupMenuButton(items=[
                        ft.PopupMenuItem(text="Edit", icon="edit", on_click=lambda _, ticker=t: self.edit_holding_dialog(ticker)),
                        ft.PopupMenuItem(text="Delete", icon="delete", on_click=lambda _, ticker=t: self.delete_holding(ticker)),
                    ])
                ]),
                padding=15, bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 0, 0, 10)
            ))
        items.insert(1, ft.Text(f"Total Value: ${total_val:.2f}", size=20, weight="bold", color="cyan"))
        self.main_screen.content.controls = items
        self.page.update()

    def edit_holding_dialog(self, ticker=""):
        h = self.engine.config['my_holdings'].get(ticker, {"qty": 0, "avg_cost": 0})
        t_field = ft.TextField(label="Ticker", value=ticker, read_only=ticker!="")
        q_field = ft.TextField(label="Quantity", value=str(h['qty']))
        c_field = ft.TextField(label="Avg Cost", value=str(h['avg_cost']))
        
        def save_click(e):
            self.engine.update_holding(t_field.value.upper(), q_field.value, c_field.value)
            self.page.dialog.open = False
            self.refresh_data()
            self.page.update()

        self.page.dialog = ft.AlertDialog(
            title=ft.Text("Edit Holding" if ticker else "Add Holding"),
            content=ft.Column([t_field, q_field, c_field], tight=True),
            actions=[ft.TextButton("Cancel", on_click=lambda _: setattr(self.page.dialog, "open", False) or self.page.update()), ft.ElevatedButton("Save", on_click=save_click)],
        )
        self.page.dialog.open = True
        self.page.update()

    def delete_holding(self, ticker):
        self.engine.delete_holding(ticker)
        self.show_portfolio()

    def show_settings(self):
        self.main_screen.content.controls = [
            ft.Text("Settings", size=28, weight="bold"),
            ft.Container(
                content=ft.Column([
                    ft.TextField(label="Initial Capital", value=str(self.engine.config['initial_capital']), prefix_text="$"),
                    ft.TextField(label="ATR Multiplier", value=str(self.engine.config['atr_mult'])),
                    ft.ElevatedButton("Save Changes", icon="save", on_click=lambda _: self.page.show_snack_bar(ft.SnackBar(ft.Text("Settings Saved!")))),
                ], spacing=20),
                padding=20, margin=ft.Margin(0, 20, 0, 0)
            )
        ]
        self.page.update()

def main(page: ft.Page):
    app = AdaptiveScannerApp(page)

if __name__ == "__main__":
    ft.run(main)
