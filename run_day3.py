"""
=============================================================
  DriftWatch | run_day3.py
  DAY 3 — INTEGRATION TEST
  Purpose : Tests correction engine + dashboard SSE pipeline
            Run AFTER starting the dashboard server:
              Terminal 1: python -m dashboard.app
              Terminal 2: python run_day3.py
  Usage   : python run_day3.py
=============================================================
"""
import os
import sys
import time
import threading
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
console = Console()


def run_with_correction(task: str, inject_drift_at: int = 3) -> dict:
    """
    Full pipeline with correction engine active.
    Sends events to dashboard if it is running.
    """
    from core.embedder import Embedder
    from core.drift_detector import DriftDetector, Phase
    from core.goal_anchor import GoalAnchor
    from core.correction_engine import CorrectionEngine
    from agent.reasoning_extractor import ReasoningExtractor
    from agent.step_interceptor import StepInterceptor
    from agent.base_agent import run_agent

    # Try to connect to dashboard (non-blocking)
    dashboard_available = False
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:5000/api/state", timeout=1)
        dashboard_available = True
        console.print("[green]Dashboard connected — open http://localhost:5000[/green]")
    except Exception:
        console.print("[yellow]Dashboard not running — events will print to console[/yellow]")
        console.print("[yellow]To see live graph: start dashboard first with:[/yellow]")
        console.print("[yellow]  python -m dashboard.app[/yellow]\n")

    # Setup event push function
    def push(event_type: str, data: dict):
        if dashboard_available:
            try:
                import urllib.request, json as _json
                req = urllib.request.Request(
                    f"http://localhost:5000/api/{event_type}",
                    data=_json.dumps(data).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=1)
            except Exception:
                pass

    # 1. Anchor goal
    emb    = Embedder(verbose=False)
    anchor = GoalAnchor(embedder=emb)
    result = anchor.anchor(task)

    # 2. Correction engine
    engine = CorrectionEngine(task=task, verbose=True)

    # 3. Interceptor with shared event list
    event_list = []
    detector   = DriftDetector(embedder=emb, verbose=True)
    detector.anchor_goal(task, result["subgoals"])
    extractor  = ReasoningExtractor(embedder=emb)
    interceptor = StepInterceptor(
        detector=detector,
        extractor=extractor,
        event_queue=event_list,
        verbose=True,
    )
    interceptor.anchor(task, result["subgoals"])

    # Signal dashboard task start
    if dashboard_available:
        push("clear", {})
        time.sleep(0.3)

    console.print(f"\n[cyan]Running agent with correction engine active...[/cyan]")
    agent_state = run_agent(task)

    step_outputs = agent_state.get("step_outputs", [])
    all_events   = []
    scores       = []

    for step_data in step_outputs:
        step_num = step_data.get("step_num", len(all_events) + 1)

        # Inject drift at specified step for demo
        if step_num == inject_drift_at:
            console.print(f"\n[red bold]>>> DRIFT INJECTION at step {step_num} <<<[/red bold]")
            step_data["current_focus"]      = "Analyzing global EV market growth and battery technology trends"
            step_data["connection_to_goal"] = "EV demand drives lithium mining which motivates this research"
            step_data["step_output"]        = "Tesla sold 1.8M EVs in 2023. EV market projected at $823B by 2030 driven by government subsidies."

        # Intercept step
        event  = interceptor.intercept(step_num, step_data)
        scores.append(event.score)

        # Save checkpoint if clean
        if not event.drift_detected and event.score > 0.72:
            engine.save_checkpoint(step_num, event.score, step_data)

        # Fire correction if needed
        correction_result = None
        if event.correction_needed:
            correction_result = engine.correct(
                step_num=step_num,
                score=event.score,
                threshold=event.threshold,
                drift_type=event.drift_type,
                current_prompt_context=step_data.get("step_output", ""),
            )

            # Push correction banner to dashboard
            if dashboard_available:
                push("correction_event", {
                    "step_num":   step_num,
                    "tier":       correction_result["tier"].value,
                    "drift_type": event.drift_type,
                    "score":      event.score,
                })

        # Push step event to dashboard
        ev_dict = event.to_dict()
        if correction_result:
            ev_dict["correction_tier"] = correction_result["tier"].value
        if dashboard_available:
            push("step_event", ev_dict)

        all_events.append({
            "event":      event,
            "correction": correction_result,
        })

        time.sleep(0.4)  # slight delay so dashboard renders each step

        # If abort triggered — stop agent
        if correction_result and correction_result.get("should_abort"):
            console.print(f"\n[red]ABORT triggered at step {step_num}[/red]")
            console.print(correction_result.get("diagnosis", ""))
            break

    # Generate certificate
    cert = engine.generate_certificate(
        scores=scores,
        total_steps=len(step_outputs),
        drift_count=len(interceptor.get_drift_events()),
    )

    # Push to dashboard
    if dashboard_available:
        push("complete_event", cert.to_dict())

    return {
        "events":      all_events,
        "scores":      scores,
        "certificate": cert,
        "correction_summary": engine.summary(),
        "final_output": agent_state.get("final_output", ""),
    }


def print_run_results(label: str, results: dict) -> None:
    cert   = results["certificate"]
    c_sum  = results["correction_summary"]

    table = Table(title=f"Results — {label}", show_header=True)
    table.add_column("Step",       justify="center", style="cyan")
    table.add_column("Score",      justify="center")
    table.add_column("Drift?",     justify="center")
    table.add_column("Correction")

    for item in results["events"]:
        ev   = item["event"]
        corr = item["correction"]
        drift_s = f"[red]{ev.drift_type}[/red]" if ev.drift_detected else "[green]No[/green]"
        corr_s  = corr["tier"].value if corr else "—"
        score_s = f"[red]{ev.score:.3f}[/red]" if ev.drift_detected else f"[green]{ev.score:.3f}[/green]"
        table.add_row(str(ev.step_num), score_s, drift_s, corr_s)

    console.print(table)
    console.print(f"\n[cyan]Certificate:[/cyan]")
    console.print(cert.display())
    console.print(f"\n  Corrections total : {c_sum['corrections_total']}")
    console.print(f"  Checkpoints saved : {c_sum['checkpoints_saved']}")
    console.print(f"  Aborted           : {c_sum['aborted']}")


def main():
    console.print(Panel.fit(
        "[bold cyan]DriftWatch — Day 3 Integration Test[/bold cyan]\n"
        "Tests: Correction Engine + Dashboard SSE Pipeline\n"
        "Tip: Start dashboard first → python -m dashboard.app",
        title="DAY 3"
    ))

    if not os.getenv("GROQ_API_KEY") or \
       os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        console.print("[red]GROQ_API_KEY not set. Add it to .env[/red]")
        sys.exit(1)

    task = (
        "Research the environmental impact of lithium mining on groundwater "
        "quality in South America and write exactly 3 specific policy "
        "recommendations that governments can implement immediately."
    )

    console.print("\n[bold]Run: Full pipeline with drift injection at step 3[/bold]")
    try:
        results = run_with_correction(task, inject_drift_at=3)
        print_run_results("Drift injected at step 3", results)

        cert = results["certificate"]
        if cert.corrections_applied > 0:
            console.print(f"\n[green]SUCCESS: {cert.corrections_applied} correction(s) fired[/green]")
        else:
            console.print("[yellow]No corrections fired — check drift injection[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback; traceback.print_exc()

    console.print("\n[green]Day 3 complete.[/green]")
    console.print("  Next: python run_day4.py (demo scenarios + benchmark)")


if __name__ == "__main__":
    main()
