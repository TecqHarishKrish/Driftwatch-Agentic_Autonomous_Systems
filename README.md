# DriftWatch

**Real-time goal coherence monitoring for autonomous AI agents.**

Autonomous agents fail silently. By step 7 of 12, most have replaced
the original goal with a sub-goal — and nobody knows. DriftWatch detects
this in real time and corrects autonomously, without human interruption.

---

## The Problem

```
Task: "Research lithium mining water impacts → write 3 regulations"

Step 1: ✅ Reviewing hydrogeology papers          [score: 0.91]
Step 2: ✅ Analyzing contamination data           [score: 0.88]
Step 3: ⚠️  Expanding to battery technology       [score: 0.71]  ← drift starts
Step 4: 🔴 Writing about EV market trends         [score: 0.52]  ← GOAL SUBSTITUTION
Step 5: 🔴 Recommending EV subsidies              [score: 0.41]  ← wrong output
```

Without DriftWatch — nobody catches this. **Task fails silently.**

---

## The Solution

DriftWatch intercepts every agent step, embeds the structured reasoning,
computes cosine similarity vs the anchored goal, tracks momentum across
3 steps, and fires a tiered correction response — all in under 60ms/step.

```
Step 3: score=0.71 | momentum=-0.09 | SCOPE_CREEP detected
        → Correction Tier 1: goal re-injection
Step 4: score=0.86 | momentum=+0.15 | RECOVERED ✅
Step 5: score=0.88 | CONCLUDE phase | on track ✅
Final output: Correct 3-regulation policy brief
```

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_HANDLE/driftwatch
cd driftwatch
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env — add your free Groq API key from https://console.groq.com

# 3. Verify setup
python test_setup.py

# 4. Run Day 1 tests (no API key needed)
python run_day1.py

# 5. Run full pipeline (requires Groq key)
python run_day2.py
```

---

## Architecture

```
Task Input
    │
    ▼
[Goal Anchoring]     ← decompose → embed → store at t=0
    │
    ▼
[Agent Execution]    ← LangGraph 5-step agent (Groq LLM)
    │  (every step)
    ▼
[Step Interceptor]   ← extracts structured JSON reasoning
    │
    ▼
[Drift Detection]    ← cosine similarity + 3-step momentum
    │
    ▼
[Correction Engine]  ← 4-tier: nudge → re-inject → rollback → abort
    │
    ▼
[Dashboard + Audit]  ← live graph + event log + coherence certificate
    │
    ▼
Verified Output + Coherence Certificate
```

---

## File Structure

```
driftwatch/
├── core/
│   ├── embedder.py          DAY 1 — local embedding (free, <60ms)
│   ├── drift_detector.py    DAY 1 — cosine + momentum tracker
│   ├── drift_classifier.py  DAY 2 — scope/substitution/collapse
│   └── goal_anchor.py       DAY 2 — LLM-powered goal decomposition
├── agent/
│   ├── base_agent.py        DAY 1 — LangGraph 5-step agent
│   ├── step_interceptor.py  DAY 2 — hooks into every step
│   └── reasoning_extractor.py DAY 2 — structured reasoning
├── dashboard/               DAY 4 — live observatory UI
├── demos/                   DAY 5 — polished demo scenarios
├── benchmark/               DAY 4 — A/B comparison suite
├── run_day1.py              Day 1 integration test
├── run_day2.py              Day 2 full pipeline test
└── test_setup.py            Environment verification
```

---

## Tech Stack

| Component | Tool | Cost |
|---|---|---|
| LLM inference | Groq (Llama 3.1 70B) | Free tier |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | Free, local |
| Agent framework | LangGraph | Open source |
| Dashboard | Flask + Chart.js | Open source |
| Total cost | | ₹0 |

---

## Benchmark Results

*(Updated after Day 4 benchmark run)*

| Metric | Without DriftWatch | With DriftWatch |
|---|---|---|
| Task completion rate | TBD | TBD |
| Goal alignment score | TBD | TBD |
| Avg embed latency | — | TBD ms |

---

## FAR AWAY 2026 — Agentic & Autonomous Systems Theme

Built for FAR AWAY International Hackathon 2026 by Team [Name].
