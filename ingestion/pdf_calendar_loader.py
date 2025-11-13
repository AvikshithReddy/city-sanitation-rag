from pathlib import Path
import pdfplumber, json, hashlib, datetime as dt, re, dateparser, pandas as pd

PDF_DIR = Path("data/raw_pdf") if Path("data/raw_pdf").exists() else Path("data")
PDFS = sorted([str(p) for p in PDF_DIR.glob("cal_*.pdf")])

JSONL_OUT = Path("data/unified/calendars.jsonl")
CSV_OUT = Path("data/csv/calendar_events.csv"); CSV_OUT.parent.mkdir(parents=True, exist_ok=True)

def uid(s): return hashlib.md5(s.encode()).hexdigest()

def extract_events(pdf_path):
    rows=[]
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            for line in txt.splitlines():
                low=line.lower()
                if any(k in low for k in ["pickup","recycling","trash","holiday","bulky","brush"]):
                    m = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", line)
                    date = dateparser.parse(m.group(1)).date().isoformat() if m else None
                    rows.append({"event": line.strip(), "date": date, "page": i, "source_pdf": pdf_path})
    return rows

def run():
    events=[]
    with open(JSONL_OUT, "w", encoding="utf-8") as w:
        for p in PDFS:
            for it in extract_events(p):
                rec = {
                    "id": uid(p + str(it)),
                    "text": it["event"],
                    "meta": {"source":"pdf","source_id":p,"page":it["page"],"effective_date":it["date"]},
                    "ingested_at": dt.datetime.utcnow().isoformat()
                }
                w.write(json.dumps(rec, ensure_ascii=False)+"\n")
                events.append(it)
    pd.DataFrame(events).to_csv(CSV_OUT, index=False)

if __name__ == "__main__":
    run()


    