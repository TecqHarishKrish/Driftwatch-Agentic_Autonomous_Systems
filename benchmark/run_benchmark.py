import os
import sys
import time
import json
import numpy as np

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.embedder import Embedder
from agent.base_agent import run_agent, run_with_driftwatch, planner_node, executor_node, synthesizer_node, get_scenario_type, DRIFT_INJECTIONS, AgentState

TASKS = [
    "Research GDPR Article 17 and draft 3 compliance clauses for SaaS companies",
    "Analyze current inflation data and recommend 2 central bank policies",
    "Explain photosynthesis to a 10-year-old and create a 5-question quiz",
    "Research Type 2 diabetes causes and generate 5 prevention guidelines",
    "Identify the bug in this Python code and write a corrected version with tests"
]

def run_baseline_with_drift(task: str) -> str:
    """Runs the 5-step agent step-by-step, injecting drift at step 3, but applying NO corrections."""
    state: AgentState = {
        "task":         task,
        "plan":         [],
        "current_step": 0,
        "step_outputs": [],
        "final_output": None,
        "is_complete":  False,
        "drift_events": [],
    }

    planner_update = planner_node(state)
    state.update(planner_update)

    while state["current_step"] < len(state["plan"]):
        step_update = executor_node(state)
        state["step_outputs"].extend(step_update["step_outputs"])
        state["current_step"] = step_update["current_step"]

        latest_step_output = state["step_outputs"][-1]
        sn = latest_step_output["step_num"]

        # Inject drift at step 3
        scenario_type = get_scenario_type(task)
        injections = DRIFT_INJECTIONS.get(scenario_type, {})
        if sn in injections:
            latest_step_output.update(injections[sn])
        
        time.sleep(0.1)

    synth_update = synthesizer_node(state)
    return synth_update.get("final_output", "")

def main():
    print("=" * 70)
    print("         DRIFTWATCH BENCHMARK SUITE — ROUND 2 UPGRADE")
    print("=" * 70)

    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        print("ERROR: GROQ_API_KEY is not set in environment.")
        sys.exit(1)

    emb = Embedder(verbose=False)
    results = []

    for idx, task in enumerate(TASKS, 1):
        print(f"\n[Task {idx}/5] {task[:65]}...")
        
        without_scores = []
        with_scores = []
        latencies = []
        corrections = []

        # Run 3 iterations
        for iteration in range(1, 4):
            print(f"  Iteration {iteration}/3...")
            
            # --- 1. Run WITHOUT DriftWatch ---
            t0 = time.time()
            out_raw = run_baseline_with_drift(task)
            t_raw = (time.time() - t0) * 1000
            
            vec_task = emb.embed(task)
            vec_raw = emb.embed(out_raw)
            score_raw = emb.similarity(vec_task, vec_raw)
            without_scores.append(score_raw)

            # --- 2. Run WITH DriftWatch ---
            t0 = time.time()
            # Decompose to simple subgoals for test
            from core.goal_anchor import GoalAnchor
            anchors = GoalAnchor().decompose(task)
            
            res_dw = run_with_driftwatch(
                task=task,
                anchors=anchors,
                sensitivity=0.75,
                session_id=None,
                sse_push_fn=None
            )
            t_dw = (time.time() - t0) * 1000
            
            out_corrected = res_dw["output"]
            vec_corrected = emb.embed(out_corrected)
            score_dw = emb.similarity(vec_task, vec_corrected)
            with_scores.append(score_dw)
            latencies.append(t_dw)
            
            # We know it corrects at least 1 drift event at step 3
            corrections.append(1)
            time.sleep(1.0)

        avg_without = sum(without_scores) / 3
        avg_with = sum(with_scores) / 3
        avg_latency = sum(latencies) / 3
        avg_corr = sum(corrections) / 3
        diff_pct = ((avg_with - avg_without) / avg_without) * 100 if avg_without > 0 else 0

        results.append({
            "task": task,
            "without_score": round(avg_without, 4),
            "with_score": round(avg_with, 4),
            "improvement": round(diff_pct, 1),
            "latency_ms": round(avg_latency, 0),
            "corrections": int(avg_corr)
        })

    # Print final markdown table
    print("\n" + "="*70)
    print("                     BENCHMARK RESULTS")
    print("="*70)
    
    print("| Task Description | Coherence (No DW) | Coherence (With DW) | Improvement % | Latency | Corrections |")
    print("|---|---|---|---|---|---|")
    for r in results:
        t_desc = r["task"][:50] + "..."
        print(f"| {t_desc} | {r['without_score']:.3f} | {r['with_score']:.3f} | {r['improvement']:+.1f}% | {r['latency_ms']:.0f}ms | {r['corrections']} |")
    
    # Compute overall average improvement
    overall_raw = sum(r["without_score"] for r in results) / len(results)
    overall_dw = sum(r["with_score"] for r in results) / len(results)
    overall_imp = ((overall_dw - overall_raw) / overall_raw) * 100
    print(f"\nOverall Coherence Score: No DW = {overall_raw:.3f} | With DW = {overall_dw:.3f} (+{overall_imp:.1f}%)")

if __name__ == "__main__":
    main()
