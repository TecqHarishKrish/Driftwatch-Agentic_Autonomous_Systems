"""
=============================================================
  DriftWatch — test_setup.py
  DAY 0 — Run this FIRST before any other file
  Verifies: embedder speed, Groq connection, environment
=============================================================
  Usage: python test_setup.py
=============================================================
"""

import time
import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("\n" + "=" * 60)
print("  DriftWatch — Environment Verification")
print("=" * 60)

all_passed = True


# ─────────────────────────────────────────────
# TEST 1: Python version
# ─────────────────────────────────────────────
print("\n[1/4] Checking Python version...")
version = sys.version_info
if version.major == 3 and version.minor >= 9:
    print(f"  OK  Python {version.major}.{version.minor}.{version.micro}")
else:
    print(f"  FAIL  Python {version.major}.{version.minor} detected — need 3.9+")
    all_passed = False


# ─────────────────────────────────────────────
# TEST 2: Embedder speed benchmark
# ─────────────────────────────────────────────
print("\n[2/4] Loading sentence-transformers embedder...")
print("      (First load takes 10-30s to download model)")
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    start = time.time()
    model = SentenceTransformer("all-MiniLM-L6-v2")
    load_time = (time.time() - start) * 1000
    print(f"  OK  Model loaded in {load_time:.0f}ms")

    _ = model.encode("warmup")

    test_text = "Research the impact of lithium mining on water quality"
    start = time.time()
    v1 = model.encode(test_text)
    single_time = (time.time() - start) * 1000

    v2 = model.encode("Write policy recommendations for electric vehicle subsidies")
    sim = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

    print(f"  OK  Single embed: {single_time:.1f}ms  (target: <100ms)")
    print(f"  OK  Cosine similarity test: {sim:.4f}")

    if single_time > 200:
        print("  WARN  Embed speed slow — CPU only. Still usable.")
    else:
        print("  OK  Embed speed within acceptable range")

except ImportError:
    print("  FAIL  sentence-transformers not installed")
    print("     Run: pip install sentence-transformers")
    all_passed = False
except Exception as e:
    print(f"  FAIL  Error: {e}")
    all_passed = False


# ─────────────────────────────────────────────
# TEST 3: Groq API connection
# ─────────────────────────────────────────────
print("\n[3/4] Testing Groq API connection...")
groq_key = os.getenv("GROQ_API_KEY")

if not groq_key or groq_key == "your_groq_api_key_here":
    print("  FAIL  GROQ_API_KEY not set in .env file")
    print("     1. Copy .env.example to .env")
    print("     2. Get free key at: https://console.groq.com")
    print("     3. Paste key into .env file")
    all_passed = False
else:
    try:
        from groq import Groq

        client = Groq(api_key=groq_key)
        start = time.time()
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "groq/compound"),
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly 3 words: GROQ CONNECTION VERIFIED",
                }
            ],
            max_tokens=10,
            temperature=0,
        )
        elapsed = (time.time() - start) * 1000
        reply = resp.choices[0].message.content.strip()
        print(f"  OK  Groq response: '{reply}'")
        print(f"  OK  Latency: {elapsed:.0f}ms")

    except Exception as e:
        print(f"  FAIL  Groq connection failed: {e}")
        print("     Check your API key at https://console.groq.com")
        all_passed = False


# ─────────────────────────────────────────────
# TEST 4: LangGraph import
# ─────────────────────────────────────────────
print("\n[4/4] Checking LangGraph...")
try:
    import langgraph
    import langchain
    print("  OK  LangGraph package imported successfully")
    print(f"  OK  LangChain {langchain.__version__}")
except ImportError as e:
    print(f"  FAIL  {e}")
    print("     Run: pip install langgraph langchain langchain-groq")
    all_passed = False


# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
if all_passed:
    print("  ALL CHECKS PASSED — Ready to build DriftWatch")
    print("  Next: start with Day 1 files")
else:
    print("  SOME CHECKS FAILED — Fix above errors before proceeding")
print("=" * 60 + "\n")
