"""
=============================================================
  DriftWatch | core/embedder.py
  Uses local sentence-transformers (all-MiniLM-L6-v2) for 
  ultra-fast, free, offline 384-dimensional embeddings.
=============================================================
"""
import os, time
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer

# Pure-Python cosine (no sklearn needed)
def _cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


class Embedder:
    """
    Embedding wrapper that works with sentence-transformers.
    Uses all-MiniLM-L6-v2 locally (384-dimensional vector).
    Cache: stores embeddings in memory to avoid repeat calculations.
    """

    EMBED_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._cache = {}          # text → vector cache
        self._embed_count = 0
        self._total_ms    = 0.0
        self._model = SentenceTransformer(self.EMBED_MODEL)
        # Warmup to trigger PyTorch initialization/compilation before time-tracking starts
        self._model.encode("warmup")

    def embed(self, text: str) -> np.ndarray:
        """Embed text → 384-dim numpy vector."""
        if text in self._cache:
            return self._cache[text]

        t0 = time.time()
        try:
            vec = self._model.encode(text)
            # Ensure it is a numpy float32 array
            vec = np.array(vec, dtype=np.float32)
            # L2 normalise
            nrm = np.linalg.norm(vec)
            if nrm > 0:
                vec = vec / nrm
        except Exception as e:
            if self.verbose:
                print(f"[Embedder] Encode error: {e}")
            # Last resort: deterministic fallback
            import hashlib
            h   = int(hashlib.md5(text.encode()).hexdigest(), 16)
            rng = np.random.default_rng(h % (2**32))
            vec = rng.standard_normal(384).astype(np.float32)
            nrm = np.linalg.norm(vec)
            if nrm > 0:
                vec = vec / nrm

        ms = (time.time() - t0) * 1000
        self._embed_count += 1
        self._total_ms    += ms
        self._cache[text]  = vec

        if self.verbose:
            print(f"[Embedder] {ms:.0f}ms  dim={len(vec)}")
        return vec

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed multiple texts."""
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
