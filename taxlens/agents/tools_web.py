"""
Oracle Agent Core: Stealth Web Search Tool (Zero-Disk Footprint RAG)
Fetches official tax information directly from government websites with Anti-Bot bypass.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func): return func

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=6))
def _stealth_request(url: str) -> requests.Response:
    try:
        from fake_useragent import UserAgent
        ua = UserAgent()
        headers = {
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive'
        }
    except ImportError:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status() # 403 or 500 will trigger @retry
    return resp

@tool
def tool_live_vietnam_tax_search(query: str) -> Dict[str, Any]:
    """
    Oracle Agent Task: Tra cứu trực tiếp luật thuế Việt Nam trên web.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return {"status": "Error", "url": "", "content": "", "error": "Missing ddgs library."}
        
    dork_query = f"{query} luật thuế Việt Nam site:gov.vn OR site:chinhphu.vn OR site:thuvienphapluat.vn"
    
    try:
        results = []
        with DDGS() as ddgs:
            ddg_gen = ddgs.text(dork_query, max_results=3)
            results = list(ddg_gen)
            
        if not results:
            return {"status": "Không tìm thấy kết quả.", "url": "", "content": "", "error": "Empty search"}
            
        top_url = results[0].get('href', '')
        top_snippet = f"Summary: {results[0].get('body', '')}"
        
        content = ""
        try:
            resp = _stealth_request(top_url)
            soup = BeautifulSoup(resp.content, "html.parser")
            for data in soup(["script", "style", "nav", "footer", "header", "aside"]):
                data.decompose()
            text = soup.get_text(separator=' ', strip=True)
            content = text[:5000]
        except Exception:
            # Bypass Cloudflare failed, fallback to Snippet RAG
            pass 

        if len(content) < 50:
            content = top_snippet
            
        return {"status": "Thành công", "url": top_url, "content": content, "error": ""}
        
    except Exception as e:
        return {"status": "Error", "url": "", "content": "", "error": f"Lỗi: {str(e)}"}
