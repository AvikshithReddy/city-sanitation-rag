# indexing/build_graph.py
import networkx as nx, pandas as pd
from pathlib import Path

GOUT = Path("data/indices/graph.gpickle"); GOUT.parent.mkdir(parents=True, exist_ok=True)

def main():
    g = nx.DiGraph()

    # Calendar events
    cal_csv = Path("data/csv/calendar_events.csv")
    if cal_csv.exists():
        cal = pd.read_csv(cal_csv)
        for _, r in cal.iterrows():
            evt  = f"event:{str(r.get('event','')).lower()}"
            date = f"date:{str(r.get('date','unknown'))}"
            g.add_edge(evt, date, rel="occurs_on")

    # Prices
    pr_csv = Path("data/csv/prices_tidy.csv")
    if pr_csv.exists():
        pr = pd.read_csv(pr_csv)
        for _, r in pr.iterrows():
            prod  = f"product:{str(r.get('product','')).lower()}"
            price = f"price:{str(r.get('price',''))}"
            g.add_edge(prod, price, rel="has_price")

    nx.write_gpickle(g, GOUT)
    print(f"✅ Graph saved to {GOUT}")

if __name__ == "__main__":
    main()
    