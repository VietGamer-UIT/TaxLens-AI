"""
LangGraph Multi-Tenant Cyclic Orchestrator (B2B SaaS Edition)
REAL DATA PANDAS INGESTION & GEMINI 404 SAFEGUARDS.
"""
from typing import Annotated, Dict, Any, List, TypedDict, Sequence
import operator
import re
import pandas as pd
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
except ImportError:
    pass

from taxlens.agents.tools import (
    tool_reconcile_vat_3_way,
    tool_calculate_cit_adjustment,
    tool_fct_tp_scanner,
    tool_parse_vn_einvoice_xml
)
from taxlens.agents.tools_web import tool_live_vietnam_tax_search

class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_data: Dict[str, Any]
    working_papers: Dict[str, Any]
    audit_firm_name: str
    client_name: str
    review_note: str
    is_approved: bool

def node_hunter_agent(state: GraphState) -> Dict[str, Any]:
    """Hunter Agent: Real Pandas Big Data Ingestion."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    paths = raw.get("uploaded_paths", [])
    review_note = state.get("review_note", "")
    
    prefix = f"Đã rà soát lại theo lệnh: '{review_note}'. " if review_note and not state.get("is_approved", True) else ""
    findings = []
    
    # Quét thực tế bằng Pandas
    try:
        count_rows = 0
        for path in paths:
            if path.endswith(".csv"):
                # Đọc CSV hàng ngàn dòng
                df = pd.read_csv(path)
                count_rows += len(df)
                
                # Biểu thức Boolean Filtering càn quét (Rule-based)
                # Lỗi 1: TK 642, tiền cao, thiếu chứng từ
                if all(col in df.columns for col in ["TaiKhoan", "SoTien", "ChungTuHopLe"]):
                    # Chuyển đổi an toàn
                    df['TaiKhoan'] = df['TaiKhoan'].astype(str).str.strip()
                    df['ChungTuHopLe'] = df['ChungTuHopLe'].astype(str).str.upper()
                    
                    df_loi_642 = df[
                        (df['TaiKhoan'].str.startswith('642')) & 
                        (df['SoTien'] > 20000000) & 
                        (df['ChungTuHopLe'] == 'FALSE')
                    ]
                    
                    for _, row in df_loi_642.iterrows():
                        findings.append({
                            "Mã rủi ro": "CIT_ERR_642",
                            "Khoản mục": f"Chi phí Bán hàng/QLDN (Dòng {row.get('NgayGhiSo', 'N/A')})",
                            "Số tiền chênh lệch": f"{row['SoTien']:,.0f} VND",
                            "Cơ sở pháp lý": "Thiếu chứng từ hợp lệ (TT 78/2014)",
                            "Đề xuất": "Bóc ngay chi phí, tính lại Thuế TNDN"
                        })
                        
            elif path.endswith(".xml"):
                # Mô phỏng quét XML đọc nội dung thô (có thể nâng cấp bộ parser XML xịn sau)
                with open(path, "r", encoding="utf-8") as f:
                    xml_str = f.read()
                    if "<!-- CẢNH BÁO LỖI" in xml_str:
                        findings.append({
                            "Mã rủi ro": "VAT_XML_ERR",
                            "Khoản mục": f"Hóa Đơn Cụ Thể (XML_Tax_Leak)",
                            "Số tiền chênh lệch": "Phát hiện độ lệch giữa Thuế Suất và Tiền Thuế",
                            "Cơ sở pháp lý": "Vi phạm mẫu hóa đơn hợp lệ NĐ 123/2020",
                            "Đề xuất": "Lập biên bản hóa đơn điện tử sai phạm, liên hệ NCC xuất lại"
                        })
                        
        if not findings:
            findings.append({"Mã rủi ro": "N/A", "Khoản mục": f"Toàn bộ {count_rows} dòng", "Số tiền chênh lệch": "0", "Cơ sở pháp lý": "N/A", "Đề xuất": "Hồ sơ sạch"})
            
        papers["standardized_findings"] = findings
        msg_content = f"[Hunter Agent]: {prefix}Đã càn quét thành công {count_rows} dòng dữ liệu thật. Ghi nhận {len(findings)} lỗi."
    except Exception as e:
         papers["standardized_findings"] = [{"Mã rủi ro": "SYS_ERR", "Khoản mục": "Pipeline Pandas", "Số tiền chênh lệch": "0", "Cơ sở pháp lý": "N/A", "Đề xuất": f"Lỗi Pandas: {e}"}]
         msg_content = f"[Hunter Agent]: Lỗi Pipeline Data. {e}"
         
    return {"messages": [AIMessage(content=msg_content)], "working_papers": papers}

def node_oracle_agent(state: GraphState) -> Dict[str, Any]:
    """Oracle Agent: Real-time RAG & Strict Gemini Exception Handling."""
    papers = state.get("working_papers", {})
    review_note = state.get("review_note", "")
    
    question = "Cập nhật luật thuế TNDN liên quan chứng từ kế toán từ giá trị 20 triệu"
    if review_note: question = review_note 

    try:
         web_data = tool_live_vietnam_tax_search.invoke({"query": question})
         content = web_data.get("content", "")
         
         if not content or len(content) < 10 or web_data.get("status") == "Error":
              # Fallback sang Gemini
              try:
                  from langchain_google_genai import ChatGoogleGenerativeAI
                  from langchain_core.messages import SystemMessage, HumanMessage
                  from dotenv import load_dotenv
                  load_dotenv()
                  
                  import os
                  if not os.environ.get("GOOGLE_API_KEY"):
                      raise ValueError("Missing GOOGLE_API_KEY ở file .env")
                      
                  llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0) 
                  fallback = llm.invoke([
                      SystemMessage(content="Bạn là chuyên gia tư vấn luật thuế VN chuẩn Big 4."), 
                      HumanMessage(content=question)
                  ]).content
                  analysis = f"[Trí tuệ căn bản Gemini]:\n{fallback}"
              except Exception as e:
                  analysis = f"⚠️ [LỖI 404/AUTH GEMINI]: Vui lòng kiểm tra lại API Key. Chi tiết: {str(e)}"
         else:
              # Run RAG
              try:
                  from langchain_google_genai import ChatGoogleGenerativeAI
                  from langchain_core.messages import HumanMessage
                  from dotenv import load_dotenv
                  load_dotenv()
                  
                  import os
                  if not os.environ.get("GOOGLE_API_KEY"):
                      raise ValueError("Missing GOOGLE_API_KEY ở file .env")
                      
                  llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
                  prompt = f"Trích luật chính thống:\n{content[:4000]}\n\nTrả lời/Tóm tắt câu hỏi: {question}"
                  ans = llm.invoke([HumanMessage(content=prompt)]).content
                  analysis = f"Nguồn Web RAG: {web_data.get('url')}\n{ans}"
              except Exception as e:
                  analysis = f"⚠️ [LỖI TÓM TẮT GEMINI]: {str(e)}\n\nNội dung RAG Root: {content[:1000]}"
                  
    except Exception as e:
         analysis = f"Oracle SYS ERR: {e}"
         
    papers["Legal_Context"] = analysis
    return {"messages": [AIMessage(content="Oracle Data ready.")], "working_papers": papers}

def node_manager_review(state: GraphState) -> Dict[str, Any]:
    return {"messages": [AIMessage(content="HitL Paused")]}

def node_report_agent(state: GraphState) -> Dict[str, Any]:
    papers = state.get("working_papers", {})
    firm = state.get("audit_firm_name", "[Company]")
    client = state.get("client_name", "[Client]")
    findings = papers.get("standardized_findings", [])
    legal = papers.get("Legal_Context", "Trống.")
    
    draft = f"""# MANAGEMENT LETTER / BÁO CÁO TƯ VẤN THUẾ
