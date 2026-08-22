"""
=============================================================
  DriftWatch | mvp.py — Complete MVP entry point
  
  STEP 1: python mvp.py --verify     (check setup)
  STEP 2: python -m dashboard.app    (terminal 1 — keep running)
  STEP 3: python mvp.py --demo1      (terminal 2 — research)
          python mvp.py --demo2      (terminal 2 — coding)
          python mvp.py --all5       (terminal 2 — all 5 demos)
=============================================================
"""
import os, sys, time, argparse, threading
from dotenv import load_dotenv
load_dotenv()

R="\033[91m"; G="\033[92m"; Y="\033[93m"; C="\033[96m"; B="\033[1m"; E="\033[0m"
def red(s):    return f"{R}{s}{E}"
def green(s):  return f"{G}{s}{E}"
def yellow(s): return f"{Y}{s}{E}"
def cyan(s):   return f"{C}{s}{E}"
def bold(s):   return f"{B}{s}{E}"

DEMO_ORDER = ["research", "coding", "legal", "analytics", "writing"]

TASKS = {
    "research": (
        "Research the environmental impact of lithium mining on groundwater quality "
        "in South America and write exactly 3 specific, enforceable policy regulations "
        "that governments can implement."
    ),
    "coding": (
        "Build a Python JWT authentication module with exactly these features: "
        "user login, token generation, token validation, and token refresh. "
        "Return clean, production-ready Python code. No extra features."
    ),
    "legal": (
        "Review a standard software vendor NDA and list exactly 3 specific liability "
        "risks a startup should negotiate before signing. No general contract law lecture."
    ),
    "analytics": (
        "Analyze quarterly retail sales patterns and produce exactly 3 actionable "
        "inventory recommendations for a mid-size bookstore chain. No ML model building."
    ),
    "writing": (
        "Write exactly 200 words announcing a new portable water filtration product "
        "for hikers. Product name, price, and availability only. No marketing campaign."
    ),
}

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


def check_key():
    k = os.getenv("GROQ_API_KEY", "")
    if not k or k == "your_groq_api_key_here":
        print(red("\nERROR: GROQ_API_KEY not set in .env file"))
        print("  1. Open .env")
        print("  2. Get free key: https://console.groq.com")
        print("  3. Paste key and save\n")
        sys.exit(1)


def dashboard_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:5000/health", timeout=1)
        return True
    except Exception:
        return False


