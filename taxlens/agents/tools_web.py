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
        return {"error": "Missing duckduckgo_search library. Install via pip."}
        
    dork_query = f"{query} site:gdt.gov.vn OR site:chinhphu.vn OR site:thuvienphapluat.vn"
    
    try:
        # 1. Search with DDG
        results = []
        with DDGS() as ddgs:
            # Get top 2 results to avoid rate limit
            ddg_gen = ddgs.text(dork_query, max_results=2)
            results = list(ddg_gen)
            
        if not results:
            return {"status": "Không tìm thấy kết quả từ nguồn chính thống.", "data": ""}
            
        # 2. Scrape the top URL safely (Zero-Disk Footprint)
        top_url = results[0].get('href')
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(top_url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            return {"status": "Trang web chặn truy cập.", "url": top_url, "snippet": results[0].get('body')}
            
        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Strip scripts and styles
        for data in soup(["script", "style", "nav", "footer", "header"]):
            data.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        
        # CHOP context to 4000 characters to prevent LLM memory overflow
        safe_text = text[:4000]
        
        return {
            "status": "Tra cứu Web thành công",
            "url": top_url,
            "content": safe_text,
            "note": "Trả về tối đa 4000 ký tự để trống RAM."
        }
        
    except Exception as e:
        # Catch RateLimit or other DDG failures gracefully
        return {"error": f"Lỗi tra cứu web (Thường do RateLimit): {str(e)}"}
