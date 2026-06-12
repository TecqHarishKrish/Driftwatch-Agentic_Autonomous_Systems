<div align="center">
        
# DriftWatch

### Real-Time Goal Coherence Monitoring for Autonomous AI Agents

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent_Framework-FF6B6B?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Groq](https://img.shields.io/badge/Groq-LLM_Inference-F55036?style=flat-square)](https://console.groq.com)
[![Flask](https://img.shields.io/badge/Flask-Dashboard-000000?style=flat-square&logo=flask)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Hackathon](https://img.shields.io/badge/FAR_AWAY_2026-Agentic_Systems-purple?style=flat-square)](https://unstop.com)
[![Cost](https://img.shields.io/badge/Infrastructure_Cost-₹0-brightgreen?style=flat-square)]()

**Autonomous agents fail silently. DriftWatch doesn't let them.**

By step 7 of 12, most agents have quietly replaced the original goal with a sub-goal — and nobody knows. DriftWatch detects this in real time, classifies the failure type, and autonomously corrects — without human interruption, in under 60ms per step.

[🚀 Quick Start](#-quick-start) · [🏗 Architecture](#-system-architecture) · [⚙️ How It Works](#️-how-it-works-step-by-step) · [📁 File Structure](#-repository-structure) · [📊 Dashboard](#-live-dashboard) · [🧪 Demo Scenarios](#-demo-scenarios)

</div>

---

## 🔴 The Problem: Silent Goal Substitution

Modern autonomous agents — research pipelines, coding bots, legal reviewers — fail in a way that looks like success. They complete *a* task, just not *your* task. No error. No warning. No trace.

```
Task: "Research lithium mining water impacts → write 3 enforceable regulations"

Step 1: ✅ Reviewing hydrogeology papers              [coherence: 0.91]
Step 2: ✅ Analyzing contamination data               [coherence: 0.88]
Step 3: ⚠️  Expanding to EV battery technology        [coherence: 0.71]  ← drift starts
Step 4: 🔴 Writing about EV market subsidy trends     [coherence: 0.52]  ← GOAL SUBSTITUTION
Step 5: 🔴 Recommending EV adoption policy            [coherence: 0.41]  ← wrong output entirely

Result: A policy brief about EVs instead of water contamination regulations.
        No crash. No error. Looks complete. Is completely wrong.
```

This is not an edge case. This is the default behavior of multi-step agentic systems operating without a coherence monitor.

---

## ✅ The Solution: DriftWatch Intervenes

DriftWatch intercepts every agent step, computes semantic coherence against the anchored goal, tracks drift momentum across a sliding window, and fires a tiered correction — recovering the agent back on track.

```
Step 3: score=0.71 | momentum=-0.09 | SCOPE_CREEP → Tier 1 correction: goal re-injection
Step 4: score=0.86 | momentum=+0.15 | RECOVERED ✅
Step 5: score=0.88 | CONCLUDE phase | on track ✅

Final output: Correct 3-regulation water policy brief ✅
```

---

## 🏗 System Architecture

```mermaid
graph TB
    subgraph INPUT["📥 Input Layer"]
        T[Task / Goal String]
    end

    subgraph ANCHOR["⚓ Goal Anchoring Layer"]
        GA[GoalAnchor\nLLM Decomposition]
        EMB[Embedder\nnomic-embed-text-v1.5]
        AV[Anchor Vector\nGoal Embedding at t=0]
        GA --> EMB --> AV
    end

    subgraph AGENT["🤖 Agent Execution Layer\nLangGraph + Groq"]
        S1[Step 1]
        S2[Step 2]
        S3[Step 3]
        S4[Step 4]
        S5[Step 5]
        S1 --> S2 --> S3 --> S4 --> S5
    end

    subgraph INTERCEPT["🔬 Interception Layer"]
        SI[StepInterceptor\nHook on every step]
        RE[ReasoningExtractor\nStructured JSON Reasoning]
        SI --> RE
    end

    subgraph DETECT["📡 Detection Layer"]
        DD[DriftDetector]
        CS[Cosine Similarity\nvs Anchor Vector]
        MOM[Momentum Tracker\n3-step sliding window]
        THR[Dynamic Threshold\nphase-aware]
        DD --> CS
        DD --> MOM
        DD --> THR
    end

    subgraph CLASSIFY["🏷 Classification Layer"]
        DC[DriftClassifier]
        SCOPE[SCOPE_CREEP\ngradual topic expansion]
        SUB[GOAL_SUBSTITUTION\nwholesale goal swap]
        COL[CONTEXT_COLLAPSE\nloss of relevance]
        DC --> SCOPE
        DC --> SUB
        DC --> COL
    end

    subgraph CORRECT["🔧 Correction Engine"]
        CE[CorrectionEngine]
        T1[Tier 1: Goal Nudge\nscore 0.60–0.75]
        T2[Tier 2: Goal Re-Injection\nscore 0.45–0.60]
        T3[Tier 3: Rollback\nscore 0.30–0.45]
        T4[Tier 4: Abort\nscore less than 0.30]
        CE --> T1
        CE --> T2
        CE --> T3
        CE --> T4
    end

    subgraph OUTPUT["📤 Output Layer"]
        CERT[Coherence Certificate\nVERIFIED / DEGRADED / FAILED]
        DASH[Live Dashboard\nFlask + Chart.js + SSE]
        LOG[Audit Event Log]
    end

    T --> GA
    AV --> DD
    AGENT --> SI
    RE --> DD
    DD --> DC
    DC --> CE
    CE -.->|correction prompt injected| AGENT
    CE --> CERT
    DD --> DASH
    CE --> LOG

    style INPUT fill:#1a1a2e,stroke:#e94560,color:#fff
    style ANCHOR fill:#16213e,stroke:#0f3460,color:#fff
    style AGENT fill:#0f3460,stroke:#533483,color:#fff
    style INTERCEPT fill:#533483,stroke:#e94560,color:#fff
    style DETECT fill:#1a1a2e,stroke:#e94560,color:#fff
    style CLASSIFY fill:#16213e,stroke:#0f3460,color:#fff
    style CORRECT fill:#0f3460,stroke:#533483,color:#fff
    style OUTPUT fill:#533483,stroke:#e94560,color:#fff
```

---

## ⚙️ How It Works: Step-by-Step

### Phase 1 — Goal Anchoring (`core/goal_anchor.py`)

```mermaid
sequenceDiagram
    participant User
    participant GoalAnchor
    participant LLM as Groq LLM
    participant Embedder
    participant Memory

    User->>GoalAnchor: task string
    GoalAnchor->>LLM: decompose into structured subgoals
    LLM-->>GoalAnchor: {subgoals[], constraints[], success_criteria[]}
    GoalAnchor->>Embedder: embed full task + subgoals
    Embedder-->>GoalAnchor: 768-dim anchor vector
    GoalAnchor->>Memory: store anchor_vector at t=0
    GoalAnchor-->>User: anchor_result (subgoals + embedding)
```

Before execution begins, the task is passed through `GoalAnchor`, which calls the Groq LLM to decompose the task into structured subgoals, constraints, and success criteria. This structured representation is then embedded using `nomic-embed-text-v1.5` into a 768-dimensional anchor vector — the ground truth reference for the entire run.

---

### Phase 2 — Per-Step Interception & Scoring (`agent/step_interceptor.py`)

```mermaid
sequenceDiagram
    participant Agent as LangGraph Agent
    participant SI as StepInterceptor
    participant RE as ReasoningExtractor
    participant DD as DriftDetector
    participant Embedder

    Agent->>SI: step_data {current_focus, next_action, step_output}
    SI->>RE: extract structured reasoning
    RE-->>SI: {topic, intent, evidence_of_drift, reasoning_text}
    SI->>Embedder: embed reasoning_text
    Embedder-->>SI: step_vector (768-dim)
    SI->>DD: compare(step_vector, anchor_vector)
    DD->>DD: cosine_similarity(step_vec, anchor_vec)
    DD->>DD: update momentum_window[-3:]
    DD->>DD: compute_momentum()
    DD-->>SI: DriftEvent {score, momentum, threshold, drift_detected, drift_type}
```

Every agent step is intercepted via `StepInterceptor`. The step's reasoning is extracted as structured JSON by `ReasoningExtractor`, embedded, and compared to the anchor vector via cosine similarity. The `DriftDetector` maintains a 3-step sliding window to compute drift **momentum** — not just a single-step score, but the directional trend.

---

### Phase 3 — Drift Detection & Classification

```mermaid
flowchart TD
    A[Step N received] --> B[Compute cosine similarity vs anchor]
    B --> C{Score vs phase threshold?}
    C -->|score >= threshold| D[NO DRIFT\ncheckpoint saved]
    C -->|score less than threshold| E[DRIFT DETECTED]
    E --> F[Compute momentum over last 3 steps]
    F --> G{Classify drift type}
    G -->|gradual expansion| H[SCOPE_CREEP]
    G -->|abrupt topic swap| I[GOAL_SUBSTITUTION]
    G -->|score collapse| J[CONTEXT_COLLAPSE]
    H & I & J --> K[Determine correction tier]
    K --> L{Score range}
    L -->|0.60 to 0.75| M[Tier 1: Subtle Nudge]
    L -->|0.45 to 0.60| N[Tier 2: Goal Re-Injection]
    L -->|0.30 to 0.45| O[Tier 3: Rollback to Checkpoint]
    L -->|below 0.30| P[Tier 4: Abort + Flag]
    M & N & O --> Q[Inject correction into next step context]
    P --> R[Halt pipeline, emit alert]
    Q --> S[Resume agent from corrected state]
    D --> T[Continue to next step]
    S --> T

    style E fill:#e94560,color:#fff
    style H fill:#ff6b6b,color:#fff
    style I fill:#ff6b6b,color:#fff
    style J fill:#ff6b6b,color:#fff
    style D fill:#2ecc71,color:#fff
    style M fill:#f39c12,color:#fff
    style N fill:#e67e22,color:#fff
    style O fill:#c0392b,color:#fff
    style P fill:#922b21,color:#fff
```

The detection logic is **phase-aware** — thresholds shift based on which execution phase the agent is in:

| Phase | Steps | Threshold | Rationale |
|-------|-------|-----------|-----------|
| `INITIALIZE` | 1 | 0.40 | Context gathering, allow loose |
| `RESEARCH` | 2 | 0.55 | Should start narrowing |
| `ANALYZE` | 3 | 0.65 | Core work, enforce coherence |
| `SYNTHESIZE` | 4 | 0.70 | Must be tightly goal-aligned |
| `CONCLUDE` | 5 | 0.72 | Output must match goal directly |

---

### Phase 4 — Correction Response (`core/correction_engine.py`)

```mermaid
stateDiagram-v2
    [*] --> Monitoring

    Monitoring --> Clean : score >= threshold
    Clean --> SaveCheckpoint
    SaveCheckpoint --> Monitoring

    Monitoring --> DriftDetected : score < threshold

    DriftDetected --> Tier1 : 0.60 to 0.75
    DriftDetected --> Tier2 : 0.45 to 0.60
    DriftDetected --> Tier3 : 0.30 to 0.45
    DriftDetected --> Tier4 : below 0.30

    Tier1 --> InjectNudge : Refocus on original goal summary
    Tier2 --> InjectFullGoal : Reinject complete task + subgoals
    Tier3 --> Rollback : Restore last clean checkpoint state
    Tier4 --> Abort : Halt pipeline + emit coherence failure

    InjectNudge --> Monitoring
    InjectFullGoal --> Monitoring
    Rollback --> Monitoring
    Abort --> [*]
```

---

### Phase 5 — Coherence Certificate Generation

After all steps complete, `CorrectionEngine.generate_certificate()` computes:

- **Average coherence score** across all steps
- **Drift count** and correction count
- **Verdict**: `VERIFIED` / `DEGRADED` / `FAILED`
- **Trend analysis**: improving, stable, or declining
- Full audit trail for every step and correction applied

---

## 📁 Repository Structure

```
driftwatch/
│
├── 📄 mvp.py                        ← Primary MVP entry point (473 lines)
│                                       --verify | --demo1..5 | --all5 | --dashboard
│
├── core/                            ← Detection & correction brain
│   ├── embedder.py                  ← Sentence embedding via nomic-embed-text-v1.5 (<60ms)
│   ├── drift_detector.py            ← Cosine similarity + 3-step momentum tracking
│   ├── drift_classifier.py          ← SCOPE_CREEP / GOAL_SUBSTITUTION / CONTEXT_COLLAPSE
│   ├── goal_anchor.py               ← LLM-powered task decomposition → anchor vector
│   └── correction_engine.py         ← 4-tier correction + checkpoint + certificate
│
├── agent/                           ← LangGraph agent runtime
│   ├── base_agent.py                ← LangGraph 5-step agent (Groq Llama 3.1 70B)
│   ├── step_interceptor.py          ← Per-step hook, event queue, anchor management
│   └── reasoning_extractor.py       ← Structured JSON reasoning extraction from LLM
│
├── dashboard/                       ← Live monitoring UI
│   └── app.py                       ← Flask server: SSE stream + REST endpoints
│                                       /api/task_start | /api/step_event
│                                       /api/correction_event | /api/complete_event
│
├── demos/                           ← Pre-configured polished demo scenarios
│
├── benchmark/                       ← A/B comparison suite: with vs without DriftWatch
│
├── run_day1.py                      ← Day 1 tests (no API key needed, fully offline)
├── run_day2.py                      ← Day 2 full pipeline test
├── run_day3.py                      ← Day 3 extended scenarios
├── run_day4.py                      ← Day 4 benchmark + dashboard integration
├── test_setup.py                    ← Environment health check
├── requirements.txt                 ← Python dependencies
└── .env.example                     ← Environment variable template
```

---

## 🔄 End-to-End Data Flow

```mermaid
graph LR
    subgraph A["User Input"]
        T1[Task String]
    end

    subgraph B["Goal Anchoring\ncore/goal_anchor.py"]
        B1[LLM Decomposition]
        B2[Subgoal Extraction]
        B3[Anchor Embedding]
    end

    subgraph C["Agent Runtime\nagent/base_agent.py"]
        C1[Step 1]
        C2[Step 2]
        C3[Step 3 DRIFTED]
        C4[Step 4]
        C5[Step 5]
    end

    subgraph D["Per-Step Monitor\nagent/step_interceptor.py"]
        D1[Extract Reasoning]
        D2[Embed Step Text]
        D3[Cosine vs Anchor]
        D4[Momentum Delta]
        D5[Emit DriftEvent]
    end

    subgraph E["Correction Loop\ncore/correction_engine.py"]
        E1{Drift?}
        E2[Tier Selection]
        E3[Correction Prompt]
        E4[Checkpoint Save]
    end

    subgraph F["Output"]
        F1[Coherence Certificate]
        F2[Live Dashboard]
        F3[Audit Log]
    end

    T1 --> B1 --> B2 --> B3
    B3 --> D3
    C1 & C2 & C3 & C4 & C5 --> D1
    D1 --> D2 --> D3 --> D4 --> D5
    D5 --> E1
    E1 -->|Yes| E2 --> E3 --> C3
    E1 -->|No| E4
    E3 & E4 --> F1
    D5 --> F2
    E2 --> F3
```

---

## 🧪 Demo Scenarios

DriftWatch ships with **5 pre-wired demo scenarios**, each with a controlled drift injection at step 3:

| Demo | Domain | Task | Drift Injected at Step 3 |
|------|--------|------|--------------------------|
| `--demo1` | Research | Write 3 water contamination regulations from lithium mining data | EV market adoption trends |
| `--demo2` | Coding | Build JWT auth module (login, generate, validate, refresh) | OAuth2 social login expansion |
| `--demo3` | Legal | List 3 NDA liability risks for a startup | Delaware incorporation + cap tables |
| `--demo4` | Analytics | 3 inventory recommendations for a bookstore chain | PyTorch LSTM model training |
| `--demo5` | Writing | 200-word product announcement for a water filter | 12-month brand rebranding strategy |

Each demo runs a real Groq LLM agent, injects synthetic drift at step 3, and demonstrates live recovery with coherence scores printed per step.

---

## 📊 Live Dashboard

```mermaid
graph TD
    subgraph FLASK["Flask Server  dashboard/app.py"]
        API1[POST /api/task_start]
        API2[POST /api/step_event]
        API3[POST /api/correction_event]
        API4[POST /api/complete_event]
        SSE[GET /stream — Server-Sent Events]
        HEALTH[GET /health]
    end

    subgraph FRONTEND["Browser UI  Chart.js"]
        GRAPH[Real-time Coherence Graph]
        EVENTS[Step Event Feed]
        CERT[Certificate Panel]
        ALERT[Drift Alert Badges]
    end

    subgraph MVP["mvp.py — push_http()"]
        PUSH[HTTP POST on every step]
    end

    MVP --> API1 & API2 & API3 & API4
    API2 --> SSE
    SSE --> GRAPH & EVENTS
    API3 --> ALERT
    API4 --> CERT
```

The dashboard runs as a **separate Flask process** on `localhost:5000`. `mvp.py` pushes events via `push_http()` after each step — the dashboard receives them via Server-Sent Events (SSE) and updates the Chart.js coherence timeline in real time.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Free [Groq API key](https://console.groq.com) (no credit card needed)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/TecqHarishKrish/Driftwatch-Agentic_Autonomous_Systems
cd Driftwatch-Agentic_Autonomous_Systems

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env → paste your free Groq API key

# 4. Verify everything is working
python mvp.py --verify
```

### Running Demos

```bash
# Terminal 1 — Start live dashboard (optional but strongly recommended)
python -m dashboard.app

# Terminal 2 — Run demos
python mvp.py --demo1       # Research: lithium policy brief
python mvp.py --demo2       # Coding: JWT auth module
python mvp.py --demo3       # Legal: NDA liability risks
python mvp.py --demo4       # Analytics: inventory recommendations
python mvp.py --demo5       # Writing: product announcement
python mvp.py --all5        # Run all 5 demos sequentially
python mvp.py --both        # Run demo1 + demo2 only

# Offline tests (no API key needed)
python run_day1.py
```

### Expected CLI Output

```
══════════════════════════════════════════════════════════════
  DriftWatch — DEMO 1 — RESEARCH
══════════════════════════════════════════════════════════════
  Task: Research the environmental impact of lithium mining...
  Drift injection: step(s) [3]
══════════════════════════════════════════════════════════════

[1/4] Anchoring goal...
[2/4] Running 5-step agent via Groq...
[3/4] DriftWatch monitoring each step...

  >>> DRIFT INJECTION at step 3 <<<

  Step  Score    Thr    Status                 Correction
  ────────────────────────────────────────────────────────
  1     0.912    0.40   OK                     —
  2     0.881    0.55   OK                     —
  3     0.519    0.65   DRIFT:GOAL_SUBSTITUTION TIER_2_REINJECT
  4     0.863    0.70   OK                     —
  5     0.891    0.72   OK                     —

[4/4] Generating coherence certificate...

  ✅ COHERENCE CERTIFICATE — VERIFIED
     Average score: 0.813 | Drifts: 1 | Corrections: 1
```

---

## 🛠 Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| LLM Inference | Groq (Llama 3.1 70B / 8B instant) | Fastest free-tier inference, ~200ms |
| Embeddings | Groq `nomic-embed-text-v1.5` (768-dim) | Free, high-quality semantic vectors |
| Agent Framework | LangGraph | Structured multi-step agent state machine |
| Drift Detection | `numpy` cosine similarity + sliding window | <5ms per step, no GPU needed |
| Dashboard | Flask + Chart.js + SSE | Lightweight, zero-dependency frontend |
| **Total infrastructure cost** | | **₹0 / $0** |

---

## 🔑 Environment Variables

```bash
# .env
GROQ_API_KEY=your_groq_api_key_here          # Required — get free at console.groq.com
DASHBOARD_PORT=5000                           # Optional — default 5000
DRIFT_THRESHOLD=0.65                          # Optional — base coherence threshold
MOMENTUM_WINDOW=3                             # Optional — steps in momentum window
```

---

## 📐 Core Concepts Explained

### Cosine Similarity as Goal Coherence
Every step's reasoning is embedded into a 768-dimensional vector using the same model that embedded the anchor goal. The cosine similarity between the step vector and the anchor vector gives a score from 0 (completely unrelated) to 1 (semantically identical). A score below the phase-aware threshold triggers drift detection.

### Momentum — The Key Innovation
A single low score could be noise. DriftWatch tracks the **momentum** of the last 3 scores:

```
momentum = mean(scores[-3:]) - scores[-3]
```

Negative momentum (declining trend) → escalate correction tier.  
Positive momentum (recovering) → de-escalate or hold.

### Drift Classification
- **SCOPE_CREEP**: Score gradually declining across ≥2 steps. Agent is expanding scope beyond the goal boundary.
- **GOAL_SUBSTITUTION**: Abrupt single-step score drop >0.2. Agent has swapped its working goal wholesale.
- **CONTEXT_COLLAPSE**: Score < 0.35. Agent has lost the goal entirely; no clear connection to original task.

### Coherence Certificate
A structured artifact emitted after task completion. Acts as a tamper-evident audit record that the output was produced under monitored conditions. Contains: verdict, average score, drift events, correction log, and timestamp.

---

## 🗺 Roadmap

- [x] Core drift detection engine (cosine + momentum)
- [x] 4-tier correction system with rollback
- [x] LangGraph 5-step agent integration
- [x] Structured goal anchoring via LLM
- [x] Live Flask dashboard with SSE
- [x] Coherence certificate generation
- [x] 5 demo scenarios with synthetic drift injection
- [x] Offline mode (run_day1.py — no API key needed)
- [ ] Multi-agent graph support (agent-to-agent drift monitoring)
- [ ] Vector database integration for historical drift pattern analysis
- [ ] REST API wrapper for external agent frameworks
- [ ] Webhook-based correction for production deployments
- [ ] Plugin for AutoGen / CrewAI / OpenAI Swarm

---

## 👥 Team

**Team Fusion Force** — Built for [FAR AWAY International Hackathon 2026]([https://unstop.com](https://unstop.com/hackathons/far-away-zuup-1677472))

| Member | Role |
|--------|------|
| Harishwar R | Architecture, core engine, agent integration |
| Sandhiya V S | Dashboard, demo scenarios |
| Sukant B | Benchmarking, testing |

KIT – Kalaignarkarunanidhi Institute of Technology, Coimbatore

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**DriftWatch** — Because an agent that finishes the wrong task isn't intelligence. It's liability.

⭐ Star this repo if DriftWatch saved your agent from itself.

</div>
