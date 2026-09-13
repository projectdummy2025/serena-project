import os
import re
import logging
from typing import List, Dict, Any
import httpx
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from app.memory.vault_writer import create_note
from app import config

logger = logging.getLogger(__name__)

def search_web_ddg(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Perform free web search using DuckDuckGo Search API.
    """
    results = []
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            for item in raw_results:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", "")
                })
        logger.info(f"Pencarian DuckDuckGo untuk '{query}' menghasilkan {len(results)} entri.")
    except Exception as err:
        logger.warning(f"Kendala pada pencarian DuckDuckGo Search: {err}")
    return results

async def fetch_web_markdown(url: str) -> str:
    """
    Fetch clean markdown content from URL using Jina AI Reader API (r.jina.ai).
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(jina_url)
            if response.status_code == 200:
                return response.text[:3000]
    except Exception as err:
        logger.debug(f"Gagal mengambil konten Jina AI Reader untuk {url}: {err}")
    return ""

async def conduct_research_task(query: str) -> str:
    """
    Conduct comprehensive web research:
    1. Search web via DuckDuckGo.
    2. Read top result snippets & content.
    3. Synthesize research findings.
    4. Save research note to Obsidian Vault (Kotak Masuk/Riset-<topic>.md).
    5. Return research report.
    """
    search_results = search_web_ddg(query, max_results=5)
    
    if not search_results:
        return f"Mohon maaf, tidak ditemukan informasi web yang relevan untuk kueri riset: '{query}'."

    report_lines = [
        f"Laporan Riset Web: {query}\n",
        "----------------------------------------\n"
    ]
    
    for i, res in enumerate(search_results, 1):
        report_lines.append(f"[{i}] {res['title']}\nURL: {res['url']}\nRingkasan: {res['snippet']}\n")
        
    compiled_findings = "\n".join(report_lines)
    
    safe_topic = re.sub(r'[^a-zA-Z0-9_-]', '_', query[:30]).strip('_')
    filename = f"Riset_{safe_topic}.md"
    
    try:
        create_note(
            folder="Kotak Masuk",
            filename=filename,
            content=compiled_findings,
            tags=["riset", "web-search", "second-brain"]
        )
    except Exception as e:
        logger.warning(f"Gagal menyimpan catatan riset ke Obsidian: {e}")

    return compiled_findings
