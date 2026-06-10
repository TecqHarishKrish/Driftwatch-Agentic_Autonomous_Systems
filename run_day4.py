"""
=============================================================
  DriftWatch | run_day4.py
  DAY 4 — FULL DEMO RUNNER
  Purpose : Runs both demo scenarios sequentially with the
            live dashboard open. This is your submission demo.
  Usage   :
    Terminal 1: python -m dashboard.app
    Terminal 2: python run_day4.py
  Options :
    python run_day4.py --demo1     (research only)
    python run_day4.py --demo2     (coding only)
    python run_day4.py --benchmark (run A/B benchmark)
    python run_day4.py             (both demos)
=============================================================
"""
import os
import sys
import time
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
console = Console()


def check_dashboard() -> bool:
    """Return True if dashboard is running."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:5000/api/state", timeout=1)
        return True
    except Exception:
        return False


def run_demo1() -> dict:
    from demos.demo_research import run_research_demo
    console.print(Panel.fit(
        "[bold cyan]Demo 1 — Research Task[/bold cyan]\n"
        "Lithium mining water quality policy brief\n"
        "Drift injected at step 3 (EV market tangent)",
        title="DEMO 1 / 2"
    ))
    return run_research_demo(verbose=True)


def run_demo2() -> dict:
    from demos.demo_coding import run_coding_demo
    console.print(Panel.fit(
        "[bold cyan]Demo 2 — Code Generation Task[/bold cyan]\n"
        "JWT authentication module\n"
        "Scope creep drift injected at step 3 (OAuth2 + admin panel)",
        title="DEMO 2 / 2"
    ))
    return run_coding_demo(verbose=True)


def print_comparison(r1: dict, r2: dict) -> None:
    """Side-by-side summary of both demo runs."""
    table = Table(title="Demo Comparison Summary", show_header=True)
    table.add_column("Metric",    style="cyan")
    table.add_column("Demo 1 — Research", justify="center")
    table.add_column("Demo 2 — Coding",   justify="center")

    c1 = r1["certificate"]
    c2 = r2["certificate"]

    def v(val, good_if_high: bool = True):
        if isinstance(val, float):
            col = "green" if (val >= 0.75) == good_if_high else "red"
            return f"[{col}]{val:.3f}[/{col}]"
        col = "green" if (val > 0) == good_if_high else "yellow"
        return f"[{col}]{val}[/{col}]"

    table.add_row("Final coherence",    v(c1.final_score),   v(c2.final_score))
    table.add_row("Avg coherence",      v(c1.avg_score),     v(c2.avg_score))
    table.add_row("Drift events",       v(c1.drift_events, False),   v(c2.drift_events, False))
    table.add_row("Corrections fired",  v(c1.corrections_applied, False), v(c2.corrections_applied, False))
    table.add_row("Verdict",
                  f"[green]{c1.verdict}[/green]" if "VERIFIED" in c1.verdict else f"[red]{c1.verdict}[/red]",
                  f"[green]{c2.verdict}[/green]" if "VERIFIED" in c2.verdict else f"[red]{c2.verdict}[/red]")

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="DriftWatch Day 4 Runner")
    parser.add_argument("--demo1",     action="store_true", help="Run demo 1 only")
    parser.add_argument("--demo2",     action="store_true", help="Run demo 2 only")
    parser.add_argument("--benchmark", action="store_true", help="Run A/B benchmark")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]DriftWatch — Day 4 Full Demo[/bold cyan]\n"
        "Two polished demo scenarios for Round 1 submission\n"
        "Tip: Start dashboard first → python -m dashboard.app",
        title="DAY 4"
    ))

    if not os.getenv("GROQ_API_KEY") or \
       os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        console.print("[red]ERROR: GROQ_API_KEY not set in .env[/red]")
        sys.exit(1)

    if check_dashboard():
        console.print("[green]Dashboard connected — http://localhost:5000[/green]\n")
    else:
        console.print("[yellow]Dashboard not running. Start it with:[/yellow]")
        console.print("[yellow]  python -m dashboard.app[/yellow]\n")

    if args.benchmark:
        from benchmark.run_benchmark import run_benchmark
        console.print("[cyan]Running A/B Benchmark (15-25 minutes)...[/cyan]")
        run_benchmark()
        return

    r1 = r2 = None

    if args.demo1 or (not args.demo1 and not args.demo2):
        r1 = run_demo1()
        console.print("\n[green]Demo 1 complete.[/green]\n")
        time.sleep(2)

    if args.demo2 or (not args.demo1 and not args.demo2):
        r2 = run_demo2()
        console.print("\n[green]Demo 2 complete.[/green]\n")

    if r1 and r2:
        print_comparison(r1, r2)

    console.print("\n[bold green]Day 4 complete. You are ready to record your demo video.[/bold green]")
    console.print("\n  Recording checklist:")
    console.print("  1. Open http://localhost:5000 in browser")
    console.print("  2. Start screen recording")
    console.print("  3. Run: python run_day4.py --demo1")
    console.print("  4. Show the drift graph dropping, correction firing, score recovering")
    console.print("  5. Show the coherence certificate at the end")
    console.print("  6. Run: python run_day4.py --demo2 for the second scenario")
    console.print("  7. Stop recording. Target: 3-4 minutes total.")


if __name__ == "__main__":
    main()
