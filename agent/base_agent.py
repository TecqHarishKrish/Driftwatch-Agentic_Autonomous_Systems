"""
DriftWatch | agent/base_agent.py
LangGraph 5-step agent with structured JSON reasoning.
"""
import os, json
from typing import TypedDict, List, Optional, Annotated
import operator
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

def get_llm(temp=0.3):
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=temp,
        max_tokens=300,
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
    """Strip markdown code fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(lines).strip()
    return raw

def planner_node(state: AgentState) -> dict:
    llm  = get_llm(0.2)
    resp = llm.invoke([
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
    resp = llm.invoke([
        SystemMessage(content=EXECUTOR_SYS),
        HumanMessage(content=
            f"Main task: {state['task']}\n"
            f"Step {idx+1}/5: {desc}{prev}\n"
            f"Return JSON:"
        )
    ])
    raw = _clean_json(resp.content)

    # Default fallback
    parsed = {
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

    print(f"\n[Agent] Step {idx+1}/5 | {parsed['current_focus'][:70]}")
    return {"step_outputs": [parsed], "current_step": idx + 1}

def should_continue(state: AgentState) -> str:
    return "synthesize" if state["current_step"] >= len(state["plan"]) else "execute"

def synthesizer_node(state: AgentState) -> dict:
    outputs = "\n\n".join(
        f"Step {o['step_num']}: {o.get('step_output','')}"
        for o in state.get("step_outputs", [])
    )
    llm  = get_llm(0.2)
    resp = llm.invoke([
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

def run_agent(task: str) -> AgentState:
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
    return graph.invoke(state)