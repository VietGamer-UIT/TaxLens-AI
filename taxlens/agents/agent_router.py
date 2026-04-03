"""
LangGraph Multi-Agent Orchestrator.
Defines the Big 4 Tax Audit fieldwork flow, terminating at Manager Review before Reporting.
"""

from typing import Annotated, Dict, Any, List, TypedDict, Sequence
import operator
import re
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
except ImportError:
    BaseMessage = Any
    HumanMessage = Any
    AIMessage = Any

from taxlens.agents.tools import (
    tool_reconcile_vat_3_way,
    tool_calculate_cit_adjustment,
    tool_fct_tp_scanner,
    tool_parse_vn_einvoice_xml
)
from taxlens.agents.tools_web import tool_live_vietnam_tax_search

# 1. State Definition
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_data: Dict[str, Any]      # Passed from UI (e.g. GL rows, VAT totals)
    working_papers: Dict[str, Any] # Accumulated findings
    manager_approval: bool        # Flag from HITL
    next_route: str               # Dynamic routing flag


# 2. Nodes (The Agents)

def node_supervisor(state: GraphState) -> Dict[str, Any]:
    """Supervisor Agent: Phân loại Ý định (Intent) của người dùng để quyết định luồng."""
    messages = state.get("messages", [])
    if not messages:
        return {"next_route": "TB_Mapping_Agent"}
    
    last_msg = messages[-1].content.lower()
    
    # Regex/Keyword logic
    compliance_keywords = ["thuế", "luật", "bao nhiêu", "quy định", "được không", "?"]
    audit_keywords = ["kiểm toán", "đối soát", "sổ cái", "hóa đơn", "kiểm tra"]
    
    if any(k in last_msg for k in compliance_keywords):
        route = "Compliance_Agent"
    elif any(k in last_msg for k in audit_keywords):
        route = "TB_Mapping_Agent"
    else:
        route = "TB_Mapping_Agent" # Default fallback
        
    return {"next_route": route}


def node_tb_mapping(state: GraphState) -> Dict[str, Any]:
    """Junior Auditor: Maps accounts."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    
    # Fake processing for demo purposes
    gl_accounts = raw.get("accounts", ["133", "3331", "642", "811"])
    mapping_result = f"Mapped {len(gl_accounts)} accounts to Tax Categories successfully."
    
    papers["TB_Mapping"] = {"status": "Done", "details": mapping_result}
    
    msg = AIMessage(content="[TB_Mapping_Agent]: Đã hoàn thành sơ đồ tài khoản (Trial Balance Mapping).")
    return {"messages": [msg], "working_papers": papers}


def node_vat_recon(state: GraphState) -> Dict[str, Any]:
    """Tax Senior 1: VAT Reconciliation."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    
    # Extract mock data or defaults
    gl = raw.get("gl_vat_total", 1000000)
    tax_return = raw.get("tax_return_total", 1000000)
    
    einvoice_total = raw.get("einvoice_total", 950000)
    xml_content = raw.get("xml_content")
    xml_parsed = None
    if xml_content:
        xml_parsed = tool_parse_vn_einvoice_xml(xml_content)
        if "vat_amount" in xml_parsed:
            einvoice_total = float(xml_parsed["vat_amount"])
    
    # Use tool
    result = tool_reconcile_vat_3_way(gl, tax_return, einvoice_total)
    
    if xml_parsed and "error" not in xml_parsed:
         result["xml_details"] = f"XML MST: {xml_parsed.get('mst')}, Total: {xml_parsed.get('total_amount')}"

    papers["VAT_Recon"] = result
    
    msg = AIMessage(content=f"[VAT_Reconciliation_Agent]: Kết quả đối soát VAT 3 bên: {result['status']}. Lệch hóa đơn: {result['return_vs_einvoice_variance']}")
    return {"messages": [msg], "working_papers": papers}


