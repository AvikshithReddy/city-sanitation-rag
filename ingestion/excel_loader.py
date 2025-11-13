from pathlib import Path
import pandas as pd, json, hashlib, datetime as dt

XLSX = Path("data/raw_xlsx/prices.xlsx") if Path("data/raw_xlsx/prices.xlsx").exists() else Path("data/prices.xlsx")
CSV_OUT = Path("data/csv/prices_tidy.csv"); CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
JSONL_OUT = Path("data/unified/prices.jsonl")

def uid(s): return hashlib.md5(s.encode()).hexdigest()

def run():
    df = pd.read_excel(XLSX)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.dropna(how="all")
    df.to_csv(CSV_OUT, index=False)

    with open(JSONL_OUT, "w", encoding="utf-8") as w:
        for row in df.to_dict(orient="records"):
            text = " | ".join([f"{k}:{row[k]}" for k in row if pd.notna(row[k])])
            rec = {
                "id": uid(text),
                "text": text,
                "meta": {"source":"excel","source_id": str(XLSX), "title":"Price list"},
                "ingested_at": dt.datetime.utcnow().isoformat()
            }
            w.write(json.dumps(rec, ensure_ascii=False)+"\n")

if __name__ == "__main__":
    run()