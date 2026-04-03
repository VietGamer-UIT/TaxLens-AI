"""
LangGraph Multi-Agent Orchestrator.
Defines the Big 4 Tax Audit fieldwork flow, terminating at Manager Review before Reporting.
"""

from typing import Annotated, Dict, Any, List, TypedDict, Sequence
import operator
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

# 1. State Definition
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_data: Dict[str, Any]      # Passed from UI (e.g. GL rows, VAT totals)
    working_papers: Dict[str, Any] # Accumulated findings
    manager_approval: bool        # Flag from HITL


# 2. Nodes (The Agents)
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


from taxlens.agents.tools_web import tool_live_vietnam_tax_search
import os

def node_compliance(state: GraphState) -> Dict[str, Any]:
    """Compliance Agent: Autonomous Real-time Web RAG."""
    papers = state.get("working_papers", {})
    raw = state.get("raw_data", {})
    question = raw.get("compliance_question")
    api_key = raw.get("api_key", "")
    
    if not question:
        papers["Compliance"] = {"status": "Skipped", "result": "No question asked."}
        return {"messages": [], "working_papers": papers}

    # Autonomous Tool Call Simulation (Without imposing heavy API crashes)
    # Using the tool explicitly here to guarantee it functions within Streamlit!
    # In a full LangChain agent: llm.bind_tools([tool_live_vietnam_tax_search])
    sys_prompt = (
        "Nếu câu hỏi liên quan đến luật lệ mới nhất, năm hiện tại (2025/2026), "
        "hoặc kiến thức nội bộ không đủ -> TỰ ĐỘNG gọi tool search mạng. "
        "Mọi câu trả lời từ Web bắt buộc phải kết thúc bằng danh sách Nguồn (Source URLs)."
    )
    
    # We call the tool natively so the UI can display the status accurately
    try:
         web_data = tool_live_vietnam_tax_search.invoke({"query": question})
         if "error" in web_data:
              result = f"Insufficient legal basis. Error: {web_data['error']}"
         else:
              result = (
                  f"Theo [Cổng Truyền Thông Chính Phủ] - Nguồn: {web_data.get('url', 'N/A')}\n\n"
                  f"Tóm tắt luật mạng: Trích xuất thành công {len(web_data.get('content', ''))} ký tự. \n"
                  f"Phân tích LLM Cloud (Mô phỏng): Dựa trên dữ liệu mạng vừa nạp trực tiếp vào RAM, {question} "
                  f"là có rủi ro nếu không có hóa đơn chứng từ."
              )
    except Exception as e:
         result = f"Insufficient legal basis. Web RAG failed: {e}"
    
    papers["Compliance"] = {"status": "Checked", "result": result, "strict_prompt": sys_prompt}
    msg = AIMessage(content=f"[Compliance_Agent]: {result}")
    return {"messages": [msg], "working_papers": papers}


def node_manager_review(state: GraphState) -> Dict[str, Any]:
    """HITL Node: This node acts purely as a pause point. The frontend injects approval here."""
    # Note: If we reach here, the graph state will hit interrupt_before.
    # When resumed, state["manager_approval"] should be set by the UI.
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


# 3. Build Graph
def build_tax_audit_graph() -> Any:
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("TB_Mapping_Agent", node_tb_mapping)
    workflow.add_node("VAT_Reconciliation_Agent", node_vat_recon)
    workflow.add_node("CIT_Adjustments_Agent", node_cit_adjustments)
    workflow.add_node("FCT_TP_Agent", node_fct_tp_scanner)
    workflow.add_node("Compliance_Agent", node_compliance)
    workflow.add_node("Manager_Review_Node", node_manager_review)
    workflow.add_node("Management_Letter_Agent", node_management_letter)
    
    # Sequence Workflow
    workflow.add_edge(START, "TB_Mapping_Agent")
    workflow.add_edge("TB_Mapping_Agent", "VAT_Reconciliation_Agent")
    workflow.add_edge("VAT_Reconciliation_Agent", "CIT_Adjustments_Agent")
    workflow.add_edge("CIT_Adjustments_Agent", "FCT_TP_Agent")
    workflow.add_edge("FCT_TP_Agent", "Compliance_Agent")
    workflow.add_edge("Compliance_Agent", "Manager_Review_Node")
    workflow.add_edge("Manager_Review_Node", "Management_Letter_Agent")
    workflow.add_edge("Management_Letter_Agent", END)
    
    # Initialize checkpointer
    memory = MemorySaver()
    
    # INTERRUPT BEFORE MANAGER REVIEW
    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["Manager_Review_Node"]
    )
    return app
