"""
=============================================================
  DriftWatch | demos/demo_research.py
  DAY 4 — FILE 1
  Purpose : Polished demo scenario 1 — Research task
            Shows an agent drifting from "write water quality
            regulations" → "EV market analysis", then
            DriftWatch detecting and correcting it.
  Usage   : python -m demos.demo_research
=============================================================
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()


TASK = (
    "Research the environmental impact of lithium mining on groundwater "
    "quality and write exactly 3 specific, enforceable policy "
    "regulations that South American governments can implement."
)

# Steps that are injected at specific positions to simulate drift
DRIFT_INJECTIONS = {
    3: {
        "current_focus":      "Analyzing global EV market adoption and battery demand trends",
        "connection_to_goal": "Growing EV demand is the reason lithium mining is expanding",
        "next_action":        "Look at government EV subsidy programs and Tesla production",
        "step_output":        (
            "Global EV sales reached 14 million units in 2023, a 35% increase. "
            "Tesla produced 1.8M vehicles. The EV market is projected to reach "
            "$823 billion by 2030 driven by government subsidies and falling battery costs."
        ),
    },
    4: {
        "current_focus":      "Reviewing EV subsidy legislation in USA, EU, and China",
        "connection_to_goal": "Government policy on EVs shapes the lithium demand that drives mining",
        "next_action":        "Summarize IRA tax credits and European Green Deal",
        "step_output":        (
            "The US Inflation Reduction Act provides $7,500 EV tax credits. "
            "The EU Green Deal mandates 100% zero-emission vehicles by 2035. "
            "China provides $5,000 direct subsidies per EV sold domestically."
        ),
    },
}


def run_research_demo(verbose: bool = True) -> dict:
    """
    Run the research task demo with intentional drift at steps 3-4.
    Returns full results dict including certificate and corrected output.
    """
    from core.embedder import Embedder
    from core.drift_detector import DriftDetector
    from core.goal_anchor import GoalAnchor
    from core.correction_engine import CorrectionEngine
    from agent.reasoning_extractor import ReasoningExtractor
    from agent.step_interceptor import StepInterceptor
    from agent.base_agent import run_agent

    print("\n" + "=" * 62)
    print("  DEMO 1 — Research Task: Lithium Mining Policy Brief")
    print("=" * 62)
    print(f"\n  Task: {TASK[:90]}...")
    print(f"\n  DriftWatch will detect when the agent drifts from")
    print(f"  'water quality regulations' → 'EV market analysis'")
    print(f"  and correct autonomously.\n")

    emb     = Embedder(verbose=False)
    anchor  = GoalAnchor(embedder=emb)
    a_res   = anchor.anchor(TASK)
    engine  = CorrectionEngine(task=TASK, verbose=verbose)
    ev_list = []

    detector   = DriftDetector(embedder=emb, verbose=verbose)
    detector.anchor_goal(TASK, a_res["subgoals"])
    extractor  = ReasoningExtractor(embedder=emb)
    interceptor = StepInterceptor(
        detector=detector, extractor=extractor,
        event_queue=ev_list, verbose=verbose,
    )
    interceptor.anchor(TASK, a_res["subgoals"])

    print("\n[Running agent...]\n")
    agent_state = run_agent(TASK)
    step_outputs = agent_state.get("step_outputs", [])

    events_out = []
    scores     = []

    for step_data in step_outputs:
        sn = step_data.get("step_num", len(events_out) + 1)

        # Inject drift at steps 3 and 4
        if sn in DRIFT_INJECTIONS:
            if verbose:
                print(f"\n  >>> Simulating drift at step {sn} <<<")
            step_data.update(DRIFT_INJECTIONS[sn])

        ev = interceptor.intercept(sn, step_data)
        scores.append(ev.score)

        if not ev.drift_detected and ev.score > 0.72:
            engine.save_checkpoint(sn, ev.score, step_data)

        corr = None
        if ev.correction_needed:
            corr = engine.correct(sn, ev.score, ev.threshold,
                                  ev.drift_type, step_data.get("step_output", ""))

        events_out.append({"step": sn, "event": ev, "correction": corr})
        time.sleep(0.2)

    cert = engine.generate_certificate(
        scores=scores,
        total_steps=len(step_outputs),
        drift_count=len(interceptor.get_drift_events()),
    )

    print("\n" + cert.display())

    # Print score table
    print("\n  Step-by-step coherence:")
    print(f"  {'Step':<6} {'Score':<8} {'Threshold':<10} {'Status':<20} {'Correction'}")
    print(f"  {'-'*65}")
    for item in events_out:
        sn   = item["step"]
        ev   = item["event"]
        corr = item["correction"]
        status = f"DRIFT:{ev.drift_type}" if ev.drift_detected else "OK"
        corr_s = corr["tier"].value if corr else "—"
        print(f"  {sn:<6} {ev.score:<8.3f} {ev.threshold:<10.2f} {status:<20} {corr_s}")

    final = agent_state.get("final_output", "")
    if final:
        print(f"\n  Final output preview:")
        print(f"  {final[:400]}{'...' if len(final) > 400 else ''}")

    return {
        "task":       TASK,
        "scores":     scores,
        "events":     events_out,
        "certificate": cert,
        "final_output": final,
        "drift_count": len(interceptor.get_drift_events()),
        "correction_count": engine.summary()["corrections_total"],
    }


if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY") or \
       os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        print("ERROR: Set GROQ_API_KEY in .env")
        sys.exit(1)
    run_research_demo(verbose=True)
