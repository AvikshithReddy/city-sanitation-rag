# app.py
from __future__ import annotations

import re
from pathlib import Path
import streamlit as st
import networkx as nx

# ---- put page config at the top (before other st.* calls) ----
st.set_page_config(page_title="Advanced Multi-Source RAG — Demo", layout="wide")
st.title("Advanced Multi-Source RAG — Demo")
st.caption("Ask about recycling, brush & bulky, medicine disposal, holiday schedules, prices, etc.")

CORPUS = Path("data/unified/corpus.jsonl")
GRAPH_PATH = Path("data/indices/graph.gpickle")

# ---------- SECTION 3: cache heavy objects ----------
@st.cache_resource(show_spinner=False)
def load_retriever():
    if not CORPUS.exists():
        raise FileNotFoundError(
            f"Missing {CORPUS}. Run ingestion and merge first:\n"
            "  python ingestion/web_loader.py\n"
            "  python ingestion/excel_loader.py\n"
            "  python ingestion/pdf_calendar_loader.py\n"
            "  cat data/unified/*.jsonl > data/unified/corpus.jsonl"
        )
    from retrieval.retriever import SimpleMultiRetriever
    return SimpleMultiRetriever(str(CORPUS))

@st.cache_resource(show_spinner=False)
def load_graph():
    if GRAPH_PATH.exists():
        try:
            return nx.read_gpickle(GRAPH_PATH)
        except Exception:
            return None
    return None
# ----------------------------------------------------

# lazy-load with friendly errors
try:
    retriever = load_retriever()
except Exception as e:
    st.error(f"Retriever failed to load: {e}")
    st.stop()

G = load_graph()

# ---------- helpers for concise, cited answers ----------

import itertools

NEG_PATTERNS = (
    "not collected", "not accepted", "does not accept",
    "no ", "do not ", "cannot ", "can't ", "no styrofoam", "no plastic bags"
)

def _unique_sources(hits, limit=None):
    seen, out = set(), []
    for h in hits:
        src = h["meta"].get("url") or h["meta"].get("source_id")
        if src and src not in seen:
            seen.add(src); out.append(src)
            if limit and len(out) >= limit:
                break
    return out

def _short_sentences(text, min_len=40, max_chars=220):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    parts = [p.strip() for p in parts if len(p.strip()) >= min_len]
    out = []
    for p in parts:
        if len(p) <= max_chars:
            out.append(p)
        else:
            out.append(p[:max_chars].rstrip() + "…")
    return out

def _extract_negatives(hits, max_items=6):
    """
    Pull short 'not accepted / not collected' items from hit texts.
    Looks for lines/sentences containing 'no', 'not accepted', etc.
    """
    items = []
    for h in hits:
        txt = re.sub(r"\s+", " ", h["text"])
        # slice by separators
        chunks = re.split(r"[•\-\–\—\|]|(?<=[.!?])\s+", txt)
        for c in chunks:
            c_clean = c.strip()
            lc = c_clean.lower()
            if any(p in lc for p in NEG_PATTERNS):
                # normalize leading "no " / bullets
                c_clean = re.sub(r"^\W*(no\s+|not\s+)", "", c_clean, flags=re.I)
                # keep it short
                c_clean = re.sub(r"\s+", " ", c_clean)
                if 2 <= len(c_clean) <= 70:
                    items.append((c_clean, h))
            if len(items) >= max_items:
                break
        if len(items) >= max_items:
            break
    return items

