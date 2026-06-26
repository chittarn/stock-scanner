#!/usr/bin/env python3
"""
Adaptive Momentum Scanner CLI

This script provides a console-ready interface for the momentum scanner.
Use it for weekly scans, holdings management, and configuration inspection.
"""

import argparse
import json
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scanner_engine import ScannerEngine, VERSION


class CLIScanner:
    def __init__(self):
        self.engine = ScannerEngine()
        self.console = Console()

    def print_scan(self, data, weekday):
        self.console.print(Panel.fit(
            f"[bold cyan]ADAPTIVE MOMENTUM SCANNER[/bold cyan]  [dim]v{VERSION}[/dim]\n[dim]{data['timestamp']}[/dim]",
            border_style="blue"
        ))

        reg_color = "green" if data['regime'] == "BULL" else "yellow" if data['regime'] == "VOLATILE" else "red"
        reg_table = Table(title="Market Regime", box=None)
        reg_table.add_column("Metric", style="cyan")
        reg_table.add_column("Value", style="bold")
        reg_table.add_row("SPY Price", f"${data['spy_price']:.2f}")
        reg_table.add_row("SPY 200 SMA", f"${data['spy_ma']:.2f}")
        reg_table.add_row("Distance", f"{data['dist']:+.2f}%")
        reg_table.add_row("Regime", f"[{reg_color}]{data['regime']}[/{reg_color}]")
        self.console.print(reg_table)

        n_target = data['n_target']
        rank_table = Table(title=f"Momentum Rankings (Target Top {n_target})")
        rank_table.add_column("Rank", justify="center")
        rank_table.add_column("Ticker", style="bold")
        rank_table.add_column("Sector", style="dim")
        rank_table.add_column("Score", justify="right")
        rank_table.add_column("Trend", justify="center")
        rank_table.add_column("Holdings", justify="center")

        top_targets = data['top_targets']
        for i, (t, d) in enumerate(data['sorted_ranks'], 1):
            is_held = self.engine.config['my_holdings'].get(t, {}).get('qty', 0) > 0
            hold_icon = "[H]" if is_held else ""
            trend_str = "[green]UP[/green]" if d['above_ma200'] else "[red]DN[/red]"
            if t in top_targets:
                style = "bold green"
            elif t in data['eligible_candidates']:
                style = "yellow"
            else:
                style = "dim"
            rank_table.add_row(str(i), t, d['sector'], f"{d['score']:.1f}", trend_str, hold_icon, style=style)
        self.console.print(rank_table)

        if len(top_targets) >= 2:
            t1, t2 = top_targets[0], top_targets[1]
            risk_table = Table(title=f"Detailed Risk Profile: {t1} vs {t2}", box=None)
            risk_table.add_column("Metric", style="cyan")
            risk_table.add_column("Value", style="bold")
            risk_table.add_column("Impact", justify="center")

            corr_impact = "[red]HIGH[/red]" if data['top_correlation'] > 0.7 else "[green]LOW[/green]"
            sector_impact = "[red]MATCH[/red]" if data['same_sector'] else "[green]NO[/green]"
            div_color = "red" if data['diversification_score'] < 30 else "yellow" if data['diversification_score'] < 70 else "green"

            risk_table.add_row("Correlation", f"{data['top_correlation']:.2f}", corr_impact)
            risk_table.add_row("Sector Overlap", f"{data['scores'][t1]['sector']} | {data['scores'][t2]['sector']}", sector_impact)
            risk_table.add_row("Diversification Score", f"[{div_color}]{data['diversification_score']:.0f}/100[/{div_color}]", "")
            self.console.print(risk_table)

        port_table = Table(title="Current Portfolio Status")
        port_table.add_column("Ticker")
        port_table.add_column("Value", justify="right")
        port_table.add_column("P&L %", justify="right")
        port_table.add_column("Stop Loss (ATR)", justify="right")
        port_table.add_column("Status", justify="center")

        for item in data['portfolio_items']:
            status_style = "bold green" if item['status'] == "KEEP" else "bold red" if item['status'] in ["SELL", "STOP"] else "bold yellow" if item['status'] == "TRIM" else "bold orange3" if item['status'] == "EXIT" else "yellow"
            status_label = item['status']
            if item['status'] == "TRIM":
                status_label = "TRIM ✂"
            status_display = f"[{status_style}]{status_label}[/{status_style}]"
            port_table.add_row(item['ticker'], f"${item['value']:.2f}", f"{item['pnl_pct']:+.1f}%", f"-{item['atr_stop_dist']:.1f}%", status_display)
        self.console.print(port_table)

        if data['total_cost'] > 0:
            summary_table = Table(title="Portfolio Summary", box=None)
            total_pnl_pct = (data['total_value'] / data['total_cost'] - 1) * 100
            pnl_color = "green" if total_pnl_pct >= 0 else "red"
            summary_table.add_row("Total Invested", f"${data['total_cost']:.2f}")
            summary_table.add_row("Current Value", f"${data['total_value']:.2f}")
            summary_table.add_row("Overall P&L %", f"[{pnl_color}]{total_pnl_pct:+.2f}%[/{pnl_color}]")
            self.console.print(summary_table)

        action_panel = []
        if data['regime'] == "BEAR":
            action_panel.append("[bold red]ACTION: SELL EVERYTHING - MARKET IN BEAR REGIME[/bold red]")
        else:
            if data['to_sell']:
                action_panel.append("[bold red]ROTATE OUT / SELL ORDERS:[/bold red]")
                for s in data['to_sell']:
                    action_panel.append(f" - [bold red]SELL[/bold red] {s['ticker']}: {s['qty']:.4f} shares ({s['reason']})")
                if data['buy_orders']:
                    action_panel.append("\n[bold yellow]NOTE:[/] Use proceeds to fund the new target positions below.")

            if data['buy_orders']:
                action_panel.append("\n[bold green]ROTATE INTO / BUY ORDERS:[/bold green]")
                for b in data['buy_orders']:
                    buy_type = "New Entry" if b['type'] == 'NEW' else "Add"
                    action_panel.append(f" - [bold green]{buy_type}[/bold green] {b['ticker']}: ${b['amount']:.2f} (~{b['shares']:.4f} shares at ${b['price']:.2f})")

            if data['hold_orders']:
                action_panel.append("\n[bold blue]KEEP / HOLD CURRENT POSITIONS:[/bold blue]")
                for h in data['hold_orders']:
                    action_panel.append(f" - [bold blue]KEEP[/bold blue] {h['ticker']}: Current value ${h['value']:.2f}")

            if not data['to_sell'] and not data['buy_orders'] and data['hold_orders']:
                action_panel.append("\n[bold green]Recommendation:[/] Keep current positions. No rotation required this week.")

            if data['risk_tip']:
                action_panel.append(f"\n[bold yellow]RISK TIP:[/bold yellow] {data['risk_tip']}")

        if not action_panel:
            action_panel.append("OK: Everything looks good. No trades needed this week.")

        self.console.print(Panel("\n".join(action_panel), title=f"Weekly Action Plan ({weekday})", border_style="green"))

    def show_holdings(self):
        holdings = self.engine.config.get('my_holdings', {})
        if not holdings:
            self.console.print('[yellow]No holdings found in config.json.[/yellow]')
            return

        table = Table(title='Current Holdings')
        table.add_column('Ticker', style='bold')
        table.add_column('Qty', justify='right')
        table.add_column('Avg Cost', justify='right')
        table.add_column('Entry Date', justify='center')

        for ticker, data in holdings.items():
            table.add_row(
                ticker,
                f"{data.get('qty', 0):.6f}",
                f"${data.get('avg_cost', 0):.2f}",
                data.get('entry_date', 'N/A')
            )
        self.console.print(table)

    def show_config(self):
        config = self.engine.config.copy()
        config.pop('my_holdings', None)
        self.console.print('[bold cyan]Scanner Configuration[/bold cyan]')
        self.console.print(json.dumps(config, indent=2))

    def add_holding(self, ticker, qty, avg_cost, entry_date=None):
        ticker = ticker.upper()
        self.engine.update_holding(ticker, qty, avg_cost, entry_date)
        self.console.print(f'[green]Added/Updated holding:[/] {ticker} — Qty: {qty}, Avg Cost: {avg_cost}')

    def delete_holding(self, ticker):
        ticker = ticker.upper()
        self.engine.delete_holding(ticker)
        self.console.print(f'[green]Removed holding:[/] {ticker}')

    def run(self, args=None):
        parser = argparse.ArgumentParser(description=f'Adaptive Momentum Scanner v{VERSION} — Weekly review tool')
        subparsers = parser.add_subparsers(dest='command')

        scan_parser = subparsers.add_parser('scan', help='Run the scanner and display the weekly action plan.')
        scan_parser.add_argument('--date', help='Run analysis up to this date (YYYY-MM-DD). Defaults to today.')
        scan_parser.add_argument('--force', action='store_true', help='Run even if the weekday is not Sunday.')
        scan_parser.add_argument('--json', action='store_true', help='Print the scan result as JSON.')
        scan_parser.add_argument('--output', help='Save JSON output to a file.')

        subparsers.add_parser('holdings', help='Show current holdings configured in config.json.')

        add_parser = subparsers.add_parser('add-holding', help='Add or update a holding in config.json.')
        add_parser.add_argument('ticker', help='Ticker symbol to add or update.')
        add_parser.add_argument('qty', type=float, help='Quantity of shares.')
        add_parser.add_argument('avg_cost', type=float, help='Average cost per share.')
        add_parser.add_argument('--entry-date', help='Optional entry date for trailing stop logic (YYYY-MM-DD).')

        remove_parser = subparsers.add_parser('remove-holding', help='Remove a holding from config.json.')
        remove_parser.add_argument('ticker', help='Ticker symbol to remove.')

        subparsers.add_parser('config', help='Show current scanner configuration from config.json.')
        subparsers.add_parser('web', help='Show web app launch instructions.')

        import sys
        if args is None:
            args = sys.argv[1:]
        if not args:
            args = ['scan']
        parsed = parser.parse_args(args)
        if parsed.command == 'scan':
            analysis_date = None
            if parsed.date:
                analysis_date = datetime.strptime(parsed.date, '%Y-%m-%d').date()

            weekday = analysis_date.strftime('%A') if analysis_date else datetime.now().strftime('%A')
            if weekday != 'Sunday' and not parsed.force:
                self.console.print(Panel.fit(
                    f"[yellow]Note:[/] This scanner is designed for weekly Sunday review. Running for {weekday} anyway.",
                    border_style='yellow'
                ))

            with self.console.status('[bold green]Fetching & Analyzing data...'):
                data = self.engine.get_analysis(end_date=analysis_date)

            if parsed.json:
                json_data = json.dumps(data, default=str, indent=2)
                self.console.print(json_data)
                if parsed.output:
                    with open(parsed.output, 'w') as f:
                        f.write(json_data)
                    self.console.print(f'[green]Saved JSON output to {parsed.output}[/green]')
            else:
                self.print_scan(data, weekday)
                if parsed.output:
                    with open(parsed.output, 'w') as f:
                        f.write(json.dumps(data, default=str, indent=2))
                    self.console.print(f'[green]Saved JSON output to {parsed.output}[/green]')

        elif parsed.command == 'holdings':
            self.show_holdings()

        elif parsed.command == 'add-holding':
            self.add_holding(parsed.ticker, parsed.qty, parsed.avg_cost, parsed.entry_date)

        elif parsed.command == 'remove-holding':
            self.delete_holding(parsed.ticker)

        elif parsed.command == 'config':
            self.show_config()

        elif parsed.command == 'web':
            self.console.print('[bold cyan]Web Application Instructions[/bold cyan]')
            self.console.print('Run the web interface with: [green]streamlit run streamlit_app.py[/green]')
            self.console.print('Then open the browser link shown by Streamlit.')


if __name__ == '__main__':
    CLIScanner().run()