def node_cit_adjustments(state: GraphState) -> Dict[str, Any]:
    """Tax Senior 2: CIT Deductibility."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    
    # Assume we checked a big expense
    exp = raw.get("sample_expense", 500000)
    valid_inv = raw.get("has_valid_invoice", False)
    
    result = tool_calculate_cit_adjustment(exp, valid_inv, True)
    papers["CIT_Adjustments"] = result
    
    msg = AIMessage(content=f"[CIT_Adjustments_Agent]: Phát hiện chi phí không hợp lệ: {result['non_deductible_amount']}. Lý do: {result['reason']}")
    return {"messages": [msg], "working_papers": papers}


def node_fct_tp_scanner(state: GraphState) -> Dict[str, Any]:
    """Tax Senior 3: FCT & TP Scanner."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    
    result = tool_fct_tp_scanner(
        vendor_location=raw.get("vendor_loc", "Singapore"),
        is_related_party=raw.get("is_related_party", True),
        payment_amount=raw.get("foreign_payment", 2000000)
    )
    papers["FCT_TP"] = result
    
    risk_count = len(result['risk_summary'])
    msg = AIMessage(content=f"[FCT_TP_Agent]: Cảnh báo {risk_count} rủi ro Thuế nhà thầu & Chuyển giá.")
    return {"messages": [msg], "working_papers": papers}


def node_compliance(state: GraphState) -> Dict[str, Any]:
    """Compliance Agent: Autonomous Real-time Web RAG."""
    papers = state.get("working_papers", {})
    messages = state.get("messages", [])
    
    if not messages:
        papers["Compliance"] = {"status": "Skipped", "result": "No question asked."}
        return {"messages": [], "working_papers": papers}

    question = messages[-1].content

    # Autonomous Tool Call Simulation (Without imposing heavy API crashes)
    sys_prompt = (
        "Nếu câu hỏi liên quan đến luật lệ mới nhất, năm hiện tại (2025/2026), "
        "hoặc kiến thức nội bộ không đủ -> TỰ ĐỘNG gọi tool search mạng. "
        "Mọi câu trả lời từ Web bắt buộc phải kết thúc bằng danh sách Nguồn (Source URLs)."
    )
    
    # We call the tool natively so the UI can display the status accurately
    try:
         web_data = tool_live_vietnam_tax_search.invoke({"query": question})
         content = web_data.get("content", "")
         
         if not content or len(content) < 10 or web_data.get("status") == "Error":
              # Fallback directly to LLM if blocked
              try:
                  from langchain_openai import ChatOpenAI
                  from langchain_core.messages import SystemMessage, HumanMessage
                  llm = ChatOpenAI(model="gpt-3.5-turbo", api_key="placeholder") # Localhost user bypass
                  fallback_ans = llm.invoke([
                      SystemMessage(content="Bạn là trợ lý thuế VN."), 
                      HumanMessage(content=question)
                  ]).content
              except Exception:
                  fallback_ans = "Vui lòng nhập API Key để dùng LLM dự phòng."
                  
              result = f"Hệ thống bị tường lửa chặn / Lỗi mạng, không thể tra cứu. Đây là câu trả lời dựa trên kiến thức gốc: {fallback_ans}"
         else:
              # DO REAL LLM INFERENCE summarizing the prompt
              try:
                  from langchain_openai import ChatOpenAI
                  from langchain_core.messages import HumanMessage
                  llm = ChatOpenAI(model="gpt-3.5-turbo", api_key="placeholder") 
                  prompt_text = f"Dựa trên nội dung web official này:\n{content[:3000]}\n\nHãy tóm tắt và trả lời câu hỏi: {question}"
                  analysis = llm.invoke([HumanMessage(content=prompt_text)]).content
              except Exception as e:
                  analysis = "(Lỗi kết nối OpenAI do thiếu API Key hoặc Auth, tóm tắt tự động bị hủy)"
                  
              result = (
                  f"Theo {web_data.get('url', 'N/A')}...\n"
                  f"Trích xuất {len(content)} ký tự.\n\n"
                  f"Phân tích LLM:\n{analysis}"
              )
    except Exception as e:
         result = f"Hệ thống bị lỗi mạng, không thể tra cứu: {e}"
    
    papers["Compliance"] = {"status": "Checked", "result": result, "strict_prompt": sys_prompt}
    msg = AIMessage(content=f"[Compliance_Agent]: {result}")
    return {"messages": [msg], "working_papers": papers}


