"""
=============================================================
  DriftWatch | run_day1.py
  DAY 1 — INTEGRATION TEST
  Purpose : Runs all Day 1 modules together to verify
            the foundation works end-to-end.
  Usage   : python run_day1.py
=============================================================
"""
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def run_day1_verification():
    console.print(Panel.fit(
        "[bold cyan]DriftWatch — Day 1 Integration Test[/bold cyan]\n"
        "Tests: Embedder → Goal Anchor → Drift Detector (no agent calls)",
        title="DAY 1"
    ))

    passed = []
    failed = []

    # ── Test 1: Embedder loads and runs ──────────────────────────────────────
    console.print("\n[yellow]Test 1:[/yellow] Embedder loads and benchmarks...")
    try:
        from core.embedder import Embedder
        emb = Embedder(verbose=False)
        v1 = emb.embed("Research groundwater contamination from lithium mining")
        v2 = emb.embed("Analyze electric vehicle market trends globally")
        sim = emb.similarity(v1, v2)
        assert 0.0 <= sim <= 1.0, "Similarity out of range"
        assert emb.avg_latency_ms < 500, f"Too slow: {emb.avg_latency_ms}ms"
        console.print(f"  [green]PASS[/green]  similarity={sim:.3f}  latency={emb.avg_latency_ms:.1f}ms")
        passed.append("Embedder")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        failed.append("Embedder")

    # ── Test 2: Drift detector anchors goal ───────────────────────────────────
    console.print("\n[yellow]Test 2:[/yellow] Drift detector anchors goal...")
    try:
        from core.drift_detector import DriftDetector, Phase
        from core.embedder import Embedder as E2
        detector = DriftDetector(embedder=E2(verbose=False), verbose=False)
        detector.anchor_goal(
            task="Research lithium mining impacts on water quality and write 3 regulations",
            subgoals=[
                "Find peer-reviewed studies on lithium extraction groundwater effects",
                "Analyze contamination data from mining sites",
                "Draft three specific water quality regulations",
            ]
        )
        assert detector.goal_state is not None
        assert len(detector.goal_state.subgoal_vectors) == 3
        console.print(f"  [green]PASS[/green]  goal anchored with 3 sub-goals")
        passed.append("Goal Anchoring")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        failed.append("Goal Anchoring")

    # ── Test 3: Drift detector evaluates steps ────────────────────────────────
    console.print("\n[yellow]Test 3:[/yellow] Drift detection on on-track vs drifted steps...")
    try:
        on_track = "Reviewing 12 studies on arsenic contamination in lithium brine mining areas near groundwater sources"
        drifted  = "Analyzing global electric vehicle adoption rates and government subsidy programs worldwide"

        r_good = detector.evaluate_step(1, on_track,  Phase.EXPLOIT)
        r_bad  = detector.evaluate_step(2, drifted,   Phase.EXPLOIT)

        assert r_good.score > r_bad.score, \
            f"On-track ({r_good.score:.3f}) should score higher than drifted ({r_bad.score:.3f})"
        console.print(
            f"  [green]PASS[/green]  on-track={r_good.score:.3f}  "
            f"drifted={r_bad.score:.3f}  "
            f"drift_detected={r_bad.is_drift}"
        )
        passed.append("Drift Detection")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        failed.append("Drift Detection")

    # ── Test 4: Drift classifier ──────────────────────────────────────────────
    console.print("\n[yellow]Test 4:[/yellow] Drift classifier assigns correct types...")
    try:
        from core.drift_classifier import classify_drift_type, DriftType
        t1 = classify_drift_type(0.90, 0.68,  0.00, "on track text")
        t2 = classify_drift_type(0.58, 0.68, -0.02, "also expanding scope additionally")
        t3 = classify_drift_type(0.29, 0.68, -0.10, "completely different topic starting over")

        assert t1 == DriftType.NONE,             f"Expected NONE got {t1}"
        assert t2 == DriftType.SCOPE_CREEP,      f"Expected SCOPE_CREEP got {t2}"
        assert t3 == DriftType.CONTEXT_COLLAPSE, f"Expected CONTEXT_COLLAPSE got {t3}"
        console.print(f"  [green]PASS[/green]  NONE / SCOPE_CREEP / CONTEXT_COLLAPSE all correct")
        passed.append("Drift Classifier")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        failed.append("Drift Classifier")

    # ── Test 5: Reasoning extractor ───────────────────────────────────────────
    console.print("\n[yellow]Test 5:[/yellow] Reasoning extractor builds composite vector...")
    try:
        from agent.reasoning_extractor import ReasoningExtractor
        ext = ReasoningExtractor()
        trace = ext.extract(1, {
            "current_focus":     "Reviewing lithium mining studies",
            "connection_to_goal":"Directly builds evidence for groundwater impact analysis",
            "next_action":       "Compile contamination statistics",
            "step_output":       "Found 12 papers confirming arsenic contamination above WHO limits",
        })
        assert trace.composite_vector is not None
        assert trace.composite_vector.shape == (384,)
        console.print(f"  [green]PASS[/green]  composite vector shape={trace.composite_vector.shape}")
        passed.append("Reasoning Extractor")
    except Exception as e:
        console.print(f"  [red]FAIL[/red]  {e}")
        failed.append("Reasoning Extractor")

    # ── Summary ───────────────────────────────────────────────────────────────
    table = Table(title="\nDay 1 Results", show_header=True)
    table.add_column("Module", style="cyan")
    table.add_column("Status")

    for p in passed:
        table.add_row(p, "[green]PASS[/green]")
    for f in failed:
        table.add_row(f, "[red]FAIL[/red]")

    console.print(table)

    if failed:
        console.print(f"\n[red]  {len(failed)} tests failed — fix before Day 2[/red]")
        sys.exit(1)
    else:
        console.print(f"\n[green]  ALL {len(passed)} TESTS PASSED — Day 1 complete[/green]")
        console.print("  Next: run_day2.py (requires Groq API key)\n")


if __name__ == "__main__":
    run_day1_verification()
