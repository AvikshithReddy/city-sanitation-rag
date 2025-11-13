from pathlib import Path
import hashlib, json, datetime as dt, re, time
import trafilatura, requests
from urllib.parse import urlsplit, urlunsplit
from bs4 import BeautifulSoup

URLS = Path("data/raw_web/urls.txt") if Path("data/raw_web/urls.txt").exists() else Path("data/urls.txt")
OUT = Path("data/unified/web.jsonl"); OUT.parent.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
}

def uid(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", "ignore")).hexdigest()

def canonical_url(u: str) -> str:
    """strip fragments/query; normalize scheme/host casing"""
    p = urlsplit(u)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, "", ""))

def is_probably_html(url: str) -> bool:
    bad_ext = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")
    return not url.lower().endswith(bad_ext)

def fetch_html(url: str, retries: int = 2, sleep: float = 1.0) -> tuple[str, str]:
    """Return (final_url, html) using trafilatura first, then requests with UA."""
    final_url = url
    html = trafilatura.fetch_url(url)
    if not html:
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, headers=UA, timeout=15, allow_redirects=True)
                r.raise_for_status()
                final_url = r.url  # after redirects
                if "text/html" not in r.headers.get("Content-Type", ""):
                    return final_url, ""
                html = r.text
                break
            except Exception:
                if attempt < retries:
                    time.sleep(sleep)
                else:
                    return final_url, ""
    return final_url, html or ""

def extract_text(html: str) -> tuple[str, str | None]:
    """Returns (clean_text, title) using Trafilatura."""
    txt = trafilatura.extract(
        html,
        include_links=False,
        include_comments=False,
        favor_precision=True,
        no_fallback=False,
        with_metadata=True,
    )
    if not txt:
        return "", None
    # Try to pull title from metadata block if present
    m = re.search(r"^title:\s*(.+)$", txt, flags=re.MULTILINE | re.IGNORECASE)
    title = m.group(1).strip() if m else None
    # Remove metadata header (--- lines) if trafilatura added it
    txt = re.sub(r"(?s)^---.*?---\s*", "", txt)
    # light cleanup
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt, title

def bs_fallback(html: str) -> tuple[str, str | None]:
    """Fallback extraction via BeautifulSoup; returns (text, title)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    text = " ".join(soup.get_text(separator=" ").split()).strip()
    return text, title

def run():
    written = 0
    seen: set[str] = set()

    with open(URLS) as f, open(OUT, "w", encoding="utf-8") as w:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            if not is_probably_html(raw):
                print(f"[skip] non-HTML: {raw}")
                continue

            c_url = canonical_url(raw)
            final_url, html = fetch_html(c_url)
            if not html:
                print(f"[warn] empty HTML: {raw}")
                continue
            if final_url in seen:
                print(f"[dupe] {final_url}")
                continue
            seen.add(final_url)

            # primary extraction
            text, title = extract_text(html)

            # fallback to BeautifulSoup if Trafilatura was too short
            if len(text) < 120:
                bs_text, bs_title = bs_fallback(html)
                if len(bs_text) > len(text):
                    text = bs_text
                    if not title and bs_title:
                        title = bs_title

            # still short? warn but keep (you can choose to skip instead)
            if len(text) < 120:
                print(f"[warn] very short extract for {final_url} ({len(text)} chars) even after fallback.")

            rec = {
                "id": uid(final_url + text[:120]),
                "text": text,
                "meta": {
                    "source": "web",
                    "source_id": final_url,
                    "url": final_url,
                    "title": title,
                },
                "ingested_at": dt.datetime.utcnow().isoformat(),
            }
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print(f"✅ wrote {written} records to {OUT}")

if __name__ == "__main__":
    run()
    