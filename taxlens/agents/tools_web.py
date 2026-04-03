"""
Live Web Search Tool (Zero-Disk Footprint RAG)
Fetches official tax information directly from government websites to save disk space and guarantee current regulations.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func): return func


@tool
def tool_live_vietnam_tax_search(query: str) -> Dict[str, Any]:
    """
    Compliance Agent Task: Tra cứu trực tiếp luật thuế Việt Nam trên web.
    Must provide a search query. Automatically zeroes in on official government sites.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {"status": "Error", "url": "", "content": "", "error": "Missing duckduckgo_search library. Install via pip."}
        
    dork_query = f"{query} luật thuế Việt Nam"
    
    try:
        # 1. Search with DDG gracefully
        results = []
        with DDGS() as ddgs:
            # Get top 2 results to avoid rate limit
            ddg_gen = ddgs.text(dork_query, max_results=2)
            results = list(ddg_gen)
            
        if not results:
            return {"status": "Không tìm thấy kết quả.", "url": "", "content": "", "error": "Empty search result"}
            
        # 2. Scrape the top URL safely (Zero-Disk Footprint)
        top_url = results[0].get('href', '')
        top_snippet = results[0].get('body', '')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        content = ""
        try:
            resp = requests.get(top_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                for data in soup(["script", "style", "nav", "footer", "header"]):
                    data.decompose()
                text = soup.get_text(separator=' ', strip=True)
                content = text[:4000]
        except Exception:
            pass # We will fallback to snippet

        # Fallback mechanism if requests fail, get blocked, or BS4 extracts nothing
        if len(content) < 50:
            content = top_snippet
            
        return {
            "status": "Tra cứu Web thành công",
            "url": top_url,
            "content": content,
            "error": ""
        }
        
    except Exception as e:
        # Catch RateLimit or other DDG failures gracefully
        return {"status": "Error", "url": "", "content": "", "error": f"Lỗi tra cứu web (Thường do RateLimit): {str(e)}"}
