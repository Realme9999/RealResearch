"""Fetch webpage content as clean text.

Priority: Tavily Extract API → requests + BeautifulSoup fallback.

Usage:
    rr-fetch --url "https://example.com/article"
    rr-fetch --url "https://example.com" --max-length 20000
"""

import argparse
import json
import os
import re
import sys

from .utils import setup_utf8


def _build_session():
    """Build a requests session with retry logic."""
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ImportError:
        return None

    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _fetch_tavily(url: str, extract_depth: str = "basic") -> dict | None:
    """Fetch via Tavily Extract API."""
    api_key = os.environ.get("RR_SEARCH_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
    except ImportError:
        return None

    try:
        client = TavilyClient(api_key=api_key)
        response = client.extract(urls=url, extract_depth=extract_depth, format="text", timeout=30)
        if response.get("results"):
            result = response["results"][0]
            content = result.get("raw_content", "")
            return {
                "url": url, "status": 200,
                "content_type": "text/plain; charset=utf-8",
                "length": len(content), "truncated": False,
                "content": content, "title": result.get("title", ""),
                "source": "tavily",
            }
    except Exception:
        pass
    return None


def _fetch_requests(url: str, max_length: int = 15000) -> dict:
    """Fallback: fetch via requests + BeautifulSoup."""
    try:
        import requests
    except ImportError:
        return {"error": "requests is not installed. Run: pip install requests"}

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        session = _build_session()
        if session:
            resp = session.get(url, headers=headers, timeout=30)
        else:
            resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return {"error": f"Failed to fetch URL: {e}", "url": url}

    content_type = resp.headers.get("Content-Type", "")
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        if resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding

    text = ""
    try:
        if "text/html" in content_type:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                    tag.decompose()
                for selector in ["article", "main", "[role='main']", ".content", "#content"]:
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(separator="\n")
                        break
                else:
                    body = soup.find("body")
                    text = (body.get_text(separator="\n") if body else soup.get_text(separator="\n"))
            except ImportError:
                text = resp.text
        else:
            text = resp.text
    except Exception as e:
        return {"error": f"Content parsing failed: {e}", "url": url}

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    truncated = len(text) > max_length
    if truncated:
        text = text[:max_length] + "\n... [content truncated]"

    return {
        "url": url, "status": resp.status_code,
        "content_type": content_type,
        "length": len(text), "truncated": truncated,
        "content": text, "source": "requests",
    }


def fetch(url: str, max_length: int = 15000, extract_depth: str = "basic") -> dict:
    """Fetch webpage content (Tavily first, requests fallback)."""
    result = _fetch_tavily(url, extract_depth=extract_depth)
    if result is not None:
        content = result["content"]
        truncated = len(content) > max_length
        if truncated:
            content = content[:max_length] + "\n... [content truncated]"
            result["content"] = content
            result["length"] = len(content)
            result["truncated"] = True
        return result
    return _fetch_requests(url, max_length=max_length)


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(description="RealResearch: fetch webpage content")
    parser.add_argument("--url", "-u", required=True, help="Target URL")
    parser.add_argument("--max-length", "-m", type=int, default=15000, help="Max content length (default: 15000)")
    parser.add_argument("--extract-depth", "-d", default="basic", choices=["basic", "advanced"])
    args = parser.parse_args()

    from .logger import get_logger
    logger = get_logger()
    if logger:
        logger.start_step("rr-fetch", {"url": args.url, "max_length": args.max_length, "extract_depth": args.extract_depth})

    result = fetch(args.url, args.max_length, args.extract_depth)

    if logger:
        summary = None
        if "error" not in result:
            summary = {
                "url": result.get("url", ""),
                "length": result.get("length", 0),
                "truncated": result.get("truncated", False),
                "source": result.get("source", ""),
            }
        logger.end_step(result_summary=summary, error=result.get("error"))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)
