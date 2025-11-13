# indexing/build_indices.py
from pathlib import Path
import json

CORPUS = Path("data/unified/corpus.jsonl")
INDICES_DIR = Path("data/indices"); INDICES_DIR.mkdir(parents=True, exist_ok=True)
SENTWIN_PATH = INDICES_DIR / "sentwin.jsonl"
FAISS_DIR = INDICES_DIR / "faiss"

# --- sentence-window builder (always works) -------------------------------
def load_chunks():
    """Return list of dicts: {'id','text','meta'} using a light splitter."""
    import re
    chunks = []
    with open(CORPUS, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            text = rec.get("text", "")
            # simple sentence-ish split, then pack to ~450 words with 80 overlap
            sents = re.split(r'(?<=[.!?])\s+', text.strip())
            words = (" ".join(sents)).split()
            if not words: 
                continue
            start, L, O = 0, 450, 80
            while start < len(words):
                end = min(start + L, len(words))
                chunk = " ".join(words[start:end]).strip()
                if chunk:
                    chunks.append({"id": rec["id"], "text": chunk, "meta": rec.get("meta", {})})
                if end == len(words): break
                start = max(0, end - O)
    return chunks

def build_sentence_window(chunks):
    with open(SENTWIN_PATH, "w", encoding="utf-8") as w:
        for n in chunks:
            w.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"✅ Built sentence-window: {SENTWIN_PATH} ({sum(1 for _ in open(SENTWIN_PATH))} nodes)")

# --- FAISS + LlamaIndex (optional) ----------------------------------------
def build_faiss_index(chunks):
    """Build a FAISS vector index via LlamaIndex if available."""
    try:
        import faiss  # noqa: F401
        from llama_index.core import VectorStoreIndex, StorageContext
        from llama_index.core.schema import TextNode
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        from llama_index.vector_stores.faiss import FaissVectorStore
    except Exception as e:
        print(f"⚠️  Skipping FAISS/LlamaIndex build ({e}). Sentence-window is still available.")
        return

    # convert dicts -> TextNodes
    li_nodes = [TextNode(text=n["text"], id_=n["id"], metadata=n.get("meta", {})) for n in chunks]

    emb = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    vec_store = FaissVectorStore()  # creates an in-memory faiss.IndexFlatIP lazily
    storage = StorageContext.from_defaults(vector_store=vec_store, persist_dir=str(FAISS_DIR))

    # Build index from nodes (current API)
    _ = VectorStoreIndex(nodes=li_nodes, storage_context=storage, embed_model=emb)

    # Persist to disk
    storage.persist(persist_dir=str(FAISS_DIR))
    print(f"✅ Built FAISS index at {FAISS_DIR}")

# --- main -----------------------------------------------------------------
if __name__ == "__main__":
    if not CORPUS.exists():
        raise SystemExit(f"Missing {CORPUS}. Run ingestion + merge first.")

    chunks = load_chunks()
    build_sentence_window(chunks)
    build_faiss_index(chunks)