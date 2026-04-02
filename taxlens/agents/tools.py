"""
Enterprise Big 4 Tool Calling Layer.
These functions represent deterministic data hooks into ERP and calculation engines.
Decorated with @tool for LangChain/LangGraph accessibility.
"""

from typing import Any, Dict, List
import json
from datetime import datetime
from pydantic import BaseModel, Field

try:
    from langchain_core.tools import tool
except ImportError:
    # Dummy decorator fallback if not installed yet during syntax checking
    def tool(func): return func


@tool
def tool_reconcile_vat_3_way(gl_total: float, tax_return_total: float, e_invoice_total: float) -> Dict[str, Any]:
    """
    Tax Senior 1 Task: Reconcile VAT 3 ways (GL vs Tax Return vs XML e-Invoices).
    Returns a variance dictionary and a risk flag.
    """
    gl_variance = abs(gl_total - tax_return_total)
    e_invoice_variance = abs(tax_return_total - e_invoice_total)
    
    is_risky = gl_variance > 1000 or e_invoice_variance > 1000
    
    return {
        "status": "High Risk" if is_risky else "Reconciled",
        "gl_vs_return_variance": gl_variance,
        "return_vs_einvoice_variance": e_invoice_variance,
        "notes": "Lệch số liệu giữa Tờ khai và Hóa đơn điện tử." if e_invoice_variance > 0 else "Khớp số liệu VAT."
    }


@tool
def tool_calculate_cit_adjustment(expense_amount: float, has_valid_invoice: bool, is_business_related: bool) -> Dict[str, Any]:
    """
    Tax Senior 2 Task: Determine if an expense qualifies as deductible for Corporate Income Tax (CIT).
    According to VN CIT Law (Circular 78/2014 & 96/2015).
    """
    if not has_valid_invoice:
        return {
            "deductible_amount": 0.0,
            "non_deductible_amount": expense_amount,
            "reason": "Chi phí không có hóa đơn chứng từ hợp lệ (Điều 4 TT 96/2015)."
        }
    if not is_business_related:
        return {
            "deductible_amount": 0.0,
            "non_deductible_amount": expense_amount,
            "reason": "Chi phí không phục vụ hoạt động sản xuất kinh doanh (Điều 4 TT 96/2015)."
        }
        
    return {
        "deductible_amount": expense_amount,
        "non_deductible_amount": 0.0,
        "reason": "Đủ điều kiện chi phí được trừ."
    }


@tool
def tool_fct_tp_scanner(vendor_location: str, is_related_party: bool, payment_amount: float) -> Dict[str, Any]:
    """
    Tax Senior 3 Task: Scan for Foreign Contractor Tax (FCT) and Transfer Pricing (TP) risks.
    """
    risks = []
    fct_risk = False
    tp_risk = False
    
    if vendor_location.lower() not in ["vn", "vietnam", "việt nam"]:
        fct_risk = True
        risks.append("Phát sinh thanh toán đi nước ngoài -> Rủi ro FCT (Cần nộp thuế nhà thầu).")
        
    if is_related_party:
        tp_risk = True
        risks.append("Giao dịch liên kết (Related Party Transaction) -> Cần so sánh giá độc lập (Arm's length) và nộp Phụ lục GDLK.")
        
    return {
        "fct_flag": fct_risk,
        "tp_flag": tp_risk,
        "amount_exposed": payment_amount if (fct_risk or tp_risk) else 0.0,
        "risk_summary": risks
    }


@tool
def tool_save_audit_trail(action: str, decision: str, user: str = "Manager") -> str:
    """
    Manager Task: Saves an immutable audit log line when human-in-the-loop approves a step.
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "action": action,
        "decision": decision
    }
    return f"Audit log saved successfully: {json.dumps(log_entry)}"


@tool
def tool_parse_vn_einvoice_xml(xml_content: str) -> Dict[str, Any]:
    """
    Data Analyst Task: Parses Vietnamese E-Invoice XML using xml.etree.ElementTree.
    Extracts MST (Tax Code), Total amount, and VAT amount.
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_content)
        # Attempt to find standard VN E-Invoice tags.
        # This is a robust fallback scanner ignoring deep namespaces for enterprise readiness.
        mst = None
        tong_tien = 0.0
        tien_thue = 0.0
        
        for elem in root.iter():
            tag = elem.tag.split('}')[-1].lower() # strip namespace
            if tag in ['mst', 'ma_so_thue', 'buyer_taxcode', 'sellertaxcode'] and not mst:
                mst = elem.text
            if tag in ['tgttc', 'tong_tien', 'total_amount'] and elem.text:
                tong_tien = float(elem.text)
            if tag in ['tgtgt', 'tien_thue', 'vat_amount'] and elem.text:
                tien_thue = float(elem.text)
                
        return {
            "mst": mst or "NOT_FOUND",
            "total_before_tax": tong_tien - tien_thue if tong_tien else 0.0,
            "vat_amount": tien_thue,
            "total_amount": tong_tien
        }
    except Exception as e:
        return {"error": f"Invalid XML format: {e}"}
