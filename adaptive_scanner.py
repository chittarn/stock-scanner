#!/usr/bin/env python3
"""
ADAPTIVE MOMENTUM SCANNER (CLI Version)
- Powered by ScannerEngine
"""

from scanner_engine import ScannerEngine
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint
import pandas as pd
import argparse
from datetime import datetime

class CLIScanner:
    def __init__(self):
        self.engine = ScannerEngine()
        self.console = Console()

    def run(self, analysis_date=None, force=False):
        if analysis_date is not None:
            date_to_use = analysis_date
        else:
            date_to_use = datetime.now().date()

        weekday = date_to_use.strftime('%A')
        if weekday != 'Sunday' and not force:
            self.console.print(Panel.fit(
                f"[yellow]Note:[/] This scanner is designed for weekly Sunday review. Running for {weekday} anyway.",
                border_style="yellow"
            ))

        with self.console.status("[bold green]Fetching & Analyzing data..."):
            data = self.engine.get_analysis(end_date=date_to_use)

        rprint(Panel.fit(
            f"[bold cyan]ADAPTIVE MOMENTUM SCANNER[/bold cyan]\n[dim]{data['timestamp']}[/dim]",
            border_style="blue"
        ))

        # 📊 Market Regime Table
        reg_color = "green" if data['regime'] == "BULL" else "yellow" if data['regime'] == "VOLATILE" else "red"
        reg_table = Table(title="Market Regime", box=None)
        reg_table.add_column("Metric", style="cyan")
        reg_table.add_column("Value", style="bold")
        reg_table.add_row("SPY Price", f"${data['spy_price']:.2f}")
        reg_table.add_row("SPY 200 SMA", f"${data['spy_ma']:.2f}")
        reg_table.add_row("Distance", f"{data['dist']:+.2f}%")
        reg_table.add_row("Regime", f"[{reg_color}]{data['regime']}[/{reg_color}]")
        self.console.print(reg_table)

        # 📈 Rankings Table (Sorted by Conviction)
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
            
            # Row styling: Green for top targets, Yellow for other eligible ones, Dim for others
            if t in top_targets:
                row_style = "bold green"
            elif t in data['eligible_candidates']:
                row_style = "yellow"
            else:
                row_style = "dim"
            
            rank_table.add_row(
                str(i), t, d['sector'], f"{d['score']:.1f}", 
                trend_str, hold_icon,
                style=row_style
            )
        self.console.print(rank_table)

        # 🛡️ Risk & Diversification Panel
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

        # 💼 Portfolio Analysis
        port_table = Table(title="Current Portfolio Status")
        port_table.add_column("Ticker")
        port_table.add_column("Value", justify="right")
        port_table.add_column("P&L %", justify="right")
        port_table.add_column("Stop Loss (ATR)", justify="right")
        port_table.add_column("Status", justify="center")
        
        for item in data['portfolio_items']:
            status_style = "bold green" if item['status'] == "KEEP" else "bold red" if item['status'] in ["SELL", "STOP"] else "yellow"
            status_display = f"[{status_style}]{item['status']}[/{status_style}]"
            
            port_table.add_row(
                item['ticker'], f"${item['value']:.2f}", f"{item['pnl_pct']:+.1f}%", 
                f"-{item['atr_stop_dist']:.1f}%", status_display
            )
        
        self.console.print(port_table)

        # 📊 Summary
        if data['total_cost'] > 0:
            summary_table = Table(title="Portfolio Summary", box=None)
            total_pnl_pct = (data['total_value'] / data['total_cost'] - 1) * 100
            pnl_color = "green" if total_pnl_pct >= 0 else "red"
            summary_table.add_row("Total Invested", f"${data['total_cost']:.2f}")
            summary_table.add_row("Current Value", f"${data['total_value']:.2f}")
            summary_table.add_row("Overall P&L %", f"[{pnl_color}]{total_pnl_pct:+.2f}%[/{pnl_color}]")
            self.console.print(summary_table)

        # 🎯 Action Plan
        action_panel = []
        if data['regime'] == "BEAR":
            action_panel.append("[bold red]ACTION: SELL EVERYTHING - MARKET IN BEAR REGIME[/bold red]")
        else:
            if data['to_sell']:
                action_panel.append("[bold red]ROTATE OUT / SELL ORDERS:[/bold red]")
                for s in data['to_sell']:
                    action_panel.append(f" - [bold red]SELL ALL[/bold red] {s['ticker']}: {s['qty']:.4f} shares ({s['reason']})")
                action_panel.append("\n[bold yellow]NOTE:[/bold yellow] Use proceeds to fund the new target positions below.")

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


def parse_args():
    parser = argparse.ArgumentParser(description="Adaptive Momentum Scanner for weekly review")
    parser.add_argument("--date", help="Run analysis up to this date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--force", action="store_true", help="Run even if the weekday is not Sunday.")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    analysis_date = None
    if args.date:
        analysis_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    scanner = CLIScanner()
    scanner.run(analysis_date=analysis_date, force=args.force)