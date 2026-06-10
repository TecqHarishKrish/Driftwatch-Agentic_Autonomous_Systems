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

DECOMPOSE_PROMPT = """Break this task into exactly 4 specific sub-goals.
Return ONLY a JSON array of 4 strings.
Each sub-goal: 1 sentence, specific, directly related to the task.
No markdown, no extra text — just the JSON array.
Task: {task}"""


def decompose_goal(task: str) -> List[str]:
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL","llama-3.1-70b-versatile"),
            messages=[{"role":"user","content":DECOMPOSE_PROMPT.format(task=task)}],
            max_tokens=400, temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        subgoals = json.loads(raw)
        if isinstance(subgoals, list) and len(subgoals) >= 2:
            return subgoals[:5]
    except Exception as e:
        print(f"[GoalAnchor] decompose failed: {e}")
    return [
        f"Understand and analyze the requirements of: {task[:80]}",
        f"Research and gather relevant information for the task",
        f"Process and synthesize the gathered information",
        f"Produce the specific output as requested in the task",
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

    def to_dict(self):
        return {"task": self.task, "subgoals": self.subgoals, "anchored": self._anchored}
