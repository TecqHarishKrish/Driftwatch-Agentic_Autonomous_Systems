"""
DriftWatch | agent/base_agent.py
LangGraph 5-step agent with structured JSON reasoning.
"""
import os, json
from typing import TypedDict, List, Optional, Annotated, Any, Callable, cast
import operator
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

def get_llm(temp=0.3):
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "groq/compound"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=temp,
        max_tokens=1024,
    )

class AgentState(TypedDict):
    task:          str
    plan:          List[str]
    current_step:  int
    step_outputs:  Annotated[List[dict], operator.add]
    final_output:  Optional[str]
    is_complete:   bool
    drift_events:  Annotated[List[dict], operator.add]

PLANNER_SYS = """You are a task planner. Break the task into exactly 5 sequential steps.
Return ONLY a JSON array of 5 strings like this:
["Step 1 description", "Step 2 description", "Step 3 description", "Step 4 description", "Step 5 description"]
No markdown. No explanation. Just the JSON array."""

EXECUTOR_SYS = """You are an AI agent executing one step of a task.
Return ONLY valid JSON with exactly these keys:
{
  "current_focus": "what you are doing this step (1 sentence)",
  "connection_to_goal": "how this step serves the main task (1 sentence)",
  "next_action": "what you will do next step (1 sentence)",
  "step_output": "the actual work produced this step (2-3 sentences)"
}
Return only JSON. No markdown. No explanation."""

SYNTH_SYS = """Write a final response that directly answers the original task.
Be specific and concise. Use the step outputs provided."""

