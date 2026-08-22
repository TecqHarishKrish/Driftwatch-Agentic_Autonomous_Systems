"""
=============================================================
  DriftWatch | dashboard/app.py  [FINAL VERSION]
  Flask SSE server — run this first, then run demos.
  Usage: python -m dashboard.app
         Then open: http://localhost:5000
=============================================================
"""
import os, json, time, queue, threading
from flask import Flask, Response, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv

from core.workflow_session import WorkflowSession, SessionPhase, save_session_dict
from core.goal_anchor import GoalAnchor
from core.intervention_gate import resolve_decision, get_pending_payload
from core.human_readable import get_certificate_meaning
load_dotenv()

app   = Flask(__name__)
CORS(app)

# ── Shared state (thread-safe) ────────────────────────────────────────────────
_clients: list     = []          # one Queue per connected browser tab
_lock              = threading.Lock()

_sse_queues = {}   # session_id → list of pending SSE events

def push_sse_event(session_id, event_type, data):
    if session_id not in _sse_queues:
        _sse_queues[session_id] = []
    _sse_queues[session_id].append({
        "event": event_type,
        "data": data
    })
_log:    list      = []          # full event log for page-reload recovery
_state             = {
    "task": "", "scores": [], "thresholds": [],
    "is_running": False, "is_complete": False,
    "certificate": None, "step_count": 0,
    "drift_count": 0, "correction_count": 0,
}

def _broadcast(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": data})
    with _lock:
        _log.append({"type": event_type, "data": data})
        if event_type == "task_start":
            _state["step_list"] = []
            _state.update({
                "task": data.get("task", ""),
                "scores": [],
                "thresholds": [],
                "is_running": True,
                "is_complete": False,
                "certificate": None,
                "step_count": 0,
                "drift_count": 0,
                "correction_count": 0,
            })
            _log.clear()
        elif event_type == "step":
            step_num = data.get("step_num", 0)
            if "step_list" not in _state:
                _state["step_list"] = []
            existing = [s.get("step_num") for s in _state["step_list"]]
            if step_num in existing:
                return
            _state["step_list"].append({
                "step_num": step_num,
                "score": data.get("score", 0)
            })
            _state["scores"].append(data.get("score", 0))
            _state["thresholds"].append(data.get("threshold", 0.28))
            _state["step_count"] = step_num
            if data.get("drift_detected"):
                _state["drift_count"] += 1
            if data.get("correction_needed"):
                _state["correction_count"] += 1
        elif event_type == "task_complete":
            _state["is_running"] = False
            _state["is_complete"] = True
            _state["certificate"] = data
        dead = []
        for q in _clients:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for d in dead:
            try:
                _clients.remove(d)
            except ValueError:
                pass

# ── Public API called by mvp.py pipeline ─────────────────────────────────────
def push_event(event_type: str, data: dict):       _broadcast(event_type, data)
def push_task_start(task: str, total_steps: int=5):_broadcast("task_start",{"task":task,"total_steps":total_steps})
def push_task_complete(certificate: dict):          _broadcast("task_complete", certificate)
def push_correction(correction: dict):              _broadcast("correction", correction)

# ── SSE stream ────────────────────────────────────────────────────────────────
def _sse_generator():
    q = queue.Queue()
    with _lock:
        _clients.append(q)
        state_copy = dict(_state)
    # Send current state immediately so page reload recovers chart
    yield f"data: {json.dumps({'type':'state_sync','data':state_copy})}\n\n"
    try:
        while True:
            try:
                payload = q.get(timeout=20)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type':'heartbeat'})}\n\n"
    finally:
        with _lock:
            try: _clients.remove(q)
            except ValueError: pass

@app.route("/stream")
def stream():
    return Response(
        _sse_generator(), mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                 "Access-Control-Allow-Origin":"*"},
    )

@app.route("/api/state")
def get_state():
    with _lock: return jsonify(_state)

@app.route("/api/events")
def get_events():
    return jsonify(_log)

@app.route("/health")
def health():
    return jsonify({"status":"ok","clients":len(_clients)})

# ── HTTP POST endpoints (for cross-process push from mvp.py) ──────────────────
@app.route("/api/task_start", methods=["POST"])
def api_task_start():
    data = request.get_json(silent=True) or {}
    _broadcast("task_start", data)
    return jsonify({"ok": True})

@app.route("/api/step_event", methods=["POST"])
def api_step_event():
    data = request.get_json(silent=True) or {}
    _broadcast("step", data)
    return jsonify({"ok": True})

@app.route("/api/correction_event", methods=["POST"])
def api_correction_event():
    data = request.get_json(silent=True) or {}
    _broadcast("correction", data)
    return jsonify({"ok": True})

@app.route("/api/complete_event", methods=["POST"])
def api_complete_event():
    data = request.get_json(silent=True) or {}
    _broadcast("task_complete", data)
    return jsonify({"ok": True})

# ── Dashboard HTML ────────────────────────────────────────────────────────────
DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DriftWatch Observatory</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#1c2128;--bd:#30363d;
  --tx:#e6edf3;--tx2:#8b949e;--tx3:#484f58;
  --g:#3fb950;--y:#e3b341;--r:#f85149;--b:#58a6ff;
  --o:#fb8f44;--p:#bc8cff;
}
body{font-family:'Segoe UI',system-ui,sans-serif;
     background:var(--bg);color:var(--tx);min-height:100vh;
     overflow-x:hidden}

/* ── HEADER ── */
.hdr{background:var(--bg2);border-bottom:1px solid var(--bd);
     padding:0 24px;height:56px;display:flex;align-items:center;
     gap:16px;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px}
