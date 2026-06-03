from __future__ import annotations
import asyncio
import os
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document

_BASE = "https://www.newadvent.org/cathen/"
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_DELAY = 1.0
_SAINT_KEYWORDS = re.compile(r"\bsaint\b|\bst\.\s|\bblessed\b|\bvenerable\b", re.IGNORECASE)
_MAX_WORDS = 400
_MIN_ARTICLE_LENGTH = 100


def filter_saint_links(html: str, base: str) -> list[tuple[str, str]]:
    """
    From a CE letter index page, return (url, title) pairs for saint articles.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if not title or not href.endswith(".htm"):
            continue
        if not _SAINT_KEYWORDS.search(title):
            continue
        # Build absolute URL
        if href.startswith("http"):
            url = href
        else:
            url = base + href
        results.append((url, title))
    return results


def parse_saint_article(html: str) -> str:
    """Extract main article text from a New Advent CE article page."""
    soup = BeautifulSoup(html, "lxml")
    # Try the main content div first
    content_div = soup.find("div", id="bodycontents") or soup.find("div", class_="bodycontents")
    if content_div:
        target = content_div
    else:
        target = soup.find("body") or soup

    paragraphs = [p.get_text(separator=" ", strip=True) for p in target.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p) > 20)
    return text


def chunk_text(text: str, max_words: int = _MAX_WORDS) -> list[str]:
    """Split text into chunks of at most max_words, splitting on word boundaries."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i : i + max_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


async def main(pool) -> None:
    print("Collecting saint article URLs from New Advent CE...")
    all_links: list[tuple[str, str]] = []
    skipped_pages: list[str] = []
    skipped_articles: list[str] = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        # Step 1: collect all saint URLs from A-Z index pages
        for letter in _LETTERS:
            time.sleep(_DELAY)
            url = f"{_BASE}{letter}.htm"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                links = filter_saint_links(resp.text, _BASE)
                all_links.extend(links)
            except Exception as exc:
                print(f"\n  WARNING: Failed index page {url}: {exc}", file=sys.stderr)
                skipped_pages.append(url)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_links: list[tuple[str, str]] = []
        for url, title in all_links:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_links.append((url, title))

        print(f"  Found {len(unique_links)} saint article URLs.")

        # Step 2: scrape each article
        with tqdm(total=len(unique_links), unit="saint", desc="Saints") as pbar:
            for art_url, title in unique_links:
                time.sleep(_DELAY)
                try:
                    resp = client.get(art_url)
                    resp.raise_for_status()
                except Exception as exc:
                    print(f"\n  WARNING: Failed {title}: {exc}", file=sys.stderr)
                    skipped_articles.append(title)
                    pbar.update(1)
                    continue

                article_text = parse_saint_article(resp.text)
                if len(article_text) < _MIN_ARTICLE_LENGTH:
                    skipped_articles.append(title)
                    pbar.update(1)
                    continue

                text_chunks = chunk_text(article_text)
                if not text_chunks:
                    pbar.update(1)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="saints",
                    title=title,
                    translation="",
                    author="Catholic Encyclopedia",
                    year=1913,
                    metadata={"url": art_url},
                )

                for position, content in enumerate(text_chunks):
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=f"{title} — Catholic Encyclopedia",
                    )

                pbar.set_postfix({"saint": title[:30]})
                pbar.update(1)

    total_skipped = len(skipped_pages) + len(skipped_articles)
    if total_skipped:
        print(f"\n  WARNING: {total_skipped} items skipped.", file=sys.stderr)
    print(f"  Done. {len(unique_links) - len(skipped_articles)} saints written.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