def _clean_json(raw: str) -> str:
    """Strip thinking blocks and markdown code fences if present."""
    import re
    raw = re.sub(r'<think>.*?(?:</think>|$)', '', raw, flags=re.DOTALL).strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part_clean = part.strip()
            if part_clean.startswith("json"):
                part_clean = part_clean[4:].strip()
            if part_clean.startswith("[") or part_clean.startswith("{"):
                raw = part_clean
                break
        else:
            raw = parts[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
    return raw.strip()

def invoke_with_retry(llm, messages):
    try:
        return llm.invoke(messages)
    except Exception as e:
        err_str = str(e).lower()
        if "rate limit" in err_str or "429" in err_str or "ratelimit" in err_str:
            print("[Groq] Rate limit hit. Sleeping 10 seconds before retry...")
            import time
            time.sleep(10)
            try:
                return llm.invoke(messages)
            except Exception as e2:
                print(f"[Groq] Retry failed: {e2}")
                raise e2
        raise e

def planner_node(state: AgentState) -> dict:
    llm  = get_llm(0.2)
    resp = invoke_with_retry(llm, [
        SystemMessage(content=PLANNER_SYS),
        HumanMessage(content=f"Task: {state['task']}")
    ])
    raw = _clean_json(resp.content)

    plan = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            plan = [str(s) for s in parsed][:5]
        elif isinstance(parsed, dict):
            # Sometimes model returns {"steps": [...]}
            for key in parsed:
                if isinstance(parsed[key], list):
                    plan = [str(s) for s in parsed[key]][:5]
                    break
    except Exception:
        pass

    # Fallback: split by newlines
    if not plan or len(plan) < 3:
        lines = [l.strip().lstrip("0123456789.-) \"'")
                 for l in raw.split("\n") if l.strip()]
        plan = [l for l in lines if len(l) > 5][:5]

    # Final fallback
    while len(plan) < 5:
        plan.append(f"Continue executing: {state['task'][:50]}")

    print(f"\n[Agent] Plan ({len(plan)} steps):")
    for i, s in enumerate(plan, 1):
        print(f"  {i}. {str(s)[:70]}")

    return {"plan": plan, "current_step": 0, "is_complete": False}

def executor_node(state: AgentState) -> dict:
    idx  = state["current_step"]
    plan = state["plan"]
    desc = str(plan[idx]) if idx < len(plan) else "Finalize task"

    prev = ""
    if state.get("step_outputs"):
        last = state["step_outputs"][-1]
        prev_out = last.get("step_output", "")
        if prev_out:
            prev = f"\nPrevious step output: {str(prev_out)[:150]}"

    llm  = get_llm(0.4)
    resp = invoke_with_retry(llm, [
        SystemMessage(content=EXECUTOR_SYS),
        HumanMessage(content=
            f"Main task: {state['task']}\n"
            f"Step {idx+1}/{len(plan)}: {desc}{prev}\n"
            f"Return JSON:"
        )
    ])
    raw = _clean_json(resp.content)

    # Default fallback
    parsed: dict[str, Any] = {
        "current_focus":      f"Executing step {idx+1}: {desc[:60]}",
        "connection_to_goal": f"Advancing the main task",
        "next_action":        "Proceed to next step",
        "step_output":        raw[:200] if raw else "Step completed",
    }

    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            for k in ["current_focus","connection_to_goal","next_action","step_output"]:
                if k in result and result[k]:
                    parsed[k] = str(result[k])
    except Exception:
        pass

    parsed["step_num"]  = idx + 1
    parsed["step_desc"] = desc

    print(f"\n[Agent] Step {idx+1}/{len(plan)} | {parsed['current_focus'][:70]}")
    return {"step_outputs": [parsed], "current_step": idx + 1}

def should_continue(state: AgentState) -> str:
    return "synthesize" if state["current_step"] >= len(state["plan"]) else "execute"

def synthesizer_node(state: AgentState) -> dict:
    outputs = "\n\n".join(
        f"Step {o['step_num']}: {o.get('step_output','')}"
        for o in state.get("step_outputs", [])
    )
    llm  = get_llm(0.2)
    resp = invoke_with_retry(llm, [
        SystemMessage(content=SYNTH_SYS),
        HumanMessage(content=
            f"Task: {state['task']}\n\n"
            f"Work done:\n{outputs}\n\n"
            f"Final response:"
        )
    ])
    print(f"\n[Agent] Complete. Output: {len(resp.content)} chars")
    return {"final_output": resp.content.strip(), "is_complete": True}

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner",    planner_node)
    g.add_node("execute",    executor_node)
    g.add_node("synthesize", synthesizer_node)
    g.set_entry_point("planner")
    g.add_edge("planner", "execute")
    g.add_conditional_edges(
        "execute", should_continue,
        {"execute": "execute", "synthesize": "synthesize"}
    )
    g.add_edge("synthesize", END)
    return g.compile()

def run_agent(task: str, session_id: Optional[str] = None, sse_push_fn: Optional[Callable] = None) -> AgentState:
    if session_id is not None:
        # Delegate to run_with_driftwatch if session_id is provided
        from core.goal_anchor import GoalAnchor
        from core.workflow_session import WorkflowSession
        # Use simple anchors fallback if none are stored yet
        try:
            ws_data = WorkflowSession.load(session_id)
            anchors = ws_data.get("goal_anchors", [])
            sensitivity = ws_data.get("sensitivity", 0.75)
        except Exception:
            anchors = [task]
            sensitivity = 0.75
        
        res = run_with_driftwatch(task, anchors, sensitivity, session_id, sse_push_fn)
        state: AgentState = {
            "task": task,
            "plan": [],
            "current_step": 5,
            "step_outputs": [],
            "final_output": res["output"],
            "is_complete": True,
            "drift_events": [],
        }
        return state

    print(f"\n{'='*60}")
    print(f"  Agent Task: {task[:80]}")
    print(f"{'='*60}")
    graph = build_graph()
    state: AgentState = {
        "task":         task,
        "plan":         [],
        "current_step": 0,
        "step_outputs": [],
        "final_output": None,
        "is_complete":  False,
        "drift_events": [],
    }
    return cast(AgentState, graph.invoke(state))

DRIFT_INJECTIONS = {
    "research": {
        3: {
            "current_focus":      "Analyzing global EV market adoption and battery demand trends",
            "connection_to_goal": "EV demand is the reason lithium mining is expanding globally",
            "next_action":        "Look at EV subsidy programs — the real driver of lithium demand",
            "step_output":        "Global EV sales reached 14M units in 2023, up 35%. Tesla produced "
                                  "1.8M vehicles. EV market projected at $823B by 2030 via subsidies.",
        },
    },
    "coding": {
        3: {
            "current_focus":      "Adding OAuth2 social login with Google, GitHub, and Facebook providers",
            "connection_to_goal": "OAuth2 extends the authentication module beyond the JWT requirement",
            "next_action":        "Implement Google OAuth2 callback handler and session management",
            "step_output":        "Adding OAuth2 support requiring flask-oauthlib, callback routes, "
                                  "session storage, and provider-specific client ID/secret config.",
        },
    },
    "legal": {
        3: {
            "current_focus":      "Researching Delaware C-corp incorporation and cap table structures",
            "connection_to_goal": "Corporate structure affects how liability flows in vendor contracts",
            "next_action":        "Compare Series A term sheet provisions across Silicon Valley VCs",
            "step_output":        "Delaware corps offer predictable case law. Standard Series A includes "
                                  "1x liquidation preference, anti-dilution, and board seats for lead investors.",
        },
    },
    "analytics": {
        3: {
            "current_focus":      "Building a PyTorch LSTM demand forecasting model from scratch",
            "connection_to_goal": "ML forecasting could eventually improve inventory decisions",
            "next_action":        "Tune hyperparameters and set up GPU training on AWS SageMaker",
            "step_output":        "LSTM architecture: 2 layers, 128 hidden units, dropout 0.2. Training on "
                                  "3 years of SKU-level data. Target MAPE under 8% before deployment.",
        },
    },
    "writing": {
        3: {
            "current_focus":      "Developing a 12-month omnichannel brand rebranding strategy",
            "connection_to_goal": "Rebrand launch could include the new filtration product announcement",
            "next_action":        "Draft social media calendar across Instagram, TikTok, and LinkedIn",
            "step_output":        "Rebrand pillars: sustainability, adventure, trust. Q1 influencer "
                                  "partnerships with 50 micro-creators. Budget $2.4M across channels.",
        },
    },
}

def get_scenario_type(task: str) -> str:
    task_lower = task.lower()
    if "lithium" in task_lower or "groundwater" in task_lower or "gdpr" in task_lower or "compliance" in task_lower or "diabetes" in task_lower:
        return "research"
    if "jwt" in task_lower or "bug" in task_lower or "python" in task_lower:
        return "coding"
    if "nda" in task_lower or "liability" in task_lower:
        return "legal"
    if "inflation" in task_lower or "sales" in task_lower or "bookstore" in task_lower:
        return "analytics"
    if "photosynthesis" in task_lower or "hiking" in task_lower or "hikers" in task_lower or "filtration" in task_lower:
        return "writing"
    return "research"

def run_with_driftwatch(task: str, anchors: List[str], sensitivity: float,
                        session_id: Optional[str] = None, sse_push_fn: Optional[Callable] = None) -> dict:
    from core.embedder import Embedder
    from core.drift_detector import DriftDetector, Phase
    from core.correction_engine import CorrectionEngine
    from agent.reasoning_extractor import ReasoningExtractor
    from agent.step_interceptor import StepInterceptor, dispatch_correction_with_gate
    from core.workflow_session import WorkflowSession
    import core.drift_detector

    # Adjust thresholds globally for the detector
    ratio = sensitivity / 0.75
    core.drift_detector.THRESH = {
        Phase.EXPLORE:  round(0.20 * ratio, 3),
        Phase.EXPLOIT:  round(0.28 * ratio, 3),
        Phase.CONCLUDE: round(0.35 * ratio, 3),
    }

    emb = Embedder(verbose=False)
    detector = DriftDetector(embedder=emb, verbose=True)
    detector.anchor_goal(task, anchors)
    extractor = ReasoningExtractor(embedder=emb)
    
    interceptor = StepInterceptor(
        detector=detector,
        extractor=extractor,
        event_queue=None,
        verbose=True
    )
    interceptor.anchor(task, anchors)
    engine = CorrectionEngine(task=task, verbose=True)

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

    if session_id:
        try:
            from core.workflow_session import WorkflowSession, save_session_dict
            ws_data = WorkflowSession.load(session_id)
            ws_data["total_steps"] = len(state["plan"])
            save_session_dict(session_id, ws_data)
        except Exception as e:
            print(f"[DriftWatch] Warning: could not save total steps: {e}")

    if sse_push_fn:
        sse_push_fn("agent_start", {
            "total_steps": len(state["plan"]),
            "goals": anchors
        })

    raw_step_outputs = []

    while state["current_step"] < len(state["plan"]):
        step_update = executor_node(state)
        state["step_outputs"].extend(step_update["step_outputs"])
        state["current_step"] = step_update["current_step"]

        latest_step_output = state["step_outputs"][-1]
        sn = latest_step_output["step_num"]

        # Inject drift at step 3 if scenario matches
        scenario_type = get_scenario_type(task)
        injections = DRIFT_INJECTIONS.get(scenario_type, {})
        if sn in injections:
            print(f"[Agent] Injecting drift for {scenario_type} at step {sn}")
            latest_step_output.update(injections[sn])

        # Intercept step
        ev = interceptor.intercept(sn, latest_step_output, len(state["plan"]))
        
        # Save raw output (with drift but before correction)
        raw_step_outputs.append(dict(latest_step_output))

        # Checkpoint if clean
        if not ev.drift_detected and ev.score > 0.72:
            engine.save_checkpoint(sn, ev.score, latest_step_output)

        # Log StepRecord
        if session_id:
            try:
                from core.workflow_session import WorkflowSession, save_session_dict
                ws_data = WorkflowSession.load(session_id)
                step_rec = {
                    "step_number": sn,
                    "action": latest_step_output.get("current_focus", ""),
                    "drift_score": float(ev.score),
                    "momentum": float(ev.momentum),
                    "drift_type": str(ev.drift_type),
                    "timestamp": __import__('time').time()
                }
                ws_data.setdefault("steps", []).append(step_rec)
                save_session_dict(session_id, ws_data)

                if sse_push_fn:
                    sse_push_fn("step_update", step_rec)
            except Exception as e:
                print(f"[DriftWatch] Warning: could not log step record: {e}")

        # Correct drift if needed
        corr = None
        if ev.correction_needed:
            depth = max(0.0, ev.threshold - ev.score)
            if   depth < 0.08: tier = 1
            elif depth < 0.18: tier = 2
            elif depth < 0.30: tier = 3
            else:              tier = 4

            # Budget check
            cp = engine.last_checkpoint()
            if cp:
                retries = engine.retry_map.get(cp.step_num, 0)
                if retries >= engine.MAX_RETRIES:
                    tier = min(tier + 1, 4)

            # Gate correction check
            status = "applied"
            if session_id:
                status = dispatch_correction_with_gate(
                    tier=tier,
                    drift_type=ev.drift_type,
                    session_id=session_id,
                    step_number=sn,
                    sse_push_fn=sse_push_fn
                )

            if status == "applied":
                corr = engine.correct(
                    step_num=sn,
                    score=ev.score,
                    threshold=ev.threshold,
                    drift_type=ev.drift_type,
                    context=latest_step_output.get("step_output", "")
                )
                if corr.get("should_rollback"):
                    rollback_step = corr["rollback_to_step"]
                    state["current_step"] = rollback_step
                    state["step_outputs"] = state["step_outputs"][:rollback_step]
                elif corr.get("should_abort"):
                    break
                else:
                    latest_step_output["step_output"] = corr["new_context"]
            else:
                # rejected
                pass

        __import__('time').sleep(0.5)

    # Synthesis
    synth_state = cast(AgentState, dict(state))
    synth_update = synthesizer_node(synth_state)
    final_output = synth_update.get("final_output", "")

    raw_synth_state = cast(AgentState, dict(state))
    raw_synth_state["step_outputs"] = raw_step_outputs
    raw_synth_update = synthesizer_node(raw_synth_state)
    raw_output = raw_synth_update.get("final_output", "")

    return {
        "output":     final_output,
        "raw_output": raw_output
    }