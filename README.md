System Architecture — Advanced Multi-Source RAG Pipeline

┌──────────────────────────────────────────────────────────────────────────────┐
│                           1. Streamlit User Interface                         │
│──────────────────────────────────────────────────────────────────────────────│
│ • User enters a natural-language question                                     │
│ • Query sent to the back-end RAG engine                                       │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Query
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                           2. Data Ingestion Pipeline                          │
│──────────────────────────────────────────────────────────────────────────────│
│ • Web Loader (HTML pages)                                                     │
│ • Excel Loader (Fees, schedules, prices)                                      │
│ • PDF Loader (bulky pickup calendars, event dates)                            │
│ • All processed files converted into JSONL format                              │
│   → stored in `data/unified/corpus.jsonl`                                     │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Unified Corpus (JSONL)
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                               3. Processing Layer                             │
│──────────────────────────────────────────────────────────────────────────────│
│ • Cleaning (HTML stripping, trafilatura + BeautifulSoup fallback)             │
│ • Chunking via SentenceSplitter (450 tokens, 80 overlap)                       │
│ • Metadata tagging (source URL, title, file path, etc.)                       │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Clean chunks + metadata
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                                4. Indexing Layer                              │
│──────────────────────────────────────────────────────────────────────────────│
│ • FAISS Vector Index (semantic search)                                         │
│ • Sentence-Window Store (context windows)                                      │
│ • Graph Index (events, dates, prices → relations)                              │
│                                                                                 │
│ Files generated:                                                                │
│   • `data/indices/faiss/`                                                      │
│   • `data/indices/sentwin.jsonl`                                               │
│   • `data/indices/graph.gpickle`                                               │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Multi-index retrieval
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                        5. Multi-Retriever System                               │
│──────────────────────────────────────────────────────────────────────────────│
│ ① Vector Retriever (semantic FAISS search)                                      │
│ ② Sentence-Window Retriever (nearby text slices)                               │
│ ③ Graph Retriever (exact matches: dates, events, prices)                       │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Retrieved contexts (top-k)
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                               6. Re-Ranking Layer                              │
│──────────────────────────────────────────────────────────────────────────────│
│ • Scores merged using weighted fusion:                                          │
│   score = 0.55 * vector + 0.30 * window + 0.15 * graph                         │
│ • Removes duplicates                                                             │
│ • Produces final ranked list of context snippets                                │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Ranked snippets
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                           7. Answer Construction                               │
│──────────────────────────────────────────────────────────────────────────────│
│ • Extracts short sentences from top documents                                   │
│ • Generates concise bullet-point answers                                         │
│ • Attaches numeric citations to each bullet                                      │
└──────────────────────────────────────────────────────────────────────────────┘

            │ Bullets + citations
            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                               8. Final Response                                │
│──────────────────────────────────────────────────────────────────────────────│
│ • Answer shown in Streamlit                                                     │
│ • Clickable source links displayed                                               │
│ • Optional “Supporting Snippets” section                                         │
└──────────────────────────────────────────────────────────────────────────────┘




## 🧠 Project Explanation (Simple & Easy to Understand)

The **City Sanitation RAG Assistant** is a smart search system that helps users find
clear answers about trash, recycling, bulky pickup, medicine disposal, prices, and
holiday schedules in the City of Dallas.

It works by collecting information from different sources (web pages, PDFs,
Excel sheets), organizing it, and then searching through it quickly when a user
asks a question.

The system does not use generative AI to make up answers.  
Instead, it extracts real information from your documents — so answers are always
accurate and based on true sources.

---

## How the System Works (In Simple Steps)

### 1. Data Collection
The system gathers information from:
- City sanitation web pages  
- PDF calendars (bulky pickup, holidays)
- Excel sheets (prices, fees)
- Any other structured or unstructured files

Everything is cleaned and stored in one large file (`corpus.jsonl`).

---

### 2. Data Processing  
Before searching, the documents are:
- Cleaned (HTML removed, text normalized)
- Split into smaller readable chunks
- Tagged with metadata (source link, title, type of file)

This makes the search results accurate and easy to trace.

---

### 3. Indexing  
To enable fast and smart search, the system builds:
- **FAISS Vector Index:** finds similar sentences based on meaning  
- **Sentence-Window Index:** finds nearby context around a sentence  
- **Graph Index:** stores exact facts like prices, dates, and events  

These indices work together like a mini search engine.

---

### 4. Multi-Retriever Search  
When the user asks a question, the system uses three methods:

1. **Semantic Search:** finds text similar in meaning  
2. **Window Search:** retrieves surrounding text for more context  
3. **Graph Search:** directly looks up exact facts  

All results are combined and ranked.

---

### 5. Answer Creation  
The app generates:
- Short, clear bullet-point answers  
- Small, readable text snippets  
- Numbered citations to show where each answer came from

Users can also expand a section to see the supporting text.

---

### 6. Final Output
The answer appears instantly in Streamlit with:
- Concise bullets  
- Clickable source links  
- Full transparency about where info came from  

No hallucinations — everything is extracted from your own data.

---

## Why This Project Is Useful
This project shows:
- How to build a real RAG system from scratch  
- How to process web/PDF/Excel data in one pipeline  
- How to build vector search + graph search  
- How to design a clean, user-friendly search interface  
- How to produce trustworthy, cited answers  

It is production-style, easy to extend, and ideal for city services, internal
knowledge bases, and customer-support search systems.
