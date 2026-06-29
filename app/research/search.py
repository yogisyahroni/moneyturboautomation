"""
Research Engine — Mencari referensi dari internet
Menggunakan DuckDuckGo (gratis, no API key)
"""
import json
import re
from typing import List, Dict, Optional
from loguru import logger

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None
    logger.warning("duckduckgo_search not installed. Install with: pip install duckduckgo-search")


def search_web(query: str, max_results: int = 5, language: str = "id") -> List[Dict]:
    """
    Cari artikel/berita dari internet pake DuckDuckGo
    
    Args:
        query: Kata kunci pencarian
        max_results: Max hasil yang dikembalikan
        language: Bahasa (id = Indonesia, en = English)
        
    Returns:
        List of {title, url, snippet, body}
    """
    if DDGS is None:
        logger.error("duckduckgo_search tidak tersedia")
        return []
    
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="id-ID" if language == "id" else "wt-wt", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        logger.success(f"Research: found {len(results)} results for '{query}'")
    except Exception as e:
        logger.error(f"Research search failed: {e}")
    
    return results


def search_news(query: str, max_results: int = 5, language: str = "id") -> List[Dict]:
    """
    Cari berita terbaru dari DuckDuckGo News
    """
    if DDGS is None:
        return []
    
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": r.get("source", ""),
                })
        logger.success(f"Research News: found {len(results)} results for '{query}'")
    except Exception as e:
        logger.error(f"Research news failed: {e}")
    
    return results


def fetch_page_content(url: str) -> Optional[str]:
    """
    Ambil teks dari halaman web (sederhana, pake requests)
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Hapus tag script, style, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n", "\n", text)
        # Ambil 3000 karakter pertama aja
        return text[:3000]
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def research_topic(query: str, max_sources: int = 5, language: str = "id") -> Dict:
    """
    Research lengkap: search web + ambil konten + balikin hasil
    
    Returns:
        {
            "topic": query,
            "sources": [...],
            "summaries": [...],
            "combined_text": "..."
        }
    """
    logger.info(f"🔍 Researching: '{query}'")
    
    # 1. Search web + news
    web_results = search_web(query, max_results=max_sources, language=language)
    news_results = search_news(query, max_results=max_sources, language=language)
    
    all_sources = web_results + news_results
    
    if not all_sources:
        return {
            "topic": query,
            "sources": [],
            "summaries": [],
            "combined_text": "",
            "error": "No sources found"
        }
    
    # 2. Ambil konten dari beberapa sumber
    summaries = []
    combined_text = ""
    for src in all_sources[:3]:  # Ambil 3 sumber teratas
        content = fetch_page_content(src.get("url", ""))
        if content:
            summaries.append({
                "title": src.get("title", ""),
                "url": src.get("url", ""),
                "content": content
            })
            combined_text += f"\n\n=== {src['title']} ===\n{content}"
    
    return {
        "topic": query,
        "sources": all_sources,
        "summaries": summaries,
        "combined_text": combined_text.strip()
    }


if __name__ == "__main__":
    # Test
    import json
    result = research_topic("kenapa rupiah melemah 2026", max_sources=3)
    print(json.dumps(result, indent=2)[:500])
