# retrieval/retriever.py
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer, util

from .fusion import rrf  # simple Reciprocal Rank Fusion

SENTWIN = Path("data/indices/sentwin.jsonl")


# ----------------------------
# Device selection (fixes "meta tensor" crash)
# ----------------------------
def _pick_device() -> str:
    """
    Prefer Apple's MPS on Mac if available, else CPU.
    Keeps things stable across PyTorch builds.
    """
    try:
        import torch

        if getattr(torch.backends, "mps", None):
            if torch.backends.mps.is_available() and torch.backends.mps.is_built():
                return "mps"
    except Exception:
        pass
    return "cpu"


# ----------------------------
# Optional cross-encoder reranker (small & fast)
# ----------------------------
try:
    from sentence_transformers import CrossEncoder

    _CROSS = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
except Exception:
    _CROSS = None


def cross_rerank(query: str, docs: List[Dict], topk: int = 6) -> List[Dict]:
    """Rerank with a cross-encoder if available, else no-op."""
    if not docs or _CROSS is None:
        return docs
    pairs = [(query, d["text"]) for d in docs]
    scores = _CROSS.predict(pairs)
    order = np.argsort(-scores)[:topk]
    return [docs[i] for i in order]


# ----------------------------
# MMR diversification (reduce near-duplicates)
# ----------------------------
def mmr(
    query_emb: np.ndarray, doc_embs: np.ndarray, k: int = 6, lambda_: float = 0.6
) -> List[int]:
    """
    Maximal Marginal Relevance:
    select k indices balancing relevance to query and dissimilarity to chosen docs.
    """
    if doc_embs.size == 0:
        return []

    sim_to_query = (doc_embs @ query_emb.T).ravel()
    candidates = list(range(len(doc_embs)))
    selected: List[int] = []

    # pick best first
    first = int(np.argmax(sim_to_query))
    selected.append(first)
    candidates.remove(first)

    while candidates and len(selected) < k:
        # diversity: max similarity to any already selected doc
        if len(selected) == 1:
            div = (doc_embs[candidates] @ doc_embs[selected[0]].T).ravel()
        else:
            div = np.max(doc_embs[candidates] @ doc_embs[selected].T, axis=1)

        cand_rel = sim_to_query[candidates]
        score = lambda_ * cand_rel - (1.0 - lambda_) * div
        nxt = candidates[int(np.argmax(score))]
        selected.append(nxt)
        candidates.remove(nxt)

    return selected


# ----------------------------
# Retriever
# ----------------------------
class SimpleMultiRetriever:
    """
    Minimal multi-retriever:
      - Vector similarity over corpus chunks
      - Sentence-window keyword hits
      - RRF fuse -> MMR -> optional cross-encoder rerank
    """

    def __init__(self, corpus_path: str = "data/unified/corpus.jsonl"):
        self.device = _pick_device()
        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2", device=self.device
        )

        # Load corpus
        with open(corpus_path, "r", encoding="utf-8") as f:
            self.corpus: List[Dict] = [json.loads(l) for l in f]

        self.texts = [c["text"] for c in self.corpus]

        # Precompute embeddings (numpy on CPU for simplicity)
        self.embs = self.model.encode(
            self.texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        # Sentence-window nodes (optional extra signal)
        self.sentwin_nodes: List[Dict] = (
            [json.loads(l) for l in open(SENTWIN, "r", encoding="utf-8")]
            if SENTWIN.exists()
            else []
        )

    # -------- helpers --------
    def _vector_hits(self, query: str, topn: int = 20) -> List[Tuple[int, float]]:
        q = self.model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[
            0
        ]
        sims = (self.embs @ q).ravel()
        # take topn indices
        idxs = sims.argsort()[-topn:][::-1]
        return [(int(i), float(sims[int(i)])) for i in idxs]

    def _sentence_window_hits(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
        """
        Very lightweight keyword overlap against sentence-window nodes,
        then map back to corpus indices by exact text match if possible.
        """
        if not self.sentwin_nodes:
            return []

        q_tokens = set(query.lower().split())
        scored: List[Tuple[int, float]] = []

        # quick scoring: count token overlaps
        for n in self.sentwin_nodes:
            t = n.get("text", "").lower()
            if not t:
                continue
            score = sum(1 for w in q_tokens if w in t)
            if score > 0:
                scored.append((t, float(score)))

        if not scored:
            return []

        # take top-k unique texts
        scored.sort(key=lambda x: x[1], reverse=True)
        top_texts = [t for t, _ in scored[:k]]

        # map each text back to first matching corpus index (best-effort)
        hits: List[Tuple[int, float]] = []
        text_to_idx = {c["text"]: i for i, c in enumerate(self.corpus)}
        for t in top_texts:
            i = text_to_idx.get(t)
            if i is not None:
                hits.append((int(i), 1.0))
        return hits

    # -------- public API --------
    def search(self, query: str, k_total: int = 6) -> List[Dict]:
        # 1) Retrieve from both sources
        v_hits = self._vector_hits(query, topn=20)
        s_hits = self._sentence_window_hits(query, k=10)

        # 2) Fuse results with RRF
        fused = rrf([v_hits, s_hits])  # returns list[(idx, score)]
        fused_idxs = [i for i, _ in fused][: max(20, k_total)]

        if not fused_idxs:
            return []

        # 3) MMR diversification on fused pool
        qemb = self.model.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True
        )[0]
        pool_embs = self.embs[fused_idxs]
        keep_rel = mmr(qemb, pool_embs, k=k_total, lambda_=0.6)

        docs = [self.corpus[fused_idxs[i]] for i in keep_rel]

        # 4) Optional cross-encoder final rerank (polish)
        docs = cross_rerank(query, docs, topk=k_total)

        return docs
    