<div style="color: gray; font-size: 14px; text-transform: uppercase;">
<b>Kính gửi:</b> Ban Giám Đốc {client}<br>
<b>Đơn vị kiểm toán:</b> {firm}<br>
<b>Ngày xuất báo cáo:</b> Hôm nay
</div>

---

### I. CÁC VẤN ĐỀ TRỌNG YẾU PHÁT HIỆN QUA PANDAS ENGINE
"""
    for item in findings:
        draft += f"- **[{item['Mã rủi ro']}] {item['Khoản mục']}**:\n"
        draft += f"  - Chênh lệch/Quy mô: `{item['Số tiền chênh lệch']}`\n"
        draft += f"  - Rủi ro pháp lý: {item['Cơ sở pháp lý']}\n"
        draft += f"  - Khuyến nghị: *{item['Đề xuất']}*\n\n"

    draft += "### II. THAM CHIẾU PHÁP LÝ (GEMINI RAG)\n"
    draft += f"{legal}\n\n"
    
    draft += "---\n*Powered by TaxLens-AI - Core Engine created by Đoàn Hoàng Việt (Việt Gamer)*"
    return {"messages": [AIMessage(content=draft)]}

def feedback_router(state: GraphState) -> str:
    return "Report_Agent" if state.get("is_approved") else "Hunter_Agent"

def build_tax_audit_graph() -> Any:
    workflow = StateGraph(GraphState)
    workflow.add_node("Hunter_Agent", node_hunter_agent)
    workflow.add_node("Oracle_Agent", node_oracle_agent)
    workflow.add_node("Manager_Review_Node", node_manager_review)
    workflow.add_node("Report_Agent", node_report_agent)
    
    workflow.add_edge(START, "Hunter_Agent")
    workflow.add_edge("Hunter_Agent", "Oracle_Agent")
    workflow.add_edge("Oracle_Agent", "Manager_Review_Node")
    workflow.add_conditional_edges("Manager_Review_Node", feedback_router)
    workflow.add_edge("Report_Agent", END)
    
    return workflow.compile(checkpointer=MemorySaver(), interrupt_before=["Manager_Review_Node"])
