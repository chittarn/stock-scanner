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
        
        if self.data['regime'] == "BEAR":
            actions.append(self.action_item("SELL EVERYTHING", "Market is in Bear Regime", "red"))
        else:
            # Sells
            for s in self.data['to_sell']:
                actions.append(self.action_item(f"SELL {s['ticker']}", f"Exit position ({s['reason']})", "red"))
            
            # Buys
            for b in self.data['buy_orders']:
                buy_label = "New Entry" if b['type'] == 'NEW' else "Add"
                actions.append(self.action_item(f"BUY ({buy_label}) {b['ticker']}", f"Invest ${b['amount']:.2f} (~{b['shares']:.4f} shares)", "green"))
            
            # Holds
            for h in self.data['hold_orders']:
                actions.append(self.action_item(f"HOLD {h['ticker']}", f"Current value: ${h['value']:.2f}", "cyan"))
                
            # Risk Tip
            if self.data['risk_tip']:
                actions.append(ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon("warning", color="orange"),
                        title=ft.Text("Risk Warning", weight="bold", color="orange"),
                        subtitle=ft.Text(self.data['risk_tip'], size=12, color="white60"),
                    ),
                    bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 0, 0, 10)
                ))

        if not actions: 
            actions.append(ft.Text("No actions needed.", color="white60"))
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
        items = [ft.Text("Momentum Rankings", size=28, weight="bold")]
        top_targets = self.data['top_targets']
        
        for i, (t, d) in enumerate(self.data['sorted_ranks'], 1):
            if t in top_targets:
                color = "green"
            elif t in self.data['eligible_candidates']:
                color = "orange"
            else:
                color = "white60"
                
            items.append(ft.Container(
                content=ft.Row([
                    ft.Text(str(i), size=18, weight="bold", width=30),
                    ft.Column([
                        ft.Text(t, size=18, weight="bold"), 
                        ft.Text(d['sector'], size=12, color="white60")
                    ], expand=True),
                    ft.Column([
                        ft.Text(f"{d['conviction']:.1f}", size=18, weight="bold", color=color, text_align="right"), 
                        ft.Text(f"Score: {d['score']:.1f}%", size=12, color="white60", text_align="right")
                    ]),
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
        
        for item in self.data['portfolio_items']:
            t = item['ticker']
            val = item['value']
            pnl = item['pnl_pct']
            pnl_color = "green" if pnl >= 0 else "red"
            
            qty = self.engine.config['my_holdings'].get(t, {}).get('qty', 0)
            status_color = "green" if item['status'] == "KEEP" else "red" if item['status'] in ["SELL", "STOP"] else "orange"
            
            items.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(t, size=20, weight="bold"), 
                        ft.Text(f"{qty:.4f} shares | ATR Stop: -{item['atr_stop_dist']:.1f}%", size=12, color="white60")
                    ], expand=True),
                    ft.Column([
                        ft.Text(f"${val:.2f}", size=18, weight="bold", text_align="right"), 
                        ft.Row([
                            ft.Text(f"{pnl:+.1f}%", size=12, weight="bold", color=pnl_color),
                            ft.Text(f" | {item['status']}", size=12, weight="bold", color=status_color)
                        ], alignment="end")
                    ], horizontal_alignment="end"),
                    ft.PopupMenuButton(items=[
                        ft.PopupMenuItem(content="Edit", icon="edit", on_click=lambda _, ticker=t: self.edit_holding_dialog(ticker)),
                        ft.PopupMenuItem(content="Delete", icon="delete", on_click=lambda _, ticker=t: self.delete_holding(ticker)),
                    ])
                ]),
                padding=15, bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 0, 0, 10)
            ))
            
        items.insert(1, ft.Text(f"Total Value: ${self.data['total_value']:.2f}", size=20, weight="bold", color="cyan"))
        
        # Add Detailed Risk Card if there are top targets
        if len(self.data['top_targets']) >= 2:
            t1, t2 = self.data['top_targets'][0], self.data['top_targets'][1]
            div_color = "red" if self.data['diversification_score'] < 30 else "orange" if self.data['diversification_score'] < 70 else "green"
            
            items.append(ft.Container(
                content=ft.Column([
                    ft.Text("Risk Profile", size=18, weight="bold", color="white"),
                    ft.Divider(height=10, color="white24"),
                    ft.Row([ft.Text("Correlation:", size=14, color="white60"), ft.Text(f"{self.data['top_correlation']:.2f}", size=14, weight="bold")]),
                    ft.Row([ft.Text("Sector Match:", size=14, color="white60"), ft.Text("MATCH" if self.data['same_sector'] else "NO", size=14, weight="bold", color="red" if self.data['same_sector'] else "green")]),
                    ft.Row([ft.Text("Diversification Score:", size=14, color="white60"), ft.Text(f"{self.data['diversification_score']:.0f}/100", size=14, weight="bold", color=div_color)]),
                ], spacing=10),
                padding=20, bgcolor="#1E293B", border_radius=12, margin=ft.Margin(0, 10, 0, 0)
            ))
            
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
        cap_field = ft.TextField(label="Initial Capital", value=str(self.engine.config['initial_capital']), prefix_text="$")
        atr_field = ft.TextField(label="ATR Multiplier", value=str(self.engine.config['atr_mult']))
        
        def save_settings(e):
            try:
                self.engine.config['initial_capital'] = float(cap_field.value)
                self.engine.config['atr_mult'] = float(atr_field.value)
                self.engine.save_config()
                self.page.show_snack_bar(ft.SnackBar(ft.Text("Settings Saved!")))
                self.refresh_data()
            except ValueError:
                self.page.show_snack_bar(ft.SnackBar(ft.Text("Error: Please enter valid numbers.")))

        self.main_screen.content.controls = [
            ft.Text("Settings", size=28, weight="bold"),
            ft.Container(
                content=ft.Column([
                    cap_field,
                    atr_field,
                    ft.ElevatedButton("Save Changes", icon="save", on_click=save_settings),
                ], spacing=20),
                padding=20, margin=ft.Margin(0, 20, 0, 0)
            )
        ]
        self.page.update()

def main(page: ft.Page):
    app = AdaptiveScannerApp(page)

if __name__ == "__main__":
    ft.run(main)
