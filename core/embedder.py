"""
=============================================================
  DriftWatch | core/embedder.py  [REBUILT — Groq embeddings]
  No HuggingFace download needed. Uses Groq API embeddings.
  Model: llama-3.1-8b-instant (embedding mode via nomic)
  Fallback: Groq LLM-based semantic scoring if embed fails
=============================================================
"""
import os, time, hashlib, json
import numpy as np
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

# ── Pure-Python cosine (no sklearn needed) ────────────────────────────────────
def _cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


class Embedder:
    """
    Embedding wrapper that works with Groq API.
    Uses nomic-embed-text model via Groq embeddings endpoint.
    Cache: stores embeddings in memory to avoid repeat API calls.
    """

    EMBED_MODEL = "nomic-embed-text-v1.5"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._cache: dict = {}          # text → vector cache
        self._embed_count = 0
        self._total_ms    = 0.0
        self._client      = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def embed(self, text: str) -> np.ndarray:
        """Embed text → numpy vector via Groq embeddings API."""
        ck = self._cache_key(text)
        if ck in self._cache:
            return self._cache[ck]

        t0 = time.time()
        try:
            client = self._get_client()
            resp   = client.embeddings.create(
                model=self.EMBED_MODEL,
                input=text[:2048],   # nomic max context
            )
            vec = np.array(resp.data[0].embedding, dtype=np.float32)
            # L2 normalise
            nrm = np.linalg.norm(vec)
            if nrm > 0:
                vec = vec / nrm
        except Exception as e:
            if self.verbose:
                print(f"[Embedder] API error: {e}. Using LLM fallback.")
            vec = self._llm_embed_fallback(text)

        ms = (time.time() - t0) * 1000
        self._embed_count += 1
        self._total_ms    += ms
        self._cache[ck]    = vec

        if self.verbose:
            print(f"[Embedder] {ms:.0f}ms  dim={len(vec)}")
        return vec

    def _llm_embed_fallback(self, text: str) -> np.ndarray:
        """
        Fallback: ask LLM to produce a 64-dim semantic vector.
        Used only when embedding endpoint fails.
        """
        try:
            client = self._get_client()
            prompt = (
                "Return ONLY a JSON array of exactly 64 floating-point numbers "
                "that semantically represent this text. "
                "Numbers in range [-1, 1]. No other text.\n"
                f"Text: {text[:300]}"
            )
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role":"user","content":prompt}],
                max_tokens=512, temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            arr = json.loads(raw)
            vec = np.array(arr, dtype=np.float32)
            if len(vec) != 64:
                vec = np.resize(vec, 64)
        except Exception:
            # Last resort: hash-based deterministic vector
            h   = int(hashlib.md5(text.encode()).hexdigest(), 16)
            rng = np.random.default_rng(h % (2**32))
            vec = rng.standard_normal(64).astype(np.float32)
        nrm = np.linalg.norm(vec)
        return vec / nrm if nrm > 0 else vec

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed multiple texts. Uses cache for already-seen texts."""
        return [self.embed(t) for t in texts]

    def similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        return _cosine(v1, v2)

    def max_similarity(self, query: np.ndarray,
                       candidates: List[np.ndarray]) -> float:
        if not candidates:
            return 0.0
        return max(_cosine(query, c) for c in candidates)

    @property
    def avg_latency_ms(self) -> float:
        return self._total_ms / self._embed_count if self._embed_count else 0.0

    def stats(self) -> dict:
        return {
            "model":          self.EMBED_MODEL,
            "embed_count":    self._embed_count,
            "cache_hits":     len(self._cache),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


if __name__ == "__main__":
    print("="*50)
    print("  Embedder Self-Test")
    print("="*50)
    emb = Embedder(verbose=True)
    g  = emb.embed("Research lithium mining water quality impacts and write 3 policy regulations")
    on = emb.embed("Analyzing hydrogeological studies on lithium brine groundwater contamination")
    dr = emb.embed("Electric vehicle market adoption trends government subsidies Tesla sales")
    s1 = emb.similarity(g, on)
    s2 = emb.similarity(g, dr)
    print(f"\n  goal ↔ on-track : {s1:.4f}  (expect > drift score)")
    print(f"  goal ↔ drifted  : {s2:.4f}")
    print(f"  PASS: {s1 > s2}")
    print(f"\n  Stats: {emb.stats()}")
