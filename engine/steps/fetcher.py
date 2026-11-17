"""Gets text out of a URL (HTML or PDF) or a local file. Plain code, no LLM.
PDFs come back with [[page N]] markers so we can cite page numbers as evidence.
"""
import hashlib
import io
import json
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from engine.shared import config

FETCH_CACHE = config.CACHE_DIR / "fetch"
FETCH_CACHE.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (research prototype; contact: me@example.com)"}


class BlockedSource(Exception):
    pass


def _check_allowed(url):
    host = urlparse(url).netloc.lower()
    for bad in config.BLOCKED_DOMAINS:
        if host == bad or host.endswith("." + bad):
            raise BlockedSource(f"{host} is on the blocked list (terms forbid scraping)")
    # robots.txt check. We download it ourselves with our own User-Agent: RobotFileParser.read()
    # uses Python's default agent, gets a 403 from many sites, and then treats EVERYTHING as
    # disallowed. If robots.txt can't be read at all we carry on.
    try:
        r = requests.get(f"{urlparse(url).scheme}://{host}/robots.txt", headers=HEADERS, timeout=(5, 10))
    except requests.RequestException:
        return
    if r.status_code != 200:
        return
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    if not rp.can_fetch(HEADERS["User-Agent"], url):
        raise BlockedSource(f"robots.txt disallows {url}")


def _pdf_to_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        parts.append(f"[[page {i}]]\n{page.extract_text() or ''}")
    return "\n".join(parts)


def _html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def linked_pdfs(html, base_url):
    """SEBI filing pages are thin wrappers around their documents: an <iframe> showing one PDF
    (IPO filings) or plain links to several PDFs (takeovers, buybacks)."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for tag in soup.find_all(["iframe", "embed", "object", "a"]):
        src = tag.get("src") or tag.get("data") or tag.get("href") or ""
        target = parse_qs(urlparse(src).query).get("file", [src])[0]
        if target.lower().endswith(".pdf"):
            url = urljoin(base_url, target)
            if url not in found:
                found.append(url)
    return found


def expand(url):
    """A thin page that only points at PDFs -> those PDF urls. Anything else -> [url]."""
    if not url.startswith("http") or url.lower().endswith(".pdf"):
        return [url]
    cache_file = FETCH_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".links.json")
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    _check_allowed(url)
    r = _download(url)
    r.raise_for_status()
    if "pdf" in r.headers.get("content-type", ""):
        result = [url]
    else:
        pdfs = linked_pdfs(r.content, url)
        # a real article that happens to link a PDF is still an article
        thin = len(_html_to_text(r.content)) < 3000
        result = pdfs[:config.MAX_LINKED_DOCS] if (pdfs and thin) else [url]
    cache_file.write_text(json.dumps(result), encoding="utf-8")
    return result


def _download(url, tries=3):
    """Big PDFs from SEBI/exchange servers often drop mid-download, so retry a few times.
    A server that never answers (NSE does this to scripts) fails fast instead of hanging."""
    for attempt in range(1, tries + 1):
        try:
            # (connect, read) seconds; read = max silence between bytes, not total time
            return requests.get(url, headers=HEADERS, timeout=(10, 30))
        except requests.Timeout:
            raise BlockedSource(f"{urlparse(url).netloc} is not answering scripts. Open the link in a "
                                f"browser, save the file, and use {{\"url\": ..., \"file\": ...}}.")
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError):
            if attempt == tries:
                raise
            time.sleep(3 * attempt)


def get_text(source):
    """source can be a URL or a path to a file on disk (.pdf, .html or plain text)."""
    cache_file = FETCH_CACHE / (hashlib.sha1(source.encode()).hexdigest() + ".txt")
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    if source.startswith("http"):
        _check_allowed(source)
        time.sleep(1)                       # be polite
        r = _download(source)
        if r.status_code in (401, 403):
            raise BlockedSource(f"{urlparse(source).netloc} refused the download ({r.status_code}). "
                                f"Open it in a browser, save the file, and pass the file path instead.")
        r.raise_for_status()
        is_pdf = source.lower().endswith(".pdf") or "pdf" in r.headers.get("content-type", "")
        # raw bytes, so BeautifulSoup reads the page's own charset (r.text guesses wrong: â€“)
        text = _pdf_to_text(r.content) if is_pdf else _html_to_text(r.content)
    else:
        p = Path(source)
        if not p.is_absolute() and not p.exists():
            p = config.ROOT / p                 # event files use paths relative to the project
        if not p.exists():
            raise FileNotFoundError(f"saved copy not found: {p}. Save the page there first.")
        if p.suffix.lower() == ".pdf":
            text = _pdf_to_text(p.read_bytes())
        elif p.suffix.lower() in (".html", ".htm"):
            text = _html_to_text(p.read_text(encoding="utf-8", errors="replace"))
        else:
            text = p.read_text(encoding="utf-8", errors="replace")

    cache_file.write_text(text, encoding="utf-8")
    return text