def push_http(event_type: str, data: dict):
    """Push event to dashboard via HTTP POST."""
    try:
        import urllib.request, json as _j
        url_map = {
            "task_start":    "http://localhost:5000/api/task_start",
            "step":          "http://localhost:5000/api/step_event",
            "correction":    "http://localhost:5000/api/correction_event",
            "task_complete": "http://localhost:5000/api/complete_event",
        }
        url = url_map.get(event_type)
        if not url:
            return
        req = urllib.request.Request(
            url, data=_j.dumps(data).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def cmd_verify():
    print(bold("\n=== DriftWatch — System Verification ===\n"))
    ok = True
    checks = [
        ("Python 3.9+",       lambda: sys.version_info >= (3, 9)),
        ("numpy",             lambda: __import__("numpy") and True),
        ("flask",             lambda: __import__("flask") and True),
        ("groq SDK",          lambda: __import__("groq") and True),
        ("langchain-groq",    lambda: __import__("langchain_groq") and True),
        ("langgraph",         lambda: __import__("langgraph") and True),
        ("python-dotenv",     lambda: __import__("dotenv") and True),
        (".env file exists",  lambda: os.path.exists(".env")),
        ("GROQ_API_KEY set",  lambda: bool(
            os.getenv("GROQ_API_KEY") and
            os.getenv("GROQ_API_KEY") != "your_groq_api_key_here"
        )),
    ]
    for name, fn in checks:
        try:
            result = fn()
            print(f"  {green('PASS') if result else red('FAIL')}  {name}")
            if not result:
                ok = False
        except Exception as e:
            print(f"  {red('FAIL')}  {name} ({e})")
            ok = False

    if os.getenv("GROQ_API_KEY") and \
       os.getenv("GROQ_API_KEY") != "your_groq_api_key_here":

        print(f"\n  Testing Groq LLM...")
        try:
            from groq import Groq
            c = Groq(api_key=os.getenv("GROQ_API_KEY"))
            t0 = time.time()
            r = c.chat.completions.create(
                model=os.getenv("GROQ_MODEL_MINI", "groq/compound-mini"),
                messages=[{"role": "user", "content": "Reply with exactly: VERIFIED"}],
                max_tokens=5, temperature=0,
            )
            ms = (time.time() - t0) * 1000
            reply = (r.choices[0].message.content or "").strip()
            print(f"  {green('PASS')}  Groq LLM: '{reply}' ({ms:.0f}ms)")
        except Exception as e:
            print(f"  {red('FAIL')}  Groq LLM: {e}")
            ok = False

        print(f"\n  Testing Groq Embeddings...")
        try:
            from groq import Groq
            c = Groq(api_key=os.getenv("GROQ_API_KEY"))
            t0 = time.time()
            r = c.embeddings.create(
                model="nomic-embed-text-v1.5",
                input="DriftWatch test embedding",
            )
            ms  = (time.time() - t0) * 1000
            dim = len(r.data[0].embedding)
            print(f"  {green('PASS')}  Groq Embeddings: dim={dim} ({ms:.0f}ms)")
        except Exception as e:
            print(f"  {yellow('WARN')}  Groq Embeddings: {e}")
            print(f"          LLM fallback will be used")

    print(f"\n{'='*45}")
    if ok:
        print(green("  ALL CHECKS PASSED"))
        print(f"\n  Next steps:")
        print(f"  1. Terminal 1: python -m dashboard.app")
        print(f"  2. Open:       http://localhost:5000")
        print(f"  3. Terminal 2: python mvp.py --demo1")
    else:
        print(red("  SOME CHECKS FAILED — fix above"))
    print(f"{'='*45}\n")


def run_pipeline(scenario: str, push_fn=None) -> dict:
    from core.embedder import Embedder
    from core.drift_detector import DriftDetector
    from core.goal_anchor import GoalAnchor
    from core.correction_engine import CorrectionEngine
    from agent.reasoning_extractor import ReasoningExtractor
    from agent.step_interceptor import StepInterceptor
    from agent.base_agent import run_agent

    task       = TASKS[scenario]
    injections = DRIFT_INJECTIONS.get(scenario, {})

    demo_num = DEMO_ORDER.index(scenario) + 1 if scenario in DEMO_ORDER else 0
    label    = f"DEMO {demo_num} — {scenario.upper()}" if demo_num else scenario.upper()

    print(f"\n{bold('='*62)}")
    print(bold(f"  DriftWatch — {label}"))
    print(f"{'='*62}")
    print(f"  Task: {task[:85]}...")
    print(f"  Drift injection: step(s) {list(injections.keys())}")
    print(f"{'='*62}\n")

    if push_fn:
        push_fn("task_start", {
            "task":        task,
            "total_steps": 5,
            "demo_num":    demo_num,
            "scenario":    scenario,
        })

    # ── 1. Goal anchoring ──────────────────────────────────────────────────
    print(cyan("[1/4] Anchoring goal..."))
    emb    = Embedder(verbose=False)
    anchor = GoalAnchor(embedder=emb)
    ares   = anchor.anchor(task)

    # ── 2. Pipeline setup ─────────────────────────────────────────────────
    # NOTE: do NOT call detector.anchor_goal separately.
    # interceptor.anchor() calls it internally — calling twice causes
    # double-anchor and duplicate step events.
    engine = CorrectionEngine(task=task, verbose=True)
    ev_list = []

    detector    = DriftDetector(embedder=emb, verbose=True)
    extractor   = ReasoningExtractor(embedder=emb)
    interceptor = StepInterceptor(
        detector=detector,
        extractor=extractor,
        event_queue=ev_list,
        verbose=True,
    )
    # Single anchor call only
    interceptor.anchor(task, ares["subgoals"])

    # ── 3. Run agent ───────────────────────────────────────────────────────
    print(cyan("\n[2/4] Running 5-step agent via Groq..."))
    agent_state  = run_agent(task)
    step_outputs = agent_state.get("step_outputs", [])

    # ── 4. Monitor each step ───────────────────────────────────────────────
    print(cyan("\n[3/4] DriftWatch monitoring each step..."))
    all_events = []
    scores     = []
    seen_steps = set()   # prevent duplicate processing

    for step_data in step_outputs:
        sn = step_data.get("step_num", len(all_events) + 1)

        # Skip if we already processed this step number
        if sn in seen_steps:
            print(yellow(f"  [skip] Duplicate step {sn} ignored"))
            continue
        seen_steps.add(sn)

        # Inject drift at configured steps
        if sn in injections:
            print(red(f"\n  >>>  DRIFT INJECTION at step {sn}  <<<"))
            step_data.update(injections[sn])

        ev = interceptor.intercept(sn, step_data)
        scores.append(ev.score)

        # Save checkpoint on clean steps
        if not ev.drift_detected and ev.score > 0.25:
            engine.save_checkpoint(sn, ev.score, step_data)

        # Fire correction if needed
        corr = None
        if ev.correction_needed:
            corr = engine.correct(
                sn, ev.score, ev.threshold,
                ev.drift_type, step_data.get("step_output", ""),
            )

        # Build event dict for dashboard
        ev_dict = ev.to_dict()
        ev_dict["step_output"] = step_data.get("step_output", "")
        if corr:
            ev_dict["correction_tier"] = corr["tier"].value
            ev_dict["correction_msg"]  = corr.get("correction_msg", "")

        # Push to dashboard
        if push_fn:
            push_fn("step", ev_dict)
            if corr and corr["tier"].value not in ("NONE", "TIER_1_NUDGE"):
                push_fn("correction", ev_dict)

        all_events.append({"step": sn, "event": ev, "correction": corr})
        time.sleep(0.5)

        # Abort if correction engine says so
        if corr and corr.get("should_abort"):
            print(red(f"\n  ABORT at step {sn}: {corr.get('diagnosis', '')}"))
            break

    # ── 5. Certificate ─────────────────────────────────────────────────────
    print(cyan("\n[4/4] Generating coherence certificate..."))
    cert = engine.generate_certificate(
        scores=scores,
        total_steps=len(all_events),
        drift_count=len(interceptor.get_drift_events()),
    )
    print(f"\n{cert.display()}")

    # Print step table
    print(f"\n  {'Step':<5} {'Score':<8} {'Thr':<6} {'Status':<22} {'Correction'}")
    print(f"  {'-'*60}")
    for item in all_events:
        ev2  = item["event"]
        c2   = item["correction"]
        sn2  = item["step"]
        stat = f"DRIFT:{ev2.drift_type}" if ev2.drift_detected else "OK"
        cs   = c2["tier"].value if c2 else "—"
        col  = R if ev2.drift_detected else G
        print(f"  {sn2:<5} {col}{ev2.score:<8.3f}{E} "
              f"{ev2.threshold:<6.2f} {stat:<22} {cs}")

    final = agent_state.get("final_output", "")
    if final:
        print(f"\n  Final output:\n  "
              f"{final[:500]}{'...' if len(final) > 500 else ''}")

    # Push certificate to dashboard
    if push_fn:
        push_fn("task_complete", cert.to_dict())

    return {
        "scenario":    scenario,
        "demo_num":    demo_num,
        "scores":      scores,
        "events":      all_events,
        "certificate": cert,
        "final_output": final,
        "drift_count": len(interceptor.get_drift_events()),
        "corrections": engine.summary()["corrections_total"],
    }


def make_push_fn():
    if dashboard_running():
        print(green("  Dashboard connected — http://localhost:5000"))
        return push_http
    else:
        print(yellow("  Dashboard not running."))
        print(yellow("  Start it: python -m dashboard.app"))
        print(yellow("  (demos still run — no live graph)\n"))
        return None


def main():
    p = argparse.ArgumentParser(description="DriftWatch MVP Runner")
    p.add_argument("--verify",    action="store_true",
                   help="Verify setup — no API calls needed")
    p.add_argument("--demo1",     action="store_true",
                   help="Research — lithium policy brief")
    p.add_argument("--demo2",     action="store_true",
                   help="Coding — JWT auth module")
    p.add_argument("--demo3",     action="store_true",
                   help="Legal — NDA liability risks")
    p.add_argument("--demo4",     action="store_true",
                   help="Analytics — inventory recommendations")
    p.add_argument("--demo5",     action="store_true",
                   help="Writing — 200-word product announcement")
    p.add_argument("--both",      action="store_true",
                   help="Run demo 1 + demo 2")
    p.add_argument("--all5",      action="store_true",
                   help="Run all 5 demos in sequence")
    p.add_argument("--dashboard", action="store_true",
                   help="Start dashboard server only")
    args = p.parse_args()

    if args.verify:
        cmd_verify()
        return

    if args.dashboard:
        check_key()
        from dashboard.app import app as flask_app
        port = int(os.getenv("DASHBOARD_PORT", 5000))
        print(f"\n{green(bold('[Dashboard] http://localhost:' + str(port)))}")
        print(f"  Keep running. In a new terminal:")
        print(f"  python mvp.py --demo1\n")
        flask_app.run(
            host="0.0.0.0", port=port,
            debug=False, threaded=True, use_reloader=False,
        )
        return

    check_key()
    push_fn = make_push_fn()

    # Determine which scenarios to run
    demo_flags = [args.demo1, args.demo2, args.demo3,
                  args.demo4, args.demo5]
    if args.all5:
        scenarios = DEMO_ORDER[:]
    elif args.both:
        scenarios = ["research", "coding"]
    elif any(demo_flags):
        scenarios = [DEMO_ORDER[i] for i, on in enumerate(demo_flags) if on]
    else:
        # Default: run both if no flag given
        scenarios = ["research", "coding"]

    results = []
    for sc in scenarios:
        r = run_pipeline(sc, push_fn=push_fn)
        results.append(r)
        if len(scenarios) > 1 and sc != scenarios[-1]:
            print(f"\n{yellow('Pausing 3s before next demo...')}\n")
            time.sleep(3)

    # Summary for multi-demo runs
    if len(results) > 1:
        n     = len(results)
        title = "ALL 5 DEMOS COMPLETE" if n == 5 else f"{n} DEMOS COMPLETE"
        print(f"\n{bold('='*62)}")
        print(bold(f"  {title}"))
        print(f"{'='*62}")
        for r in results:
            c  = r["certificate"]
            vc = green(c.verdict) if "VERIFIED" in c.verdict else red(c.verdict)
            final_score = r["scores"][-1] if r["scores"] else 0
            print(
                f"  {r['scenario'].upper():<12} | "
                f"final={final_score:.3f} | "
                f"drifts={r['drift_count']} | "
                f"corrections={r['corrections']} | {vc}"
            )

    print(f"\n{green('MVP run complete.')}")
    if not dashboard_running():
        print(f"  To see live graph:")
        print(f"  Terminal 1: python -m dashboard.app")
        print(f"  Terminal 2: python mvp.py --demo1")


if __name__ == "__main__":
    main()