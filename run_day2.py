"""
=============================================================
  DriftWatch | run_day2.py
  DAY 2 — FULL PIPELINE TEST
  Purpose : Runs the complete pipeline end-to-end:
            GoalAnchor → Agent → StepInterceptor → DriftDetector
            This is the first time real Groq API calls are made.
  Usage   : python run_day2.py
  Requires: GROQ_API_KEY in .env
=============================================================
"""
import os
import sys
import json
import time
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()
console = Console()


def run_full_pipeline(task: str, with_drift: bool = False) -> dict:
    """
    Run a complete agent execution with DriftWatch monitoring.

    Args:
        task       : The task string to execute
        with_drift : If True, injects a drift-inducing context at step 3

    Returns:
        dict with step events, drift summary, final output
    """
    from core.embedder import Embedder
    from core.drift_detector import DriftDetector
    from core.goal_anchor import GoalAnchor
    from agent.reasoning_extractor import ReasoningExtractor
    from agent.step_interceptor import StepInterceptor
    from agent.base_agent import run_agent

    console.print(f"\n[cyan]Task:[/cyan] {task[:90]}")
    console.print(f"[cyan]Mode:[/cyan] {'WITH intentional drift injection' if with_drift else 'Normal execution'}\n")

    # 1. Anchor the goal
    with Progress(SpinnerColumn(), TextColumn("[yellow]Anchoring goal...")) as prog:
        task_id = prog.add_task("", total=None)
        emb      = Embedder(verbose=False)
        anchor   = GoalAnchor(embedder=emb)
        anchor_result = anchor.anchor(task)
        prog.stop()

    # 2. Set up interceptor
    event_queue = []
    detector    = DriftDetector(embedder=emb, verbose=True)
    detector.anchor_goal(task, anchor_result["subgoals"])
    extractor   = ReasoningExtractor(embedder=emb)
    interceptor = StepInterceptor(
        detector=detector,
        extractor=extractor,
        event_queue=event_queue,
        verbose=True,
    )
    interceptor.anchor(task, anchor_result["subgoals"])

    # 3. Run agent
    console.print("[yellow]Running agent...[/yellow]")
    start_time = time.time()
    agent_state = run_agent(task)
    elapsed = time.time() - start_time

    # 4. Intercept each step
    console.print("\n[yellow]Running drift analysis on each step...[/yellow]")
    step_outputs = agent_state.get("step_outputs", [])
    all_events = []

    for step_data in step_outputs:
        step_num = step_data.get("step_num", len(all_events) + 1)

        # Optionally inject drift at step 3 for demo purposes
        if with_drift and step_num == 3:
            console.print(f"\n[red]>>> INJECTING DRIFT at step {step_num} for demo <<<[/red]")
            step_data["current_focus"]     = "Analyzing global EV market adoption and battery demand trends"
            step_data["connection_to_goal"] = "Growing EV demand drives lithium mining which provides context"
            step_data["step_output"]        = "Tesla produced 1.8M EVs in 2023. EV market projected at $823B by 2030."

        event = interceptor.intercept(step_num, step_data)
        all_events.append(event)

    # 5. Build results
    drift_events = interceptor.get_drift_events()
    scores = interceptor.score_history()
    summary = detector.summary()

    return {
        "task":          task,
        "elapsed_sec":   round(elapsed, 1),
        "total_steps":   len(step_outputs),
        "scores":        scores,
        "drift_count":   len(drift_events),
        "drift_events":  [e.to_dict() for e in drift_events],
        "detector_summary": summary,
        "final_output":  agent_state.get("final_output", ""),
        "all_events":    interceptor.get_all_events(),
    }


def print_results(results: dict) -> None:
    """Pretty-print pipeline results."""
    console.print(f"\n{'='*60}")
    console.print(f"[bold]Pipeline Complete[/bold]  ({results['elapsed_sec']}s)")
    console.print(f"{'='*60}")

    # Score table
    table = Table(title="Step-by-Step Coherence Scores", show_header=True)
    table.add_column("Step", justify="center")
    table.add_column("Score", justify="center")
    table.add_column("Drift?", justify="center")
    table.add_column("Type")

    for ev in results["all_events"]:
        drift_str = "[red]YES[/red]" if ev["drift_detected"] else "[green]NO[/green]"
        score_color = "red" if ev["drift_detected"] else "green"
        table.add_row(
            str(ev["step_num"]),
            f"[{score_color}]{ev['score']:.3f}[/{score_color}]",
            drift_str,
            ev["drift_type"] if ev["drift_detected"] else "—",
        )

    console.print(table)

    # Summary
    s = results["detector_summary"]
    console.print(f"\n[cyan]Summary:[/cyan]")
    console.print(f"  Total steps    : {s.get('total_steps', 0)}")
    console.print(f"  Drift events   : {s.get('drift_events', 0)}")
    console.print(f"  Final score    : {s.get('final_score', 0):.3f}")
    console.print(f"  Average score  : {s.get('avg_score', 0):.3f}")

    # Final output preview
    final = results.get("final_output", "")
    if final:
        console.print(f"\n[cyan]Final Output Preview:[/cyan]")
        console.print(f"  {final[:300]}{'...' if len(final) > 300 else ''}")


def main():
    console.print(Panel.fit(
        "[bold cyan]DriftWatch — Day 2 Full Pipeline Test[/bold cyan]\n"
        "Runs GoalAnchor → Agent → StepInterceptor → DriftDetector\n"
        "Requires: GROQ_API_KEY in .env",
        title="DAY 2"
    ))

    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        console.print("[red]ERROR: GROQ_API_KEY not set in .env[/red]")
        console.print("  1. Copy .env.example to .env")
        console.print("  2. Get free key at https://console.groq.com")
        sys.exit(1)

    task = (
        "Research the environmental impact of lithium mining on groundwater "
        "quality in South America and write exactly 3 specific policy "
        "recommendations that governments can implement."
    )

    console.print("\n[bold]Run 1: Normal execution (no drift)[/bold]")
    try:
        r1 = run_full_pipeline(task, with_drift=False)
        print_results(r1)
        console.print("\n[green]Run 1 complete[/green]")
    except Exception as e:
        console.print(f"[red]Run 1 failed: {e}[/red]")
        import traceback; traceback.print_exc()

    console.print("\n" + "="*60)
    console.print("[bold]Run 2: With drift injection at step 3[/bold]")
    console.print("(This simulates the demo — agent drifts, DriftWatch detects)")
    try:
        r2 = run_full_pipeline(task, with_drift=True)
        print_results(r2)
        if r2["drift_count"] > 0:
            console.print(f"\n[green]SUCCESS: DriftWatch detected {r2['drift_count']} drift event(s)[/green]")
        else:
            console.print("[yellow]WARNING: No drift detected — check injection logic[/yellow]")
    except Exception as e:
        console.print(f"[red]Run 2 failed: {e}[/red]")
        import traceback; traceback.print_exc()

    console.print(f"\n[green]Day 2 test complete.[/green]")
    console.print("  Next: python run_day3.py (correction engine + dashboard)")


if __name__ == "__main__":
    main()