def concise_answer(query: str, hits: list, max_bullets: int = 3, max_chars: int = 200):
    """Intent-aware concise answer with numbered citations."""
    if not hits:
        return ["• No matching content found. Try rephrasing."], []

    ql = query.lower()

    # 1) Intent: "not collected / not accepted"
    if any(k in ql for k in ["not collected", "not accepted", "can't recycle", "cannot recycle", "what items are not"]):
        neg_items = _extract_negatives(hits, max_items=max_bullets * 2)
        if neg_items:
            # group by source and map citations
            sources = _unique_sources([h for _, h in neg_items], limit=max_bullets)
            src_idx = {s: i + 1 for i, s in enumerate(sources)}
            bullets = []
            for text, h in neg_items[: max_bullets]:
                src = h["meta"].get("url") or h["meta"].get("source_id")
                ci = src_idx.get(src, 1)
                bullets.append(f"• Not collected: {text} [{ci}]")
            return bullets, sources

    # 2) Intent: simple “what’s accepted / what are the rules”
    if any(k in ql for k in ["what items", "what can i", "what is accepted", "accepted items", "allowed items"]):
        lines = []
        for h in hits:
            sents = _short_sentences(h["text"], min_len=30, max_chars=max_chars)
            if sents:
                lines.append((sents[0], h))
            if len(lines) >= max_bullets:
                break
        if lines:
            sources = _unique_sources([h for _, h in lines], limit=max_bullets)
            src_idx = {s: i + 1 for i, s in enumerate(sources)}
            bullets = []
            for sent, h in lines:
                src = h["meta"].get("url") or h["meta"].get("source_id")
                ci = src_idx.get(src, 1)
                bullets.append(f"• {sent} [{ci}]")
            return bullets, sources

    # 3) Default: pick short sentences from top hits
    keep = []
    for h in hits:
        sents = _short_sentences(h["text"], min_len=40, max_chars=max_chars)
        if sents:
            keep.append((sents[0], h))
        if len(keep) >= max_bullets:
            break

    if not keep:
        # last resort: truncate one hit
        sources = _unique_sources(hits, limit=1)
        return [f"• {re.sub(r'\\s+',' ', hits[0]['text'])[:max_chars]}… [1]"], sources

    sources = _unique_sources([h for _, h in keep], limit=max_bullets)
    src_idx = {s: i + 1 for i, s in enumerate(sources)}
    bullets = []
    for sent, h in keep:
        src = h["meta"].get("url") or h["meta"].get("source_id")
        ci = src_idx.get(src, 1)
        bullets.append(f"• {sent} [{ci}]")
    return bullets, sources

# ---------- SECTION 4: graph shortcuts (exact answers when possible) ----------
def try_graph_answer(q: str):
    """Very small rules to answer price/date questions directly from the graph."""
    if not G:
        return None

    ql = q.lower()
    # price lookup
    if any(w in ql for w in ("price", "cost", "fee")):
        for u, v, d in G.edges(data=True):
            if d.get("rel") == "has_price" and u.startswith("product:"):
                prod = u.split("product:", 1)[-1]
                if prod and prod in ql:
                    price = v.split("price:", 1)[-1]
                    return [f"• {prod} price → {price} [1]"], ["prices.csv"]

    # simple date/event lookup (holiday/bulky etc.)
    if any(w in ql for w in ("when", "date", "pickup", "holiday", "schedule")):
        for u, v, d in G.edges(data=True):
            if d.get("rel") == "occurs_on" and u.startswith("event:"):
                ev = u.split("event:", 1)[-1]
                # naive token overlap
                if any(tok in ql for tok in ev.split()):
                    date = v.split("date:", 1)[-1]
                    return [f"• {ev} → {date} [1]"], ["calendar_events.csv"]

    return None
# ----------------------------------------------------

with st.sidebar:
    st.subheader("Settings")
    k_total = st.slider("Results (k)", 2, 8, 4)
    bullets_max = st.slider("Answer bullets", 1, 4, 2)
    char_cap = st.slider("Chars per bullet", 80, 220, 180, step=10)
    st.caption("Answers are extractive (no external LLM needed).")

# Use a small form so Enter submits
with st.form("qform", clear_on_submit=False):
    query = st.text_input("Your question")
    go = st.form_submit_button("Search")

if go and query:
    # try exact/structured response first
    direct = try_graph_answer(query)
    hits = None
    if direct:
        bullets, sources = direct
    else:
        hits = retriever.search(query, k_total=k_total)  # compute once
        bullets, sources = concise_answer(query, hits, max_bullets=bullets_max, max_chars=char_cap)

    st.subheader("Answer")
    for b in bullets:
        st.write(b)

    st.subheader("Sources")
    if not sources:
        st.write("No sources available.")
    else:
        for i, s in enumerate(sources, start=1):
            if s.startswith("http"):
                st.markdown(f"{i}. [{s}]({s})")
            else:
                st.markdown(f"{i}. {s}")

    # Optional: show supporting snippets for debugging (reuse hits)
    if hits:
        with st.expander("Supporting snippets"):
            for h in hits:
                src = h["meta"].get("url") or h["meta"].get("source_id")
                st.markdown(f"- **{h['text']}**  \n  _source_: {src}")