"""
=============================================================
  DriftWatch | core/goal_anchor.py  [REBUILT]
  Decomposes task into sub-goals via Groq LLM, embeds all.
=============================================================
"""
import os, json
from typing import List
from dotenv import load_dotenv
load_dotenv()

DECOMPOSE_PROMPT = """You are an advanced AI safety agent decomposition system. Your task is to analyze the user's high-level task and break it down into exactly 4 or 5 specific, actionable, and concrete sub-goals.

CRITICAL INSTRUCTIONS:
- Do NOT generate generic steps like "Research and gather relevant information", "Process the data", "Synthesize findings", or "Produce the requested output".
- Each sub-goal must be directly derived from the user's input, mentioning the specific topics, cybersecurity concepts, analytical steps, or report requirements mentioned in the task.
- Each sub-goal must be exactly 1 clear, concise sentence.
- Return ONLY a JSON array of strings. Do NOT include markdown code blocks, conversational introductions, or notes. Just return the JSON array.

Task: {task}"""


def decompose_goal(task: str) -> List[str]:
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL","groq/compound"),
            messages=[{"role":"user","content":DECOMPOSE_PROMPT.format(task=task)}],
            max_tokens=1024, temperature=0.1,
        )
        content = resp.choices[0].message.content
        if content is None:
            raise ValueError("Groq returned empty or None content.")
        raw = content.strip()
        import re
        raw = re.sub(r'<think>.*?(?:</think>|$)', '', raw, flags=re.DOTALL).strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        subgoals = json.loads(raw)
        if isinstance(subgoals, list) and len(subgoals) >= 2:
            return [s.strip() for s in subgoals[:5] if s.strip()]
    except Exception as e:
        print(f"[GoalAnchor] decompose failed: {e}")

    # Specific Heuristic Fallback Parser
    import re
    # Split task by clauses to capture task-specific instructions
    parts = [p.strip() for p in re.split(r'[,;.]| and | or ', task) if len(p.strip()) > 8]
    
    # Filter and format clauses into goals
    goals = []
    for p in parts:
        # Capitalize and clean punctuation
        p = p[0].upper() + p[1:] if p else ""
        if p.endswith("."):
            p = p[:-1]
        
        # Avoid generic sentences
        if not any(g in p.lower() for g in ["research information", "process", "gather info", "produce output"]):
            goals.append(p)

    # If the parser identified distinct task-specific statements, return them
    if len(goals) >= 3:
        return goals[:5]

    # Otherwise, extract high-value keywords to construct targeted goals
    words = [w for w in re.findall(r'\b\w+\b', task) if len(w) > 4]
    keywords = " ".join(words[:4]) if words else "the requested task"
    
    return [
        f"Identify key parameters and requirements regarding {keywords}.",
        f"Analyze structural factors and components associated with {keywords}.",
        f"Evaluate safety metrics and risk thresholds for {keywords}.",
        f"Deliver structured recommendations and final report for {keywords}."
    ]



class GoalAnchor:
    def __init__(self, embedder=None):
        from core.embedder import Embedder
        self.emb = embedder or Embedder(verbose=False)
        self.task = ""
        self.subgoals: List[str] = []
        self.task_vector = None
        self.subgoal_vectors: List = []
        self._anchored = False

    def anchor(self, task: str) -> dict:
        print(f"[GoalAnchor] Decomposing task...")
        self.task     = task
        self.subgoals = decompose_goal(task)
        print(f"[GoalAnchor] Embedding {len(self.subgoals)+1} vectors...")
        all_texts = [task] + self.subgoals
        all_vecs  = self.emb.embed_batch(all_texts)
        self.task_vector     = all_vecs[0]
        self.subgoal_vectors = all_vecs[1:]
        self._anchored = True
        print(f"[GoalAnchor] Anchored. Sub-goals:")
        for i, sg in enumerate(self.subgoals, 1):
            print(f"  {i}. {sg[:80]}")
        return {"task": task, "subgoals": self.subgoals, "vectors": len(all_vecs)}

    @property
    def all_vectors(self):
        return [self.task_vector] + self.subgoal_vectors

    def decompose(self, task: str) -> List[str]:
        return decompose_goal(task)

    def to_dict(self):
        return {"task": self.task, "subgoals": self.subgoals, "anchored": self._anchored}