.logo-icon{width:32px;height:32px;border-radius:8px;
           background:linear-gradient(135deg,#1a3a2a,#0d2217);
           border:1px solid #2a5a3a;display:flex;
           align-items:center;justify-content:center;flex-shrink:0}
.logo-title{font-size:16px;font-weight:600;color:#fff}
.logo-sub{font-size:11px;color:var(--tx3);margin-top:1px}
.hdr-tabs{display:flex;gap:6px;margin:0 auto}
.tab{display:flex;align-items:center;gap:8px;padding:6px 14px;
     border-radius:6px;border:1px solid var(--bd);cursor:pointer;
     font-size:12px;font-weight:500;color:var(--tx2);
     transition:all .25s;background:transparent;white-space:nowrap}
.tab:hover{border-color:var(--tx2);color:var(--tx)}
.tab.active{border-color:var(--g);color:var(--g);
            background:rgba(63,185,80,.08)}
.tab.complete{border-color:var(--g);color:var(--g)}
.tab-badge{font-size:10px;padding:2px 7px;border-radius:10px;
           font-weight:600;letter-spacing:.02em}
.badge-pending{background:#1c2128;color:var(--tx3)}
.badge-running{background:#0d2217;color:var(--g)}
.badge-complete{background:#0d2217;color:var(--g)}
.pulse-dot{width:6px;height:6px;border-radius:50%;
           background:var(--g);animation:pdot 1s infinite}
@keyframes pdot{0%,100%{opacity:1;transform:scale(1)}
                50%{opacity:.4;transform:scale(.7)}}
.hdr-right{display:flex;align-items:center;gap:10px;margin-left:auto}
.conn-pill{font-size:11px;padding:3px 10px;border-radius:12px;
           font-weight:600;display:flex;align-items:center;gap:5px}
.conn-ok{background:#0d2217;color:var(--g);border:1px solid #1a4a2a}
.conn-err{background:#2a0d0d;color:var(--r);border:1px solid #4a1a1a}
.clock{font-size:11px;color:var(--tx3);font-family:monospace}

/* ── TASK BAR ── */
.task-bar{display:flex;align-items:stretch;background:var(--bg2);
          border-bottom:1px solid var(--bd);min-height:48px}
.task-accent{width:4px;flex-shrink:0;background:var(--tx3);
             transition:background .3s}
.task-accent.ok{background:var(--g)}
.task-accent.drift{background:var(--r)}
.task-accent.corr{background:var(--o)}
.task-inner{padding:10px 20px;flex:1;display:flex;
            align-items:center;gap:12px}
.task-lbl{font-size:10px;font-weight:700;color:var(--tx3);
          text-transform:uppercase;letter-spacing:.1em;
          flex-shrink:0}
.task-txt{font-size:13px;color:var(--tx2);line-height:1.4}
.demo-tag{font-size:10px;font-weight:700;padding:3px 9px;
          border-radius:4px;flex-shrink:0;margin-left:auto}
.demo-tag.d1{background:#0d1f38;color:var(--b);border:1px solid #1a3a6b}
.demo-tag.d2{background:#1a0d2a;color:var(--p);border:1px solid #3a1a5a}

/* ── INSTRUCTIONS ── */
.instr{background:#0a1628;border-bottom:1px solid #1a3a6b;
       padding:12px 24px;transition:all .4s}
.instr.hide{display:none}
.instr-title{font-size:12px;font-weight:600;color:var(--b);
             margin-bottom:8px}
.instr-grid{display:flex;gap:20px;flex-wrap:wrap}
.instr-step{font-size:12px;color:#8b9fc4;display:flex;
            align-items:center;gap:6px}
.instr-step code{background:#0d1117;border:1px solid #1a3a6b;
                 border-radius:4px;padding:2px 7px;font-size:11px;
                 color:var(--g);font-family:monospace}

/* ── STEP PIPELINE ── */
.pipeline-wrap{padding:16px 24px;background:var(--bg2);
               border-bottom:1px solid var(--bd)}
.pipeline-title{font-size:10px;font-weight:700;color:var(--tx3);
                text-transform:uppercase;letter-spacing:.1em;
                margin-bottom:12px}
.pipeline{display:flex;align-items:center;justify-content:center;
          gap:0;position:relative}
.step-node{display:flex;flex-direction:column;align-items:center;
           gap:6px;position:relative;z-index:2}
.step-circle{width:44px;height:44px;border-radius:50%;
             display:flex;align-items:center;justify-content:center;
             font-size:14px;font-weight:700;transition:all .4s;
             cursor:pointer;position:relative;border:2px solid var(--bd)}
.step-circle.waiting{background:var(--bg3);color:var(--tx3);
                     border-color:var(--bd)}
.step-circle.active{background:#0d2a45;color:var(--b);
                    border-color:var(--b);
                    box-shadow:0 0 0 3px rgba(88,166,255,.2);
                    animation:stepPulse 1.2s infinite}
@keyframes stepPulse{0%,100%{box-shadow:0 0 0 3px rgba(88,166,255,.2)}
                     50%{box-shadow:0 0 0 6px rgba(88,166,255,.05)}}
.step-circle.clean{background:#0d2217;color:var(--g);border-color:var(--g)}
.step-circle.drift{background:#2a0d0d;color:var(--r);border-color:var(--r);
                   box-shadow:0 0 8px rgba(248,81,73,.3)}
.step-circle.corrected{background:#2a1a05;color:var(--o);
                       border-color:var(--o)}
.step-label{font-size:11px;font-weight:600;color:var(--tx3);
            text-align:center;line-height:1.3}
.step-phase{font-size:10px;color:var(--tx3)}
.step-connector{flex:1;height:2px;background:var(--bd);
                min-width:40px;max-width:100px;transition:background .5s}
.step-connector.done{background:var(--g)}
.step-connector.drift{background:var(--r)}

/* Step hover popup */
.step-popup{position:absolute;bottom:calc(100% + 14px);left:50%;
            transform:translateX(-50%);width:220px;
            background:#1c2128;border:1px solid var(--bd);
            border-radius:8px;padding:10px 12px;font-size:12px;
            box-shadow:0 8px 24px rgba(0,0,0,.6);display:none;
            z-index:200;pointer-events:none}
.step-popup::after{content:'';position:absolute;top:100%;left:50%;
                   transform:translateX(-50%);border:6px solid transparent;
                   border-top-color:#1c2128}
.step-node:hover .step-popup{display:block}

/* ── METRICS ── */
.metrics{display:grid;grid-template-columns:repeat(8,1fr);
         gap:8px;padding:14px 24px 0}
@media(max-width:1100px){
  .metrics{grid-template-columns:repeat(4,1fr)}}
.met{background:var(--bg2);border:1px solid var(--bd);
     border-radius:8px;padding:12px 14px;transition:border-color .3s}
.mv{font-size:22px;font-weight:700;margin-bottom:2px;
    transition:color .4s;font-family:monospace}
.ml{font-size:10px;color:var(--tx2);text-transform:uppercase;
    letter-spacing:.05em}
.met.c-g{border-color:#1a3a2a}.met.c-g .mv{color:var(--g)}
.met.c-y{border-color:#3a2e1a}.met.c-y .mv{color:var(--y)}
.met.c-r{border-color:#3a1a1a}.met.c-r .mv{color:var(--r)}
.met.c-b .mv{color:var(--b)}
.met.c-o .mv{color:var(--o)}
.met.c-p .mv{color:var(--p)}
.info-btn{display:inline-flex;align-items:center;justify-content:center;
          width:14px;height:14px;border-radius:50%;
          border:1px solid var(--tx3);color:var(--tx3);
          font-size:9px;font-weight:700;cursor:pointer;
          margin-left:4px;vertical-align:middle;
          position:relative;transition:all .2s}
.info-btn:hover{border-color:var(--b);color:var(--b)}
.info-tip{position:absolute;bottom:calc(100% + 8px);left:50%;
          transform:translateX(-50%);width:200px;
          background:#1c2128;border:1px solid var(--bd);
          border-radius:6px;padding:8px 10px;font-size:11px;
          color:var(--tx2);line-height:1.5;
          box-shadow:0 4px 16px rgba(0,0,0,.5);
          display:none;z-index:300;pointer-events:none;
          text-align:left;font-weight:400}
.info-btn:hover .info-tip{display:block}
.mom-arrow{font-size:16px;margin-right:3px}
.phase-pill{font-size:10px;padding:2px 8px;border-radius:10px;
            font-weight:600;display:inline-block;margin-top:2px}
.phase-explore{background:#0d1f38;color:var(--b)}
.phase-exploit{background:#2a1e0a;color:var(--y)}
.phase-conclude{background:#1a0d2a;color:var(--p)}

/* ── MAIN GRID ── */
.main{display:grid;grid-template-columns:1fr 360px;
      gap:14px;padding:14px 24px}

/* ── CHART CARD ── */
.card{background:var(--bg2);border:1px solid var(--bd);
      border-radius:10px;padding:16px}
.ct{font-size:11px;font-weight:700;color:var(--tx2);
    text-transform:uppercase;letter-spacing:.07em;
    margin-bottom:4px}
.ct-sub{font-size:11px;color:var(--tx3);margin-bottom:14px;
        line-height:1.4}
.chart-wrap{position:relative;height:250px}

/* Zone labels on chart */
.zone-labels{display:flex;flex-direction:column;
             position:absolute;right:-40px;top:0;
             height:100%;justify-content:space-around;
             pointer-events:none}
.zone-lbl{font-size:9px;color:var(--tx3);
          text-transform:uppercase;letter-spacing:.05em}

/* ── DRIFT + CORRECTION BANNERS ── */
.banner-stack{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.banner{border-radius:8px;padding:11px 16px;font-size:12px;
        font-weight:500;display:none;
        animation:bannerSlide .35s cubic-bezier(.34,1.56,.64,1)}
.banner.show{display:flex;align-items:flex-start;gap:10px}
@keyframes bannerSlide{from{opacity:0;transform:translateY(-8px)}
                       to{opacity:1;transform:translateY(0)}}
.banner-drift{background:#2a0d0d;border:1px solid #742a2a;color:#ff8585}
.banner-corr{background:#0a2a1a;border:1px solid #1a5c35;color:#4ade80}
.banner-icon{font-size:16px;flex-shrink:0;margin-top:-1px}
.banner-content{flex:1}
.banner-title{font-weight:700;margin-bottom:2px}
.banner-detail{font-size:11px;opacity:.8}

/* ── CORRECTION REPLAY ── */
.corr-replay{margin-top:14px;display:none}
.corr-replay.show{display:block}
.corr-replay-title{font-size:11px;font-weight:700;color:var(--tx2);
                   text-transform:uppercase;letter-spacing:.07em;
                   margin-bottom:10px}
.corr-card{border-radius:8px;border:1px solid var(--bd);
           overflow:hidden;margin-bottom:8px;
           animation:cardIn .4s ease-out}
@keyframes cardIn{from{opacity:0;transform:translateX(-12px)}
                  to{opacity:1;transform:translateX(0)}}
.corr-card-bar{height:3px}
.bar-nudge{background:var(--y)}
.bar-reinject{background:var(--o)}
.bar-rollback{background:var(--r)}
.bar-abort{background:#8b0000}
.corr-card-body{padding:10px 14px;background:var(--bg3)}
.corr-card-top{display:flex;align-items:center;gap:8px;
               margin-bottom:6px}
.corr-step-lbl{font-size:13px;font-weight:700;color:var(--tx)}
.corr-drift-badge{font-size:10px;padding:2px 7px;border-radius:4px;
                  font-weight:600}
.corr-tier-badge{font-size:10px;padding:2px 7px;border-radius:4px;
                 font-weight:600;margin-left:auto}
.tier-nudge{background:#2a2a0d;color:var(--y)}
.tier-reinject{background:#2a1a05;color:var(--o)}
.tier-rollback{background:#2a0d0d;color:var(--r)}
.corr-score-row{font-size:11px;color:var(--tx2);margin-bottom:8px}
.corr-bar-wrap{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.corr-bar-bg{flex:1;height:6px;background:var(--bg);
             border-radius:3px;overflow:hidden}
.corr-bar-fill{height:100%;border-radius:3px;transition:width 1s ease}
.corr-action{font-size:11px;color:var(--tx2);font-style:italic}

/* ── INFOGRAPHIC ── */
.infographic{margin-top:14px;transition:all .5s}
.infographic.hide{display:none}
.info-panels{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.info-panel{background:var(--bg3);border:1px solid var(--bd);
            border-radius:8px;padding:14px 12px;
            position:relative;overflow:hidden}
.info-panel::before{content:'';position:absolute;top:0;left:0;
                    right:0;height:3px}
.ip1::before{background:var(--b)}
.ip2::before{background:var(--g)}
.ip3::before{background:var(--y)}
.ip4::before{background:var(--p)}
.info-panel-icon{width:36px;height:36px;border-radius:8px;
                 display:flex;align-items:center;justify-content:center;
                 margin-bottom:10px;font-size:18px}
.ip1 .info-panel-icon{background:#0d1f38;color:var(--b)}
.ip2 .info-panel-icon{background:#0d2217;color:var(--g)}
.ip3 .info-panel-icon{background:#2a1e0a;color:var(--y)}
.ip4 .info-panel-icon{background:#1a0d2a;color:var(--p)}
.info-panel-title{font-size:12px;font-weight:600;color:var(--tx);
                  margin-bottom:6px}
.info-panel-text{font-size:11px;color:var(--tx2);line-height:1.5}
.info-arrow{display:flex;align-items:center;justify-content:center;
            color:var(--tx3);font-size:18px;padding:0 4px}

/* ── AUDIT LOG ── */
.log{height:460px;overflow-y:auto}
.log::-webkit-scrollbar{width:3px}
.log::-webkit-scrollbar-thumb{background:var(--bd);border-radius:2px}
.lr{border-bottom:1px solid var(--bg3);cursor:pointer;
    transition:background .15s;
    animation:rowIn .35s ease-out}
@keyframes rowIn{from{opacity:0;transform:translateY(6px)}
                 to{opacity:1;transform:translateY(0)}}
.lr:hover{background:var(--bg3)}
.lr-collapsed{display:flex;align-items:flex-start;gap:8px;
              padding:9px 12px}
.lr.drift-row{border-left:2px solid var(--r)}
.lr.clean-row{border-left:2px solid var(--g)}
.lr.corr-row{border-left:2px solid var(--o)}
.lr-expanded{display:none;padding:0 12px 10px 12px;
             border-top:1px solid var(--bg3)}
.lr.open .lr-expanded{display:block}
.lr-sn{font-size:11px;font-weight:700;color:var(--tx3);
       width:26px;flex-shrink:0;padding-top:1px}
.lr-sc{width:46px;flex-shrink:0;font-family:monospace;
       font-weight:700;font-size:13px}
.sc-g{color:var(--g)}.sc-y{color:var(--y)}.sc-r{color:var(--r)}
.lr-badge{font-size:10px;padding:3px 7px;border-radius:4px;
          font-weight:700;white-space:nowrap;flex-shrink:0;
          margin-top:1px}
.bg-ok{background:#0d2217;color:var(--g)}
.bg-sc{background:#2a1e0a;color:var(--y)}
.bg-gs{background:#2a0d0d;color:var(--r)}
.bg-cc{background:#1a0d2a;color:var(--p)}
.lr-main{flex:1;min-width:0}
.lr-focus{font-size:12px;color:var(--tx);line-height:1.4;
          word-break:break-word}
.lr-meta{font-size:10px;color:var(--tx3);margin-top:2px}
.lr-chevron{color:var(--tx3);font-size:11px;flex-shrink:0;
            transition:transform .2s;margin-top:2px}
.lr.open .lr-chevron{transform:rotate(180deg)}
.lr-expanded-inner{background:var(--bg);border-radius:6px;
                   padding:10px 12px;margin-top:8px;
                   font-size:12px;line-height:1.6}
.exp-label{font-size:10px;font-weight:700;color:var(--tx3);
           text-transform:uppercase;letter-spacing:.06em;
           margin-bottom:4px}
.exp-value{color:var(--tx2);word-break:break-word;margin-bottom:8px}
.log-empty{padding:30px;text-align:center;color:var(--tx3);font-size:13px}

/* ── CERTIFICATE ── */
.cert{background:var(--bg3);border:1px solid var(--bd);
      border-radius:10px;padding:16px;margin-top:14px;
      display:none}
.cert.show{display:block;animation:bannerSlide .5s ease-out}
.cert-verdict-wrap{display:flex;align-items:center;gap:14px;
                   margin-bottom:16px;padding:14px;
                   border-radius:8px}
.cert-verdict-wrap.vf{background:#0a1f0a;border:1px solid #1a4a1a}
.cert-verdict-wrap.vc{background:#0a1f0a;border:1px solid #1a4a1a}
.cert-verdict-wrap.vp{background:#1e1a08;border:1px solid #4a3e10}
.cert-verdict-wrap.vx{background:#1f0a0a;border:1px solid #4a1a1a}
.cert-shield{font-size:32px}
.cert-verdict-text{font-size:18px;font-weight:700}
.cert-verdict-text.vf{color:var(--g)}
.cert-verdict-text.vc{color:var(--g)}
.cert-verdict-text.vp{color:var(--y)}
.cert-verdict-text.vx{color:var(--r)}
.cert-what{font-size:12px;color:var(--tx2);margin-top:3px}
.cert-gauge{display:flex;align-items:center;gap:14px;
            margin-bottom:14px}
.gauge-svg-wrap{flex-shrink:0}
.cert-stats{flex:1}
.cert-row{display:flex;justify-content:space-between;
          font-size:12px;padding:4px 0;
          border-bottom:1px solid var(--bg);color:var(--tx2)}
.cert-row .v{color:var(--tx);font-weight:600;font-family:monospace}
.cert-timeline-title{font-size:10px;font-weight:700;color:var(--tx3);
                     text-transform:uppercase;letter-spacing:.06em;
                     margin-bottom:8px}
.cert-timeline{display:flex;align-items:center;gap:6px;
               padding:8px;background:var(--bg);border-radius:6px}
.ct-step{width:32px;height:32px;border-radius:50%;display:flex;
         align-items:center;justify-content:center;
         font-size:12px;font-weight:700;flex-shrink:0}
.ct-conn{flex:1;height:2px}
.ct-clean{background:#0d2217;color:var(--g);border:1px solid var(--g)}
.ct-drift{background:#2a0d0d;color:var(--r);border:1px solid var(--r)}
.ct-corr{background:#2a1a05;color:var(--o);border:1px solid var(--o)}
.ct-wait{background:var(--bg3);color:var(--tx3);border:1px solid var(--bd)}
.ct-conn-clean{background:var(--g)}
.ct-conn-drift{background:var(--r)}
.ct-conn-wait{background:var(--bd)}

/* ── COMPARISON ── */
.comparison{padding:0 24px 24px;display:none}
.comparison.show{display:block;animation:bannerSlide .5s ease}
.comp-title{font-size:13px;font-weight:600;color:var(--tx);
            margin-bottom:12px;padding-top:4px}
.comp-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.comp-chart-wrap{height:180px;position:relative}
.comp-table{width:100%;font-size:12px;border-collapse:collapse}
.comp-table th{font-size:10px;font-weight:700;color:var(--tx3);
               text-transform:uppercase;letter-spacing:.05em;
               padding:6px 10px;text-align:left;
               border-bottom:1px solid var(--bd)}
.comp-table td{padding:7px 10px;border-bottom:1px solid var(--bg3);
               color:var(--tx2)}
.comp-table td:first-child{color:var(--tx)}
.comp-insight{margin-top:10px;padding:10px 14px;
              background:var(--bg3);border-radius:8px;
              font-size:12px;color:var(--tx2);
              border-left:3px solid var(--b);line-height:1.5}

/* ── DRIFT ALERT POPUP (fixed top-right) ── */
.drift-popup{position:fixed;top:70px;right:20px;width:290px;
             background:#1c2128;border:1px solid var(--bd);
             border-radius:10px;padding:16px;
             box-shadow:0 8px 32px rgba(0,0,0,.6);
             z-index:500;display:none;
             animation:popIn .35s cubic-bezier(.34,1.56,.64,1)}
.drift-popup.show{display:block}
@keyframes popIn{from{opacity:0;transform:scale(.85) translateY(-10px)}
                 to{opacity:1;transform:scale(1) translateY(0)}}
.dp-header{display:flex;align-items:center;gap:8px;
           padding:8px 12px;border-radius:6px;margin-bottom:10px}
.dp-header.alert{background:#2a0d0d;border:1px solid #742a2a}
.dp-header.fixed{background:#0a2a1a;border:1px solid #1a5c35}
.dp-header-text{font-size:13px;font-weight:700}
.alert .dp-header-text{color:var(--r)}
.fixed .dp-header-text{color:var(--g)}
.dp-row{font-size:12px;color:var(--tx2);margin-bottom:6px}
.dp-row strong{color:var(--tx)}
.dp-bar-wrap{margin:8px 0}
.dp-bar-bg{height:8px;background:var(--bg);border-radius:4px;overflow:hidden}
.dp-bar-fill{height:100%;border-radius:4px;transition:width 1.2s ease}
.dp-dots{display:flex;gap:4px;margin-top:8px}
.dp-dot{width:6px;height:6px;border-radius:50%;background:var(--tx3);
        animation:dotBlink 1.4s infinite}
.dp-dot:nth-child(2){animation-delay:.2s}
.dp-dot:nth-child(3){animation-delay:.4s}
@keyframes dotBlink{0%,80%,100%{opacity:.3}40%{opacity:1}}
.dp-close{position:absolute;top:10px;right:12px;
          cursor:pointer;color:var(--tx3);font-size:16px;
          line-height:1}
.dp-close:hover{color:var(--tx)}

/* ── CERTIFICATE MODAL ── */
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.75);
                z-index:600;display:none;
                align-items:center;justify-content:center;
                animation:fadeIn .3s ease}
.modal-backdrop.show{display:flex}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.modal{background:var(--bg2);border:1px solid var(--bd);
       border-radius:14px;padding:28px;width:560px;max-width:90vw;
       max-height:90vh;overflow-y:auto;
       animation:modalIn .4s cubic-bezier(.34,1.56,.64,1)}
@keyframes modalIn{from{opacity:0;transform:scale(.85)}
                   to{opacity:1;transform:scale(1)}}
.modal-title{font-size:12px;font-weight:700;color:var(--tx3);
             text-transform:uppercase;letter-spacing:.1em;
             margin-bottom:20px;text-align:center}
.modal-verdict{text-align:center;margin-bottom:24px}
.modal-shield{font-size:52px;margin-bottom:10px;display:block}
.modal-verdict-text{font-size:24px;font-weight:700;
                    letter-spacing:-.5px}
.modal-verdict-sub{font-size:13px;color:var(--tx2);
                   margin-top:6px;line-height:1.4}
.modal-gauge-wrap{display:flex;justify-content:center;
                  margin-bottom:24px}
.modal-stats{display:grid;grid-template-columns:1fr 1fr;
             gap:8px;margin-bottom:20px}
.modal-stat{background:var(--bg3);border-radius:8px;
            padding:10px 14px;text-align:center}
.modal-stat-val{font-size:18px;font-weight:700;
                font-family:monospace;color:var(--tx)}
.modal-stat-lbl{font-size:11px;color:var(--tx2);margin-top:2px}
.modal-tl-title{font-size:11px;font-weight:700;color:var(--tx2);
                text-transform:uppercase;letter-spacing:.06em;
                margin-bottom:10px}
.modal-insight{background:var(--bg3);border-radius:8px;
               padding:12px 14px;font-size:13px;
               color:var(--tx2);line-height:1.5;
               border-left:3px solid var(--b);margin-bottom:20px}
.modal-btns{display:flex;gap:10px;justify-content:center}
.modal-btn{padding:9px 20px;border-radius:8px;font-size:13px;
           font-weight:600;cursor:pointer;transition:all .2s;border:none}
.btn-primary{background:var(--g);color:#0d1117}
.btn-primary:hover{background:#4ade80}
.btn-secondary{background:var(--bg3);color:var(--tx2);
               border:1px solid var(--bd)}
.btn-secondary:hover{background:var(--bd)}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div class="logo">
    <div class="logo-icon">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="9" r="7" stroke="#3fb950" stroke-width="1.5"/>
        <circle cx="9" cy="9" r="3.5" stroke="#3fb950" stroke-width="1.5"/>
        <line x1="9" y1="1" x2="9" y2="4" stroke="#3fb950" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="9" y1="14" x2="9" y2="17" stroke="#3fb950" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="1" y1="9" x2="4" y2="9" stroke="#3fb950" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="14" y1="9" x2="17" y2="9" stroke="#3fb950" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </div>
    <div>
      <div class="logo-title">DriftWatch</div>
      <div class="logo-sub">AI Agent Coherence Monitor</div>
    </div>
  </div>
  <div class="hdr-tabs">
    <div class="tab" id="tab1" onclick="switchTab(1)">
      <span id="tab1-dot" style="display:none"><span class="pulse-dot"></span></span>
      Demo 1 &mdash; Research Task
      <span class="tab-badge badge-pending" id="tab1-badge">PENDING</span>
    </div>
    <div class="tab" id="tab2" onclick="switchTab(2)">
      <span id="tab2-dot" style="display:none"><span class="pulse-dot"></span></span>
      Demo 2 &mdash; Coding Task
      <span class="tab-badge badge-pending" id="tab2-badge">PENDING</span>
    </div>
  </div>
  <div class="hdr-right">
    <div class="conn-pill conn-ok" id="connPill">
      <span style="width:6px;height:6px;border-radius:50%;background:var(--g);display:inline-block"></span>
      CONNECTED
    </div>
    <div class="clock" id="clock">00:00:00</div>
  </div>
</div>

<!-- TASK BAR -->
<div class="task-bar">
  <div class="task-accent" id="taskAccent"></div>
  <div class="task-inner">
    <div class="task-lbl">Task</div>
    <div class="task-txt" id="taskTxt">Waiting for agent run...</div>
    <div class="demo-tag d1" id="demoTag" style="display:none">DEMO 1</div>
  </div>
</div>

<!-- INSTRUCTIONS -->
<div class="instr" id="instr">
  <div class="instr-title">Dashboard ready &mdash; start the demo in a second terminal</div>
  <div class="instr-grid">
    <div class="instr-step">Research demo: <code>python mvp.py --demo1</code></div>
    <div class="instr-step">Coding demo: <code>python mvp.py --demo2</code></div>
    <div class="instr-step">Both demos: <code>python mvp.py --both</code></div>
  </div>
</div>

<!-- STEP PIPELINE -->
<div class="pipeline-wrap">
  <div class="pipeline-title">Agent Execution Pipeline</div>
  <div class="pipeline" id="pipeline">
    <!-- built by JS -->
  </div>
</div>

<!-- METRICS -->
<div class="metrics">
  <div class="met c-b" id="mStepCard">
    <div class="mv" id="mStep">0</div>
    <div class="ml">Current step</div>
  </div>
  <div class="met" id="mPhaseCard">
    <div id="mPhase"><span class="phase-pill phase-explore">EXPLORE</span></div>
    <div class="ml" style="margin-top:4px">Phase</div>
  </div>
  <div class="met c-g" id="mScoreCard">
    <div class="mv" id="mScore">
      &mdash;
      <span class="info-btn" tabindex="0">i
        <div class="info-tip">Cosine similarity between agent reasoning and original goal. 1.0 = perfectly aligned. Below threshold = drift detected.</div>
      </span>
    </div>
    <div class="ml">Coherence score</div>
  </div>
  <div class="met" id="mMomCard">
    <div class="mv" id="mMom" style="color:var(--tx3)">
      &mdash;
      <span class="info-btn" tabindex="0">i
        <div class="info-tip">Rate of coherence change over last 3 steps. Negative = drifting away from goal. Positive = recovering toward goal.</div>
      </span>
    </div>
    <div class="ml">Momentum</div>
  </div>
  <div class="met c-y" id="mDriftCard">
    <div class="mv" id="mDrift">0</div>
    <div class="ml">Drift events</div>
  </div>
  <div class="met c-g" id="mCorrCard">
    <div class="mv" id="mCorr">0</div>
    <div class="ml">Corrections</div>
  </div>
  <div class="met" id="mAvgCard">
    <div class="mv" id="mAvg">&mdash;</div>
    <div class="ml">Avg score</div>
  </div>
  <div class="met" id="mMinCard">
    <div class="mv" id="mMin">&mdash;</div>
    <div class="ml">Min score
      <span class="info-btn" tabindex="0">i
        <div class="info-tip">Drift threshold varies by phase: EXPLORE=0.30, EXPLOIT=0.40, CONCLUDE=0.50. Stricter at conclusion because exploration legitimately covers broad topics.</div>
      </span>
    </div>
  </div>
</div>

<!-- MAIN GRID -->
<div class="main">
  <!-- LEFT COLUMN -->
  <div>
    <!-- Chart -->
    <div class="card">
      <div class="ct">Real-time Goal Coherence Score</div>
      <div class="ct-sub">Semantic similarity between agent reasoning and original task goal &mdash; monitored at every step</div>
      <div class="chart-wrap">
        <canvas id="ch"></canvas>
      </div>
    </div>

    <!-- Banners -->
    <div class="banner-stack">
      <div class="banner banner-drift" id="driftBanner">
        <div class="banner-icon">&#9888;</div>
        <div class="banner-content">
          <div class="banner-title" id="driftBannerTitle">Drift detected</div>
          <div class="banner-detail" id="driftBannerDetail"></div>
        </div>
      </div>
      <div class="banner banner-corr" id="corrBanner">
        <div class="banner-icon">&#10003;</div>
        <div class="banner-content">
          <div class="banner-title" id="corrBannerTitle">Correction applied</div>
          <div class="banner-detail" id="corrBannerDetail"></div>
        </div>
      </div>
    </div>

    <!-- Correction replay -->
    <div class="corr-replay" id="corrReplay">
      <div class="corr-replay-title">Corrections applied</div>
      <div id="corrCards"></div>
    </div>

    <!-- Infographic -->
    <div class="infographic" id="infographic">
      <div style="font-size:11px;font-weight:700;color:var(--tx2);
                  text-transform:uppercase;letter-spacing:.07em;
                  margin-bottom:10px">How DriftWatch works</div>
      <div class="info-panels">
        <div class="info-panel ip1">
          <div class="info-panel-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="10" cy="10" r="1" fill="currentColor"/>
            </svg>
          </div>
          <div class="info-panel-title">Goal Anchoring</div>
          <div class="info-panel-text">Task embedded into vector space at t=0. Sub-goals decomposed and stored as reference anchors.</div>
        </div>
        <div class="info-panel ip2">
          <div class="info-panel-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <ellipse cx="10" cy="10" rx="9" ry="5" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/>
            </svg>
          </div>
          <div class="info-panel-title">Step Monitoring</div>
          <div class="info-panel-text">Every agent reasoning step embedded and compared to goal anchor via cosine similarity.</div>
        </div>
        <div class="info-panel ip3">
          <div class="info-panel-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M10 3L18 16H2L10 3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              <line x1="10" y1="8" x2="10" y2="12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              <circle cx="10" cy="14" r="1" fill="currentColor"/>
            </svg>
          </div>
          <div class="info-panel-title">Drift Detection</div>
          <div class="info-panel-text">3-step momentum tracking catches gradual drift before it compounds. Phase-aware thresholds applied.</div>
        </div>
        <div class="info-panel ip4">
          <div class="info-panel-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M14 3L17 6L8 15L4 16L5 12L14 3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              <line x1="12" y1="5" x2="15" y2="8" stroke="currentColor" stroke-width="1.5"/>
            </svg>
          </div>
          <div class="info-panel-title">Auto Correction</div>
          <div class="info-panel-text">4-tier correction: Nudge &rarr; Re-inject &rarr; Rollback &rarr; Abort. No human intervention needed.</div>
        </div>
      </div>
    </div>

    <!-- Certificate (inline) -->
    <div class="cert" id="cert">
      <div class="ct">Coherence Certificate</div>
      <div class="cert-verdict-wrap" id="certWrap">
        <div class="cert-shield" id="certShield">&#9654;</div>
        <div>
          <div class="cert-verdict-text" id="certVerdict">---</div>
          <div class="cert-what" id="certWhat"></div>
        </div>
      </div>
      <div class="cert-gauge">
        <div class="gauge-svg-wrap">
          <svg id="gaugeSvg" width="90" height="54" viewBox="0 0 90 54">
            <path d="M 10 50 A 35 35 0 0 1 80 50" stroke="#30363d" stroke-width="8" fill="none" stroke-linecap="round"/>
            <path id="gaugeArc" d="M 10 50 A 35 35 0 0 1 80 50" stroke="#3fb950" stroke-width="8" fill="none" stroke-linecap="round" stroke-dasharray="110" stroke-dashoffset="110"/>
            <text x="45" y="48" text-anchor="middle" font-size="14" font-weight="700" fill="#e6edf3" id="gaugeText">0.00</text>
          </svg>
        </div>
        <div class="cert-stats" id="certStats"></div>
      </div>
      <div class="cert-timeline-title">Step correction timeline</div>
      <div class="cert-timeline" id="certTimeline"></div>
    </div>
  </div>

  <!-- RIGHT COLUMN -->
  <div class="card" style="padding-bottom:0">
    <div class="ct" style="margin-bottom:14px">Audit Log &mdash; Step by Step</div>
    <div class="log" id="log">
      <div class="log-empty">Waiting for agent execution...</div>
    </div>
  </div>
</div>

<!-- COMPARISON SECTION -->
<div class="comparison" id="comparison">
  <div class="comp-title">Side-by-Side Comparison &mdash; Both Demos</div>
  <div class="comp-grid">
    <div class="card">
      <div class="ct" style="margin-bottom:8px">Score Comparison</div>
      <div class="comp-chart-wrap">
        <canvas id="compCh"></canvas>
      </div>
    </div>
    <div class="card">
      <div class="ct" style="margin-bottom:10px">Metrics Table</div>
      <table class="comp-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Demo 1</th>
            <th>Demo 2</th>
          </tr>
        </thead>
        <tbody id="compBody"></tbody>
      </table>
      <div class="comp-insight" id="compInsight"></div>
    </div>
  </div>
</div>

<!-- DRIFT ALERT POPUP (fixed top-right) -->
<div class="drift-popup" id="driftPopup">
  <div class="dp-close" onclick="closeDriftPopup()">&#215;</div>
  <div class="dp-header alert" id="dpHeader">
    <span style="font-size:18px">&#9888;</span>
    <span class="dp-header-text" id="dpHeaderTxt">DRIFT DETECTED</span>
  </div>
  <div class="dp-row" id="dpStep"></div>
  <div class="dp-row" id="dpScore"></div>
  <div class="dp-bar-wrap">
    <div class="dp-bar-bg">
      <div class="dp-bar-fill" id="dpBar" style="width:0%;background:var(--r)"></div>
    </div>
  </div>
  <div class="dp-row" id="dpAction"></div>
  <div class="dp-dots" id="dpDots">
    <div class="dp-dot"></div>
    <div class="dp-dot"></div>
    <div class="dp-dot"></div>
    <span style="font-size:11px;color:var(--tx3);margin-left:4px">Applying correction...</span>
  </div>
</div>

<!-- CERTIFICATE MODAL -->
<div class="modal-backdrop" id="modalBackdrop" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="modal-title">DriftWatch &mdash; Coherence Certificate</div>
    <div class="modal-verdict">
      <span class="modal-shield" id="modalShield">&#9632;</span>
      <div class="modal-verdict-text" id="modalVerdict">---</div>
      <div class="modal-verdict-sub" id="modalSub"></div>
    </div>
    <div class="modal-gauge-wrap">
      <svg id="modalGaugeSvg" width="140" height="84" viewBox="0 0 140 84">
        <path d="M 14 78 A 56 56 0 0 1 126 78" stroke="#30363d" stroke-width="10" fill="none" stroke-linecap="round"/>
        <path id="modalGaugeArc" d="M 14 78 A 56 56 0 0 1 126 78" stroke="#3fb950" stroke-width="10" fill="none" stroke-linecap="round" stroke-dasharray="176" stroke-dashoffset="176"/>
        <text x="70" y="72" text-anchor="middle" font-size="20" font-weight="700" fill="#e6edf3" id="modalGaugeText">0.00</text>
      </svg>
    </div>
    <div class="modal-stats" id="modalStats"></div>
    <div class="modal-tl-title">Step correction timeline</div>
    <div class="cert-timeline" id="modalTimeline" style="margin-bottom:16px"></div>
    <div class="modal-insight" id="modalInsight"></div>
    <div class="modal-btns">
      <button class="modal-btn btn-primary" onclick="closeModal()">View Audit Log</button>
      <button class="modal-btn btn-secondary" onclick="closeModal()">Close</button>
    </div>
  </div>
</div>

<script>
// ── STATE ─────────────────────────────────────────────────────────────────────
const demos = {
  1: { scores:[], thresholds:[], events:[], cert:null,
       drifts:0, corrections:0, complete:false, label:'Research' },
  2: { scores:[], thresholds:[], events:[], cert:null,
       drifts:0, corrections:0, complete:false, label:'Coding'   },
};
let activeDemo = 1;
let firstLog   = true;
let seenSteps  = new Set();  // prevent duplicate log rows

// ── CLOCK ─────────────────────────────────────────────────────────────────────
setInterval(() => {
  const n = new Date();
  document.getElementById('clock').textContent =
    n.toTimeString().slice(0, 8);
}, 1000);

// ── PIPELINE BUILD ────────────────────────────────────────────────────────────
const PHASES = ['EXPLORE','EXPLORE','EXPLOIT','EXPLOIT','CONCLUDE'];
const pipelineEl = document.getElementById('pipeline');
const stepNodes  = [];

function buildPipeline() {
  pipelineEl.innerHTML = '';
  stepNodes.length = 0;
  for (let i = 1; i <= 5; i++) {
    const node = document.createElement('div');
    node.className = 'step-node';
    node.id = `sn${i}`;
    node.innerHTML = `
      <div class="step-circle waiting" id="sc${i}">${i}</div>
      <div class="step-label">S${i}</div>
      <div class="step-phase">${PHASES[i-1]}</div>
      <div class="step-popup" id="sp${i}">
        <div style="font-weight:700;margin-bottom:6px">Step ${i} &mdash; ${PHASES[i-1]}</div>
        <div id="spp${i}" style="color:var(--tx2);font-size:11px">Waiting...</div>
      </div>`;
    pipelineEl.appendChild(node);
    stepNodes.push(node);
    if (i < 5) {
      const conn = document.createElement('div');
      conn.className = 'step-connector';
      conn.id = `conn${i}`;
      pipelineEl.appendChild(conn);
    }
  }
}
buildPipeline();

function setStepState(n, state, ev) {
  const circle = document.getElementById(`sc${n}`);
  if (!circle) return;
  circle.className = `step-circle ${state}`;
  const icons = { clean:'&#10003;', drift:'&#215;', corrected:'&#8617;', active:'&#9679;' };
  if (icons[state]) circle.innerHTML = icons[state];
  else circle.textContent = n;

  if (n > 1) {
    const conn = document.getElementById(`conn${n-1}`);
    if (conn) conn.className = 'step-connector ' +
      (state === 'drift' || state === 'corrected' ? 'drift' : 'done');
  }
  if (ev) {
    const pp = document.getElementById(`spp${n}`);
    if (pp) {
      const scClass = ev.score >= 0.55 ? 'sc-g' : ev.score >= 0.35 ? 'sc-y' : 'sc-r';
      pp.innerHTML = `
        <span class="lr-sc ${scClass}">${(ev.score||0).toFixed(3)}</span>
        ${ev.drift_detected
          ? `<span style="color:var(--r);margin-left:4px">Drift: ${ev.drift_type}</span>`
          : `<span style="color:var(--g);margin-left:4px">On track</span>`}
        <br><span style="color:var(--tx3)">${(ev.focus||'').substring(0,60)}</span>`;
    }
  }
}

// ── CHART SETUP ───────────────────────────────────────────────────────────────
const chartPlugin = {
  id: 'zones',
  beforeDraw(chart) {
    const { ctx, chartArea: a, scales: { y } } = chart;
    if (!a) return;
    const zones = [
      { y0: 0.7, y1: 1.05, color: 'rgba(63,185,80,.06)',  label: 'Safe' },
      { y0: 0.4, y1: 0.7,  color: 'rgba(227,179,65,.06)', label: 'Warning' },
      { y0: 0.0, y1: 0.4,  color: 'rgba(248,81,73,.06)',  label: 'Drift' },
    ];
    zones.forEach(z => {
      const y0 = y.getPixelForValue(z.y0);
      const y1 = y.getPixelForValue(z.y1);
      ctx.fillStyle = z.color;
      ctx.fillRect(a.left, Math.min(y0, y1), a.width, Math.abs(y1 - y0));
    });
  }
};

const ctx = document.getElementById('ch').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  plugins: [chartPlugin],
  data: {
    labels: [],
    datasets: [
      { label: 'Coherence Score', data: [],
        borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.08)',
        borderWidth: 3, pointRadius: 7, pointHoverRadius: 9,
        pointBackgroundColor: [], pointBorderColor: [], pointBorderWidth: 2,
        fill: true, tension: .4 },
      { label: 'Drift Threshold', data: [],
        borderColor: '#f85149', borderWidth: 2.5, borderDash: [6,3],
        pointRadius: 0, fill: false },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 500 },
    scales: {
      y: { min: 0, max: 1.05,
           grid: { color: 'rgba(255,255,255,.05)' },
           ticks: { color: '#8b949e', font: { size: 11 },
                    callback: v => v.toFixed(1) } },
      x: { grid: { color: 'rgba(255,255,255,.05)' },
           ticks: { color: '#8b949e', font: { size: 11 } } }
    },
    plugins: {
      legend: { labels: { color: '#8b949e', font: { size: 12 },
                          boxWidth: 16, padding: 20 } },
      tooltip: {
        backgroundColor: '#1c2128', borderColor: '#30363d', borderWidth: 1,
        titleColor: '#e6edf3', bodyColor: '#8b949e',
        callbacks: {
          title: items => `Step ${items[0].label}`,
          label: item => {
            if (item.datasetIndex === 1)
              return `Threshold: ${item.parsed.y.toFixed(3)}`;
            const ev = demos[activeDemo].events[item.dataIndex];
            if (!ev) return `Score: ${item.parsed.y.toFixed(4)}`;
            return [
              `Score: ${item.parsed.y.toFixed(4)}`,
              `Phase: ${ev.phase || ''}`,
              `Momentum: ${(ev.momentum||0).toFixed(3)}`,
              ev.drift_detected ? `Drift: ${ev.drift_type}` : 'Status: On track',
              ev.correction_needed ? `Correction: ${ev.correction_tier||'fired'}` : '',
            ].filter(Boolean);
          }
        }
      }
    }
  }
});

let compChart = null;

// ── HELPERS ───────────────────────────────────────────────────────────────────
function scClass(s) { return s >= 0.55 ? 'sc-g' : s >= 0.35 ? 'sc-y' : 'sc-r'; }
function badge(t) {
  return {
    'NONE':              ['bg-ok','On track'],
    'SCOPE_CREEP':       ['bg-sc','Scope creep'],
    'GOAL_SUBSTITUTION': ['bg-gs','Goal subst.'],
    'CONTEXT_COLLAPSE':  ['bg-cc','Ctx collapse'],
  }[t] || ['bg-ok', t || 'OK'];
}

function addChartPt(score, thr, drift) {
  const d = demos[activeDemo];
  chart.data.labels.push(`S${d.scores.length}`);
  chart.data.datasets[0].data.push(score);
  chart.data.datasets[0].pointBackgroundColor.push(drift ? '#f85149' : '#3fb950');
  chart.data.datasets[0].pointBorderColor.push(drift ? '#ff6b6b' : '#68d391');
  chart.data.datasets[1].data.push(thr);
  chart.update();
}

function resetChart() {
  chart.data.labels = [];
  chart.data.datasets.forEach(d => {
    d.data = [];
    if (d.pointBackgroundColor) d.pointBackgroundColor = [];
    if (d.pointBorderColor)     d.pointBorderColor = [];
  });
  chart.update();
}

function loadChartFromDemo(demoNum) {
  const d = demos[demoNum];
  resetChart();
  d.scores.forEach((sc, i) => {
    chart.data.labels.push(`S${i+1}`);
    chart.data.datasets[0].data.push(sc);
    const drift = sc < (d.thresholds[i] || 0.4);
    chart.data.datasets[0].pointBackgroundColor.push(drift ? '#f85149' : '#3fb950');
    chart.data.datasets[0].pointBorderColor.push(drift ? '#ff6b6b' : '#68d391');
    chart.data.datasets[1].data.push(d.thresholds[i] || 0.4);
  });
  chart.update();
}

// ── TABS ─────────────────────────────────────────────────────────────────────
function switchTab(n) {
  activeDemo = n;
  seenSteps  = new Set();
  firstLog   = true;
  document.getElementById('tab1').className = 'tab' + (n===1?' active':'');
  document.getElementById('tab2').className = 'tab' + (n===2?' active':'');
  loadChartFromDemo(n);
  rebuildLog(n);
  buildPipeline();
  // Re-apply step states
  demos[n].events.forEach(ev => {
    const state = ev.drift_detected
      ? (ev.correction_needed ? 'corrected' : 'drift')
      : 'clean';
    setStepState(ev.step_num, state, ev);
  });
  // Update cert
  if (demos[n].cert) {
    document.getElementById('cert').className = 'cert show';
    renderCert(demos[n].cert);
  } else {
    document.getElementById('cert').className = 'cert';
  }
  // Update metrics from demo data
  if (demos[n].scores.length > 0) {
    const last = demos[n].scores[demos[n].scores.length-1];
    const lastEv = demos[n].events[demos[n].events.length-1];
    updateMetrics(lastEv || {score:last,drift_detected:false});
    document.getElementById('mDrift').textContent = demos[n].drifts;
    document.getElementById('mCorr').textContent  = demos[n].corrections;
  }
}

function rebuildLog(n) {
  const log = document.getElementById('log');
  log.innerHTML = '';
  firstLog = true;
  if (demos[n].events.length === 0) {
    log.innerHTML = '<div class="log-empty">No data for this demo yet</div>';
    return;
  }
  demos[n].events.forEach(ev => addLogRow(ev, false));
}

// ── LOG ROW ───────────────────────────────────────────────────────────────────
function addLogRow(ev, scroll=true) {
  const key = `${activeDemo}-${ev.step_num}`;
  if (seenSteps.has(key)) return;
  seenSteps.add(key);

  const log = document.getElementById('log');
  if (firstLog) {
    log.innerHTML = '';
    firstLog = false;
  }

  const [cls, lbl] = badge(ev.drift_type || 'NONE');
  const sc = (ev.score || 0).toFixed(3);
  const rowClass = ev.drift_detected
    ? (ev.correction_needed ? 'corr-row' : 'drift-row')
    : 'clean-row';

  const row = document.createElement('div');
  row.className = `lr ${rowClass}`;
  row.innerHTML = `
    <div class="lr-collapsed">
      <span class="lr-sn">S${ev.step_num}</span>
      <span class="lr-sc ${scClass(ev.score||0)}">${sc}</span>
      <span class="lr-badge ${cls}">${lbl}</span>
      <div class="lr-main">
        <div class="lr-focus">${(ev.focus||'No focus data')}</div>
        <div class="lr-meta">
          ${ev.phase||''} &middot; thr=${(ev.threshold||0).toFixed(2)} &middot; mom=${(ev.momentum||0).toFixed(3)}
          ${ev.correction_needed ? ` &middot; <span style="color:var(--o)">Correction fired</span>` : ''}
        </div>
      </div>
      <span class="lr-chevron">&#9660;</span>
    </div>
    <div class="lr-expanded">
      <div class="lr-expanded-inner">
        <div class="exp-label">Goal link</div>
        <div class="exp-value">${ev.goal_link || '—'}</div>
        <div class="exp-label">Agent output</div>
        <div class="exp-value">${(ev.step_output||ev.focus||'—').substring(0,250)}</div>
        ${ev.drift_detected ? `
        <div class="exp-label">Correction applied</div>
        <div class="exp-value" style="color:var(--o)">${corrTierText(ev.correction_tier||'')}</div>
        ` : ''}
      </div>
    </div>`;

  row.querySelector('.lr-collapsed').addEventListener('click', () => {
    row.classList.toggle('open');
  });

  log.appendChild(row);
  if (scroll) log.scrollTop = log.scrollHeight;
}

// ── METRICS UPDATE ────────────────────────────────────────────────────────────
function updateMetrics(ev) {
  const s = ev.score || 0;
  animateNumber('mStep',  ev.step_num || 0, 0);
  document.getElementById('mScore').childNodes[0].nodeValue = s.toFixed(3) + ' ';
  document.getElementById('mScoreCard').className =
    'met ' + (s >= 0.55 ? 'c-g' : s >= 0.35 ? 'c-y' : 'c-r');

  const mom = ev.momentum || 0;
  const momEl  = document.getElementById('mMom');
  const arrow  = mom > 0.01 ? '&#8593;' : mom < -0.01 ? '&#8595;' : '&#8594;';
  const momCol = mom > 0.01 ? 'var(--g)' : mom < -0.01 ? 'var(--r)' : 'var(--tx3)';
  momEl.innerHTML = `<span style="color:${momCol}">${arrow} ${Math.abs(mom).toFixed(3)}</span>
    <span class="info-btn" tabindex="0">i<div class="info-tip">Rate of coherence change over last 3 steps. Negative = drifting away from goal.</div></span>`;

  const phase = (ev.phase || 'EXPLORE').toUpperCase();
  const phaseClass = phase === 'EXPLORE' ? 'phase-explore'
                   : phase === 'EXPLOIT' ? 'phase-exploit' : 'phase-conclude';
  document.getElementById('mPhase').innerHTML =
    `<span class="phase-pill ${phaseClass}">${phase}</span>`;

  const d = demos[activeDemo];
  if (d.scores.length > 0) {
    const avg = d.scores.reduce((a,b)=>a+b,0)/d.scores.length;
    const mn  = Math.min(...d.scores);
    document.getElementById('mAvg').textContent = avg.toFixed(3);
    document.getElementById('mMin').textContent = mn.toFixed(3);
    document.getElementById('mAvgCard').className = 'met ' + (avg >= 0.55 ? 'c-g' : avg >= 0.35 ? 'c-y' : 'c-r');
    document.getElementById('mMinCard').className = 'met ' + (mn  >= 0.55 ? 'c-g' : mn  >= 0.35 ? 'c-y' : 'c-r');
  }
}

function animateNumber(id, target, decimals) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = parseFloat(el.textContent) || 0;
  const diff  = target - start;
  const dur   = 500;
  const t0    = performance.now();
  function step(now) {
    const p = Math.min((now - t0) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (start + diff * eased).toFixed(decimals);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ── CORRECTION CARDS ──────────────────────────────────────────────────────────
function corrTierText(tier) {
  return {
    'TIER_1_NUDGE':    'Soft goal reminder appended to agent context',
    'TIER_2_REINJECT': 'Full goal re-stated as hard constraint in prompt',
    'TIER_3_ROLLBACK': 'Agent state restored to last clean checkpoint',
    'TIER_4_ABORT':    'Task aborted — drift was irrecoverable',
  }[tier] || tier || 'Correction applied';
}

function addCorrCard(ev) {
  const replay = document.getElementById('corrReplay');
  const cards  = document.getElementById('corrCards');
  replay.className = 'corr-replay show';

  const tier    = ev.correction_tier || 'TIER_1_NUDGE';
  const barCls  = tier.includes('NUDGE') ? 'bar-nudge'
                : tier.includes('REINJECT') ? 'bar-reinject'
                : tier.includes('ROLLBACK') ? 'bar-rollback' : 'bar-abort';
  const tierCls = tier.includes('NUDGE') ? 'tier-nudge'
                : tier.includes('REINJECT') ? 'tier-reinject' : 'tier-rollback';
  const [bcls, blbl] = badge(ev.drift_type || 'NONE');
  const scorePct = Math.round((ev.score || 0) * 100);

  const card = document.createElement('div');
  card.className = 'corr-card';
  card.innerHTML = `
    <div class="corr-card-bar ${barCls}"></div>
    <div class="corr-card-body">
      <div class="corr-card-top">
        <span class="corr-step-lbl">Step ${ev.step_num}</span>
        <span class="lr-badge ${bcls}">${blbl}</span>
        <span class="corr-tier-badge ${tierCls}">${tier.replace('TIER_','T').replace('_',' ')}</span>
      </div>
      <div class="corr-score-row">Score dropped to <strong>${(ev.score||0).toFixed(3)}</strong> (threshold: ${(ev.threshold||0).toFixed(3)})</div>
      <div class="corr-bar-wrap">
        <span style="font-size:10px;color:var(--tx3);width:36px">Before</span>
        <div class="corr-bar-bg">
          <div class="corr-bar-fill" style="width:${scorePct}%;background:var(--r)"></div>
        </div>
        <span style="font-size:10px;color:var(--r)">${(ev.score||0).toFixed(2)}</span>
      </div>
      <div class="corr-action">${corrTierText(tier)}</div>
    </div>`;
  cards.insertBefore(card, cards.firstChild);
  if (cards.children.length > 4) cards.removeChild(cards.lastChild);
}

// ── CERT RENDER ───────────────────────────────────────────────────────────────
const verdictMap = {
  'VERIFIED': {
    shield:'&#9989;', cls:'vf',
    txt:'VERIFIED', sub:'Agent completed the task without any goal drift.'
  },
  'VERIFIED_WITH_CORRECTIONS': {
    shield:'&#9989;', cls:'vc',
    txt:'VERIFIED WITH CORRECTIONS',
    sub:'Agent drifted but DriftWatch corrected it — task completed on goal.'
  },
  'PARTIALLY_VERIFIED': {
    shield:'&#9888;', cls:'vp',
    txt:'PARTIALLY VERIFIED', sub:'Some goal drift occurred, partial correction achieved.'
  },
  'FAILED': {
    shield:'&#10060;', cls:'vx',
    txt:'FAILED', sub:'Goal drift was too severe to correct autonomously.'
  },
};

function renderCert(c, modal=false) {
  const v  = c.verdict || 'FAILED';
  const vm = verdictMap[v] || verdictMap['FAILED'];
  const pfx = modal ? 'modal' : 'cert';

  if (modal) {
    document.getElementById('modalShield').innerHTML  = vm.shield;
    document.getElementById('modalVerdict').textContent = vm.txt;
    document.getElementById('modalVerdict').className   = `modal-verdict-text ${vm.cls}`;
    document.getElementById('modalSub').textContent     = vm.sub;
    renderGauge('modalGaugeArc','modalGaugeText', c.final_score||0, 176, vm.cls);
  } else {
    document.getElementById('certShield').innerHTML  = vm.shield;
    document.getElementById('certVerdict').textContent = vm.txt;
    document.getElementById('certVerdict').className   = `cert-verdict-text ${vm.cls}`;
    document.getElementById('certWrap').className      = `cert-verdict-wrap ${vm.cls}`;
    document.getElementById('certWhat').textContent    = vm.sub;
    renderGauge('gaugeArc','gaugeText', c.final_score||0, 110, vm.cls);
    renderCertStats('certStats', c);
    renderTimeline('certTimeline', c);
  }

  if (modal) {
    renderCertStats('modalStats', c, true);
    renderTimeline('modalTimeline', c);
    document.getElementById('modalInsight').textContent = vm.sub;
  }
}

function renderGauge(arcId, textId, score, total, cls) {
  const arc   = document.getElementById(arcId);
  const textEl= document.getElementById(textId);
  if (!arc || !textEl) return;
  const colors = { vf:'#3fb950', vc:'#3fb950', vp:'#e3b341', vx:'#f85149' };
  arc.style.stroke = colors[cls] || '#3fb950';
  const target = total - (score * total);
  let current  = total;
  const step   = (current - target) / 60;
  let counter  = 0;
  const interval = setInterval(() => {
    current = Math.max(target, current - step);
    arc.setAttribute('stroke-dashoffset', current.toFixed(2));
    counter = Math.min(score, counter + score/60);
    textEl.textContent = counter.toFixed(2);
    if (current <= target) {
      clearInterval(interval);
      textEl.textContent = score.toFixed(2);
    }
  }, 16);
}

function renderCertStats(containerId, c, modal=false) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const stats = [
    ['Final score',   (c.final_score||0).toFixed(4)],
    ['Average score', (c.avg_score||0).toFixed(4)],
    ['Min score',     (c.min_score||0).toFixed(4)],
    ['Total steps',   c.total_steps||0],
    ['Drift events',  c.drift_events||0],
    ['Corrections',   c.corrections_applied||0],
    ['Goal maintained', c.goal_maintained ? 'Yes' : 'No'],
    ['Verdict',       (c.verdict||'').replace(/_/g,' ')],
  ];
  if (modal) {
    el.innerHTML = stats.map(([k,v]) =>
      `<div class="modal-stat">
        <div class="modal-stat-val">${v}</div>
        <div class="modal-stat-lbl">${k}</div>
      </div>`).join('');
  } else {
    el.innerHTML = stats.map(([k,v]) =>
      `<div class="cert-row"><span>${k}</span><span class="v">${v}</span></div>`
    ).join('');
  }
}

function renderTimeline(containerId, c) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const log = c.correction_log || [];
  const driftSteps = new Set(log.map(l => l.step_num));
  el.innerHTML = '';
  for (let i = 1; i <= (c.total_steps || 5); i++) {
    const isDrift = driftSteps.has(i);
    const isCorrected = log.some(l => l.step_num === i && l.tier !== 'TIER_4_ABORT');
    const cls = isDrift
      ? (isCorrected ? 'ct-corr' : 'ct-drift')
      : 'ct-clean';
    const lbl = isDrift ? (isCorrected ? '&#8617;' : '&#215;') : '&#10003;';
    el.innerHTML += `<div class="ct-step ${cls}">${lbl}</div>`;
    if (i < (c.total_steps || 5)) {
      const connCls = isDrift ? 'ct-conn-drift' : 'ct-conn-clean';
      el.innerHTML += `<div class="ct-conn ${connCls}"></div>`;
    }
  }
}

// ── POPUP ─────────────────────────────────────────────────────────────────────
let popupTimer = null;
function showDriftPopup(ev) {
  clearTimeout(popupTimer);
  const popup = document.getElementById('driftPopup');
  document.getElementById('dpHeader').className = 'dp-header alert';
  document.getElementById('dpHeaderTxt').textContent = 'DRIFT DETECTED';
  document.getElementById('dpStep').innerHTML =
    `<strong>Step ${ev.step_num}</strong> &mdash; ${ev.drift_type||''}`;
  document.getElementById('dpScore').innerHTML =
    `Score: <strong style="color:var(--r)">${(ev.score||0).toFixed(3)}</strong> &nbsp; Threshold: ${(ev.threshold||0).toFixed(3)}`;
  document.getElementById('dpBar').style.width = `${Math.round((ev.score||0)*100)}%`;
  document.getElementById('dpBar').style.background = 'var(--r)';
  document.getElementById('dpAction').textContent = '';
  document.getElementById('dpDots').style.display = 'flex';
  popup.className = 'drift-popup show';
}

function updatePopupWithCorrection(ev) {
  document.getElementById('dpHeader').className = 'dp-header fixed';
  document.getElementById('dpHeaderTxt').textContent = 'CORRECTION APPLIED';
  document.getElementById('dpDots').style.display = 'none';
  document.getElementById('dpAction').innerHTML =
    `<span style="color:var(--g)">${corrTierText(ev.correction_tier||'')}</span>`;
  popupTimer = setTimeout(closeDriftPopup, 5000);
}

function closeDriftPopup() {
  document.getElementById('driftPopup').className = 'drift-popup';
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function showModal(cert) {
  renderCert(cert, true);
  document.getElementById('modalBackdrop').className = 'modal-backdrop show';
}
function closeModal(e) {
  if (e && e.target !== document.getElementById('modalBackdrop')) return;
  document.getElementById('modalBackdrop').className = 'modal-backdrop';
  document.getElementById('log').scrollIntoView({ behavior: 'smooth' });
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ── COMPARISON ────────────────────────────────────────────────────────────────
function buildComparison() {
  const d1 = demos[1], d2 = demos[2];
  if (!d1.complete || !d2.complete) return;

  const section = document.getElementById('comparison');
  section.className = 'comparison show';
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Comparison chart
  const cctx = document.getElementById('compCh').getContext('2d');
  if (compChart) compChart.destroy();
  const maxLen = Math.max(d1.scores.length, d2.scores.length);
  const labels = Array.from({ length: maxLen }, (_, i) => `S${i+1}`);
  compChart = new Chart(cctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Demo 1 (Research)', data: d1.scores,
          borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.06)',
          borderWidth: 2, pointRadius: 4, fill: true, tension: .4 },
        { label: 'Demo 2 (Coding)', data: d2.scores,
          borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.06)',
          borderWidth: 2, pointRadius: 4, fill: true, tension: .4 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 1.05,
             ticks: { color:'#8b949e', font:{size:10} },
             grid: { color:'rgba(255,255,255,.04)' } },
        x: { ticks: { color:'#8b949e', font:{size:10} },
             grid: { color:'rgba(255,255,255,.04)' } }
      },
      plugins: { legend: { labels: { color:'#8b949e', font:{size:11} } } }
    }
  });

  // Table
  const avg1 = d1.scores.reduce((a,b)=>a+b,0)/d1.scores.length;
  const avg2 = d2.scores.reduce((a,b)=>a+b,0)/d2.scores.length;
  const rows = [
    ['Task type',    'Research', 'Coding'],
    ['Avg score',    avg1.toFixed(3), avg2.toFixed(3)],
    ['Min score',    Math.min(...d1.scores).toFixed(3), Math.min(...d2.scores).toFixed(3)],
    ['Drift events', d1.drifts, d2.drifts],
    ['Corrections',  d1.corrections, d2.corrections],
    ['Verdict',      (d1.cert?.verdict||'—').replace(/_/g,' '),
                     (d2.cert?.verdict||'—').replace(/_/g,' ')],
  ];
  document.getElementById('compBody').innerHTML = rows.map(([m,a,b]) =>
    `<tr><td>${m}</td><td>${a}</td><td>${b}</td></tr>`
  ).join('');

  // Insight
  const sameverdict = d1.cert?.verdict === d2.cert?.verdict;
  const driftDiff   = Math.abs(d1.drifts - d2.drifts);
  const more        = d1.drifts > d2.drifts ? 'Demo 1' : 'Demo 2';
  let insight = '';
  if (sameverdict) {
    insight = driftDiff > 0
      ? `Both demos achieved the same verdict. ${more} triggered ${driftDiff} more drift event(s), showing that code generation tasks carry higher scope-creep risk.`
      : 'Both demos achieved identical results — DriftWatch maintained goal coherence consistently across both task types.';
  } else {
    insight = `Demos achieved different verdicts. DriftWatch detected more severe drift in ${d1.drifts > d2.drifts ? 'Demo 1' : 'Demo 2'}, requiring stronger correction to recover goal alignment.`;
  }
  document.getElementById('compInsight').textContent = insight;
}

// ── TASK DETECTION ────────────────────────────────────────────────────────────
function detectDemo(task) {
  const t = (task || '').toLowerCase();
  if (t.includes('lithium') || t.includes('groundwater') ||
      t.includes('policy') || t.includes('mining')) return 1;
  if (t.includes('jwt') || t.includes('authentication') ||
      t.includes('token') || t.includes('login')) return 2;
  return activeDemo;
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function connect() {
  const es = new EventSource('/stream');

  es.onmessage = e => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    const { type, data } = msg;
    if (type === 'heartbeat') return;

    if (type === 'task_start') {
      const demoNum = detectDemo(data.task);
      activeDemo = demoNum;
      const d = demos[demoNum];
      d.scores = []; d.thresholds = []; d.events = [];
      d.drifts = 0;  d.corrections = 0; d.complete = false;
      seenSteps = new Set();
      firstLog  = true;

      document.getElementById('taskTxt').textContent = data.task || '—';
      document.getElementById('taskAccent').className = 'task-accent ok';
      document.getElementById('instr').className = 'instr hide';
      document.getElementById('infographic').className = 'infographic hide';
      document.getElementById('corrReplay').className = 'corr-replay';
      document.getElementById('corrCards').innerHTML = '';
      document.getElementById('cert').className = 'cert';

      const dTag = document.getElementById('demoTag');
      dTag.style.display = 'block';
      dTag.className = `demo-tag d${demoNum}`;
      dTag.textContent = `DEMO ${demoNum}`;

      // Tab states
      const otherId = demoNum === 1 ? 'tab2' : 'tab1';
      document.getElementById(`tab${demoNum}`).className = 'tab active';
      document.getElementById(`tab${demoNum}-badge`).className = 'tab-badge badge-running';
      document.getElementById(`tab${demoNum}-badge`).innerHTML =
        '<span class="pulse-dot" style="display:inline-block;vertical-align:middle;margin-right:4px"></span>RUNNING';
      document.getElementById(`tab${demoNum}-dot`).style.display = 'inline';

      resetChart();
      buildPipeline();
      document.getElementById('log').innerHTML = '';

      // Mark active step
      setStepState(1, 'active', null);
    }

    if (type === 'step') {
      const sn  = data.step_num || 1;
      const d   = demos[activeDemo];

      // Deduplicate
      if (d.events.some(e => e.step_num === sn)) return;

      d.scores.push(data.score || 0);
      d.thresholds.push(data.threshold || 0.4);
      d.events.push(data);

      if (data.drift_detected)    d.drifts++;
      if (data.correction_needed) d.corrections++;

      updateMetrics(data);
      document.getElementById('mDrift').textContent = d.drifts;
      document.getElementById('mCorr').textContent  = d.corrections;
      addLogRow(data);
      addChartPt(data.score||0, data.threshold||0.4, data.drift_detected);

      // Pipeline
      const state = data.drift_detected
        ? (data.correction_needed ? 'corrected' : 'drift')
        : 'clean';
      setStepState(sn, state, data);
      if (sn < 5) setStepState(sn+1, 'active', null);

      // Task accent
      document.getElementById('taskAccent').className =
        'task-accent ' + (data.drift_detected ? 'drift' : 'ok');

      if (data.drift_detected) {
        showDriftPopup(data);
        if (data.correction_needed) addCorrCard(data);
      }
      if (data.correction_needed) {
        setTimeout(() => updatePopupWithCorrection(data), 1200);
        document.getElementById('corrBanner').className = 'banner banner-corr show';
        document.getElementById('corrBannerTitle').textContent = 'Correction applied';
        document.getElementById('corrBannerDetail').textContent =
          `${corrTierText(data.correction_tier||'')} — Step ${sn}`;
        setTimeout(() => {
          document.getElementById('corrBanner').className = 'banner banner-corr';
        }, 5000);
      }
    }

    if (type === 'task_complete') {
      const demoNum = activeDemo;
      const d = demos[demoNum];
      d.cert     = data;
      d.complete = true;

      document.getElementById(`tab${demoNum}-badge`).className = 'tab-badge badge-complete';
      document.getElementById(`tab${demoNum}-badge`).textContent = 'COMPLETE \u2713';
      document.getElementById(`tab${demoNum}-dot`).style.display = 'none';
      document.getElementById('taskAccent').className = 'task-accent ok';
      document.getElementById('instr').className = 'instr';
      document.getElementById('infographic').className = 'infographic';

      // Show inline cert
      document.getElementById('cert').className = 'cert show';
      renderCert(data);

      // Show modal after short delay
      setTimeout(() => showModal(data), 900);

      // Comparison
      if (demos[1].complete && demos[2].complete) {
        setTimeout(buildComparison, 600);
      }
    }

    if (type === 'correction') {
      addCorrCard(data);
      updatePopupWithCorrection(data);
    }

    if (type === 'state_sync') {
      if ((data.scores||[]).length > 0) {
        const demoNum = detectDemo(data.task);
        activeDemo = demoNum;
        const d = demos[demoNum];
        data.scores.forEach((sc, i) => {
          if (!d.events[i]) {
            d.scores.push(sc);
            d.thresholds.push((data.thresholds||[])[i] || 0.4);
          }
        });
        if (data.task) document.getElementById('taskTxt').textContent = data.task;
        loadChartFromDemo(demoNum);
        if (data.is_complete && data.certificate) {
          d.cert     = data.certificate;
          d.complete = true;
          document.getElementById('cert').className = 'cert show';
          renderCert(data.certificate);
        }
        document.getElementById('instr').className = 'instr hide';
      }
    }
  };

  es.onerror = () => {
    document.getElementById('connPill').className = 'conn-pill conn-err';
    document.getElementById('connPill').innerHTML =
      '<span style="width:6px;height:6px;border-radius:50%;background:var(--r);display:inline-block"></span> RECONNECTING';
    setTimeout(() => {
      connect();
      document.getElementById('connPill').className = 'conn-pill conn-ok';
      document.getElementById('connPill').innerHTML =
        '<span style="width:6px;height:6px;border-radius:50%;background:var(--g);display:inline-block"></span> CONNECTED';
    }, 3000);
  };
}
connect();
</script>
</body>
</html>
"""

@app.route("/observatory")
def dashboard():
    return DASHBOARD

@app.route("/")
def index():
    return render_template("onboarding.html")

@app.route("/execution/<session_id>")
def execution(session_id):
    return render_template("execution.html", session_id=session_id)

@app.route("/review/<session_id>")
def review_page(session_id):
    return render_template("review.html", session_id=session_id)

@app.route("/api/step1/submit", methods=["POST"])
def step1_submit():
    task = request.json.get("task", "").strip()
    if len(task) < 10:
        return jsonify({"error": "Task description too short. "
                        "Please provide more detail."}), 400
    ws = WorkflowSession(task=task)
    ws.save()
    return jsonify({"session_id": ws.session_id, "next_step": 2})

@app.route("/api/step2/decompose", methods=["POST"])
def step2_decompose():
    session_id = request.json.get("session_id")
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    try:
        anchors = GoalAnchor().decompose(ws_data["task"])
    except Exception as e:
        # Fallback: split task into simple anchors if LLM fails
        anchors = [ws_data["task"]]
    ws_data["goal_anchors"] = anchors
    save_session_dict(session_id, ws_data)
    return jsonify({"anchors": anchors,
                    "message": "Review these goals. Edit if needed."})

@app.route("/api/step2/confirm", methods=["POST"])
def step2_confirm():
    session_id  = request.json.get("session_id")
    edited      = request.json.get("anchors", [])
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    ws_data["goal_anchors"] = edited
    save_session_dict(session_id, ws_data)
    return jsonify({"next_step": 3})

@app.route("/api/step3/configure", methods=["POST"])
def step3_configure():
    session_id = request.json.get("session_id")
    level      = request.json.get("sensitivity", "medium")
    risk_map   = {"low": 0.60, "medium": 0.75, "high": 0.88}
    sensitivity = risk_map.get(str(level).lower(), 0.75)
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    ws_data["sensitivity"] = sensitivity
    save_session_dict(session_id, ws_data)
    return jsonify({"sensitivity": sensitivity, "next_step": 4})

@app.route("/api/step4/launch", methods=["POST"])
def step4_launch():
    session_id = request.json.get("session_id")
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    ws_data["phase"] = SessionPhase.EXECUTING.value
    save_session_dict(session_id, ws_data)

    def run_agent_task():
        # Import your existing agent runner here
        # Pass session_id and push_sse_event callback into it
        from agent.base_agent import run_with_driftwatch
        push_fn = lambda etype, data: push_sse_event(
            session_id, etype, data
        )
        try:
            result = run_with_driftwatch(
                task        = ws_data["task"],
                anchors     = ws_data["goal_anchors"],
                sensitivity = ws_data["sensitivity"],
                session_id  = session_id,
                sse_push_fn = push_fn
            )
            # Save final output
            loaded = WorkflowSession.load(session_id)
            loaded["corrected_output"] = result.get("output", "")
            loaded["raw_output"]       = result.get("raw_output", "")
            loaded["phase"]            = SessionPhase.REVIEWING.value
            save_session_dict(session_id, loaded)
            push_sse_event(session_id, "execution_complete",
                           {"session_id": session_id})
        except Exception as e:
            try:
                loaded = WorkflowSession.load(session_id)
                loaded["error_message"] = str(e)
                loaded["raw_output"] = f"Error: {str(e)}"
                loaded["corrected_output"] = f"Error: {str(e)}"
                loaded["phase"] = SessionPhase.COMPLETE.value
                save_session_dict(session_id, loaded)
            except Exception as se:
                print(f"[DriftWatch] Warning: could not save error session: {se}")
            push_sse_event(session_id, "execution_error",
                           {"error": str(e), "session_id": session_id})

    t = threading.Thread(target=run_agent_task, daemon=True)
    t.start()
    return jsonify({"status": "launched", "session_id": session_id})

@app.route("/api/decision/<session_id>", methods=["POST"])
def user_decision(session_id):
    decision = request.json.get("decision")
    if decision not in ("approve", "reject"):
        return jsonify({"error": "decision must be approve or reject"}), 400
    resolved = resolve_decision(session_id, decision)
    if not resolved:
        return jsonify({"error": "No pending decision for this session"}), 404
    try:
        ws_data = WorkflowSession.load(session_id)
        ws_data.setdefault("user_decisions", []).append({
            "decision": decision,
            "timestamp": time.time()
        })
        save_session_dict(session_id, ws_data)
    except Exception:
        pass
    return jsonify({"status": "decision_recorded", "decision": decision})

@app.route("/api/review/<session_id>")
def review_data(session_id):
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    scores = [s["drift_score"] for s in ws_data.get("steps", [])
              if isinstance(s.get("drift_score"), (int, float))]
    avg    = round(sum(scores) / len(scores), 3) if scores else 0.0
    events = ws_data.get("drift_events", [])
    high_tier_count = sum(1 for e in events if e.get("tier", 0) >= 3
                          and e.get("status") != "user_rejected")
    if avg >= 0.80 and high_tier_count == 0:
        cert = "PASS"
    elif avg >= 0.65 or high_tier_count <= 1:
        cert = "WARN"
    else:
        cert = "FAIL"
    ws_data["coherence_certificate"] = cert
    ws_data["final_score"]           = avg
    ws_data["phase"]                 = SessionPhase.COMPLETE.value
    save_session_dict(session_id, ws_data)
    return jsonify({
        "raw_output":            ws_data.get("raw_output", ""),
        "corrected_output":      ws_data.get("corrected_output", ""),
        "certificate":           cert,
        "certificate_meaning":   get_certificate_meaning(cert),
        "final_score":           avg,
        "drift_timeline":        events,
        "steps":                 ws_data.get("steps", []),
        "user_decisions":        ws_data.get("user_decisions", [])
    })

@app.route("/api/stream/<session_id>")
def sse_stream(session_id):
    def generate():
        seen = 0
        while True:
            queue = _sse_queues.get(session_id, [])
            while seen < len(queue):
                item = queue[seen]
                data = dict(item['data']) if isinstance(item['data'], dict) else {"data": item['data']}
                data['session_id'] = session_id
                yield f"event: {item['event']}\n"
                yield f"data: {json.dumps(data)}\n\n"
                seen += 1
            time.sleep(0.3)
            # Check if execution complete
            if seen > 0 and queue and \
               queue[-1].get("event") in ("execution_complete", "execution_error"):
                break
    return Response(generate(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no",
                             "Access-Control-Allow-Origin": "*"})

@app.route("/api/export/<session_id>")
def export_session(session_id):
    try:
        ws_data = WorkflowSession.load(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404
    import json
    response = Response(
        json.dumps(ws_data, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition":
                f"attachment; filename=driftwatch_audit_{session_id}.json"
        }
    )
    return response

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    print(f"\n{'='*55}")
    print(f"  DriftWatch Dashboard — http://localhost:{port}")
    print(f"{'='*55}")
    print(f"  Dashboard is running. Now open a SECOND terminal and run:")
    print(f"  python mvp.py --demo1")
    print(f"  python mvp.py --demo2")
    print(f"  python mvp.py --both")
    print(f"{'='*55}\n")
    app.run(host="0.0.0.0", port=port, debug=False,
            threaded=True, use_reloader=False)
