"""
Enterprise Chat UI (Streamlit Layer).
Handles multi-file uploads, chat, and Strict Human-in-the-loop (Interrupts).
Premium UI with Tabs, Metrics, and st.status.
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd

# Fix relative imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from taxlens.agents.agent_router import build_tax_audit_graph

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    HumanMessage = lambda content: content

# Initialize Graph Once
@st.cache_resource
def get_graph():
    return build_tax_audit_graph()

graph = get_graph()
# Thread helps maintain LangGraph Checkpointer state
config = {"configurable": {"thread_id": "audit_engagement_big4"}}

st.set_page_config(page_title="TaxLens Enterprise Workspace", layout="wide", page_icon="⚖️")

# Default Session State
if "raw_data" not in st.session_state:
    st.session_state["raw_data"] = {
        "gl_vat_total": 0.0,
        "tax_return_total": 0.0,
        "einvoice_total": 0.0,
        "xml_content": "",
        "sample_expense": 500000,
        "has_valid_invoice": False,
        "vendor_loc": "Vietnam",
        "is_related_party": False,
        "foreign_payment": 0.0,
        "compliance_question": None
    }
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "uploaded_dataframes" not in st.session_state:
    st.session_state["uploaded_dataframes"] = {}

# --- METRIC SIDEBAR ---
with st.sidebar:
    st.header("⚖️ TaxLens Enterprise")
    st.divider()
    
    st.subheader("📊 Audit Overview")
    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("GL Records", len(st.session_state["uploaded_dataframes"].get("gl", [])))
    metric_col2.metric("Invoices Set", "Ready" if st.session_state["raw_data"]["xml_content"] else "None")
    
    st.divider()
    st.header("🗂️ Data Ingestion")
    
    try:
        uploaded_files = st.file_uploader(
            "Upload GL (Excel/CSV) & e-Invoice (XML)", 
            accept_multiple_files=True
        )
        
        if uploaded_files:
            for file in uploaded_files:
                file_name_lower = file.name.lower()
                try:
                    if file_name_lower.endswith('.csv'):
                        df = pd.read_csv(file)
                        st.session_state["uploaded_dataframes"]["gl"] = df
                        if 'amount' in df.columns or 'so_tien' in df.columns:
                            col = 'amount' if 'amount' in df.columns else 'so_tien'
                            st.session_state["raw_data"]["gl_vat_total"] = float(pd.to_numeric(df[col], errors='coerce').sum())
                        st.success(f"Nạp thành công GL: {file.name}")
                        
                    elif file_name_lower.endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(file)
                        st.session_state["uploaded_dataframes"]["gl"] = df
                        if 'amount' in df.columns or 'so_tien' in df.columns:
                            col = 'amount' if 'amount' in df.columns else 'so_tien'
                            st.session_state["raw_data"]["gl_vat_total"] = float(pd.to_numeric(df[col], errors='coerce').sum())
                        st.success(f"Nạp thành công GL: {file.name}")
                        
                    elif file_name_lower.endswith('.xml'):
                        xml_content = file.read().decode('utf-8')
                        if not xml_content.strip():
                            raise ValueError("File XML rỗng.")
                        st.session_state["raw_data"]["xml_content"] = xml_content
                        st.success(f"Nạp thành công Hóa đơn XML: {file.name}")
                except Exception as inner_e:
                    st.error(f"Lỗi đọc file {file.name}: {str(inner_e)}")
    except Exception as e:
        st.error(f"Lỗi hệ thống khi upload: {str(e)}")

# --- MAIN UI TABS ---
tab_chat, tab_working_papers, tab_data_explorer = st.tabs(["💬 Workspace Chat", "📄 Working Papers", "🔍 Data Explorer"])

# Read state
state_info = graph.get_state(config)
is_interrupted = False
working_papers = {}

if state_info and state_info.next:
    if "Manager_Review_Node" in state_info.next:
        is_interrupted = True
        if state_info.values and "working_papers" in state_info.values:
             working_papers = state_info.values["working_papers"]

with tab_data_explorer:
    st.subheader("Raw Data Tables")
    if not st.session_state["uploaded_dataframes"]:
        st.info("No structured data uploaded yet.")
    else:
        for key, df in st.session_state["uploaded_dataframes"].items():
            st.markdown(f"**{key.upper()}**")
            st.dataframe(df, use_container_width=True)

with tab_working_papers:
    st.subheader("Audit Manager Dashboard")
    if working_papers:
        st.json(working_papers)
    else:
        st.info("Agentic fieldwork has not completed yet.")

with tab_chat:
    st.title("Fieldwork Orchestration")
    
    # Render Chat
    chat_container = st.container(height=450)
    with chat_container:
        if state_info and state_info.values and "messages" in state_info.values:
            for msg in state_info.values["messages"]:
                role = "user" if getattr(msg, "type", "ai") == "human" else "assistant"
                st.chat_message(role).markdown(getattr(msg, "content", str(msg)))
        else:
            for msg in st.session_state["chat_history"]:
                st.chat_message(msg["role"]).markdown(msg["content"])
                
    # Human in the loop Checkpoint UI
    if is_interrupted:
        st.warning("⚠️ **APPROVAL REQUIRED:** Sếp vui lòng xem 'Working Papers' và bấm quyết định để sinh Management Letter.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Phê duyệt & Chấp nhận rủi ro", use_container_width=True, type="primary"):
                with st.status("Đang cập nhật quyết định...", expanded=True) as status:
                    st.write("Ghi nhận Approval = True")
                    graph.update_state(config, {"manager_approval": True})
                    st.write("Đang sinh Báo Cáo Management Letter...")
                    graph.invoke(None, config)
                    status.update(label="Hoàn tất phê duyệt!", state="complete", expanded=False)
                st.rerun()
        with col2:
            if st.button("❌ Bác bỏ (Reject)", use_container_width=True):
                graph.update_state(config, {"manager_approval": False})
                graph.invoke(None, config)
                st.rerun()
                
    # Input
    user_input = st.chat_input("Nhắn lệnh kiểm toán hoặc yêu cầu pháp lý (Compliance)...", disabled=is_interrupted)
    if user_input:
        st.session_state["chat_history"].append({"role": "user", "content": user_input})
        st.session_state["raw_data"]["compliance_question"] = user_input
        
        initial_state = {
            "messages": [HumanMessage(content=user_input)], 
            "raw_data": st.session_state["raw_data"],
            "working_papers": {},
            "manager_approval": False
        }
        
        with st.status("🚀 Bắt đầu Fieldwork Orchestration...", expanded=True) as status:
            st.write("⏳ Gọi TB_Mapping_Agent...")
            st.write("⏳ Chạy đối soát VAT_Reconciliation_Agent...")
            st.write("🌐 Đang kết nối Internet: Tra cứu luật thuế Việt Nam mới nhất...")
            try:
                 graph.invoke(initial_state, config)
                 st.write("✅ Đã lấy dữ liệu từ Web vào RAM thành công.")
                 status.update(label="✅ Hoàn thành Fieldwork, chờ Sếp phê duyệt.", state="complete", expanded=False)
            except Exception as e:
                 status.update(label=f"❌ Lỗi: {e}", state="error", expanded=True)
                 st.chat_message("assistant").error(f"Execution Error: {e}")
                 
        st.rerun()