def node_manager_review(state: GraphState) -> Dict[str, Any]:
    """HITL Node: This node acts purely as a pause point. The frontend injects approval here."""
    approval = state.get("manager_approval", False)
    text = "Manager APPROVED working papers." if approval else "Manager REJECTED/Needs changes."
    return {"messages": [AIMessage(content=f"[Manager]: {text}")]}


def node_management_letter(state: GraphState) -> Dict[str, Any]:
    """Reporting: Finalizes letter if approved."""
    approval = state.get("manager_approval", False)
    if not approval:
         return {"messages": [AIMessage(content="[System]: Không thể sinh Management Letter vì Sếp chưa phê duyệt (hoặc từ chối).")]}
         
    # Generate draft based on working papers
    papers = state.get("working_papers", {})
    
    draft = "### DRAFT MANAGEMENT LETTER\n\nKính gửi Ban Giám Đốc,\n\nChúng tôi xin lưu ý các điểm rủi ro: \n"
    if papers.get("VAT_Recon", {}).get("status") == "High Risk":
         draft += "- **VAT**: Lệch số liệu giữa Tờ khai và Hóa đơn điện tử.\n"
    if papers.get("CIT_Adjustments", {}).get("non_deductible_amount", 0) > 0:
         draft += f"- **CIT**: Cần bóc chi phí không hợp lệ.\n"
    if len(papers.get("FCT_TP", {}).get("risk_summary", [])) > 0:
         draft += "- **FCT/TP**: Cảnh báo giao dịch liên kết thanh toán nước ngoài.\n"
    if papers.get("Compliance", {}).get("status") == "Checked":
         draft += f"- **Compliance**: Nhận định pháp lý - {papers['Compliance']['result']}\n"
         
    return {"messages": [AIMessage(content=draft)]}


# 3. Dynamic Routing Edge
def routing_function(state: GraphState) -> str:
    """Read the routing flag set by supervisor."""
    return state.get("next_route", "TB_Mapping_Agent")


# 4. Build Graph
def build_tax_audit_graph() -> Any:
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("Supervisor_Node", node_supervisor)
    workflow.add_node("TB_Mapping_Agent", node_tb_mapping)
    workflow.add_node("VAT_Reconciliation_Agent", node_vat_recon)
    workflow.add_node("CIT_Adjustments_Agent", node_cit_adjustments)
    workflow.add_node("FCT_TP_Agent", node_fct_tp_scanner)
    workflow.add_node("Compliance_Agent", node_compliance)
    workflow.add_node("Manager_Review_Node", node_manager_review)
    workflow.add_node("Management_Letter_Agent", node_management_letter)
    
    # Edge: Start to Supervisor
    workflow.add_edge(START, "Supervisor_Node")
    
    # Conditional Edges from Supervisor
    workflow.add_conditional_edges(
        "Supervisor_Node", 
        routing_function,
        {
            "Compliance_Agent": "Compliance_Agent",
            "TB_Mapping_Agent": "TB_Mapping_Agent"
        }
    )
    
    # Audit Branch Pattern
    workflow.add_edge("TB_Mapping_Agent", "VAT_Reconciliation_Agent")
    workflow.add_edge("VAT_Reconciliation_Agent", "CIT_Adjustments_Agent")
    workflow.add_edge("CIT_Adjustments_Agent", "FCT_TP_Agent")
    workflow.add_edge("FCT_TP_Agent", "Manager_Review_Node")
    workflow.add_edge("Manager_Review_Node", "Management_Letter_Agent")
    workflow.add_edge("Management_Letter_Agent", END)
    
    # Compliance Branch Pattern (Q&A Direct Response)
    workflow.add_edge("Compliance_Agent", END)
    
    # Initialize checkpointer
    memory = MemorySaver()
    
    # INTERRUPT BEFORE MANAGER REVIEW
    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["Manager_Review_Node"]
    )
    return app
