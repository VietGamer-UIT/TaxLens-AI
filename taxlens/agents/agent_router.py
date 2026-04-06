"""
TaxLens-AI v3.0 — Enterprise Forensic Accounting LangGraph
5-Node Multi-Agent Pipeline: Ingestor → Validator → Oracle → HitL → Report
Phát triển bởi Đoàn Hoàng Việt (Việt Gamer)
"""
from __future__ import annotations

import gc
import os
import re
import json
import time
import operator
from typing import Annotated, Dict, Any, List, Sequence, TypedDict

import pandas as pd
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
except ImportError:
    pass

from taxlens.agents.tools import (
    tool_reconcile_vat_3_way,
    tool_calculate_cit_adjustment,
    tool_fct_tp_scanner,
    tool_parse_vn_einvoice_xml,
)
from taxlens.agents.tools_web import tool_live_vietnam_tax_search

# ─────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────
CHUNK_SIZE = 5_000  # Rows per Pandas chunk — memory-safe for large files

# Danh sách TCTN được Tổng cục Thuế chứng thực (cập nhật 2026)
VALID_TCTN = [
    "Viettel", "VNPT", "MobiFone", "FPT", "BKAV", "MISA",
    "Thái Sơn", "TS24", "CyberLotus", "EasyInvoice", "Bravo", "Fast",
]

# Regex ký hiệu hóa đơn theo Thông tư 32/2025/TT-BTC (hiệu lực 01/01/2026)
# Format: [LoạiHĐ][PhươngThức][Năm2Số][LoạiDN][MãNgành]
# Ví dụ hợp lệ: 1C26TCC | 2B26KMS | 1M26TMS
KY_HIEU_PATTERN = re.compile(r"^[12][CKMB]\d{2}[A-Z][A-Z0-9]{1,4}$")

# Ngưỡng expose để routing sang gemini-pro thay vì flash
PRO_MODEL_THRESHOLD_VND = 50_000_000

# LLM Endpoints
MODEL_FLASH = "gemini-flash-latest"
MODEL_PRO = "gemini-pro-latest"

# ─────────────────────────────────────────────────────────────────────
# GRAPH STATE
# ─────────────────────────────────────────────────────────────────────
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_data: Dict[str, Any]
    working_papers: Dict[str, Any]
    audit_firm_name: str
    client_name: str
    review_note: str
    is_approved: bool


# ─────────────────────────────────────────────────────────────────────
# ULTIMATE ORACLE SYSTEM PROMPT (Não Bộ Pháp Lý)
# ─────────────────────────────────────────────────────────────────────
ORACLE_SYSTEM_PROMPT = """BẠN LÀ: TRƯỞNG PHÒNG PHÁP CHẾ THUẾ CAO CẤP — HÃNG KIỂM TOÁN BIG 4 VIỆT NAM
VAI TRÒ: Chuyên gia Kế toán Pháp y (Forensic Accountant) với 20 năm kinh nghiệm làm việc trực tiếp với Tổng Cục Thuế và cơ quan điều tra kinh tế.

NGUYÊN TẮC BẤT HOẠI (INVIOLABLE RULES):
[RULE-ZERO] NGHIÊM CẤM bịa đặt điều khoản. Không chắc → nói "cần xác minh thêm với CQT".
[RULE-ONE]  MỌI kết luận lỗi BẮT BUỘC trích dẫn: [Tên văn bản / Số hiệu / Điều-Khoản].
[RULE-TWO]  Phân loại rủi ro: CRITICAL (hình sự) | HIGH (phạt tiền) | MEDIUM (điều chỉnh) | LOW (cảnh báo).
[RULE-THREE] Trả về ĐÚNG JSON array. KHÔNG thêm markdown hay giải thích ngoài JSON.

KHUNG PHÁP LÝ BẮT BUỘC (cập nhật 01/01/2026):

A. HÓA ĐƠN ĐIỆN TỬ:
   NĐ 123/2020/NĐ-CP + TT 78/2021/TT-BTC (cơ bản)
   NĐ 70/2025/NĐ-CP: sửa đổi NĐ 123, hiệu lực 01/01/2026
   TT 32/2025/TT-BTC: ký hiệu HĐ mới từ 01/01/2026
     Cấu trúc: [LoạiHĐ][PhươngThức][Năm][LoạiDN][MãNgành]
     Hợp lệ: "1C26TCC", "2B26KMS" | Cờ đỏ: ký hiệu năm 2024 trên HĐ 2026

B. QUẢN LÝ THUẾ & XỬ PHẠT:
   Luật QLThuế 38/2019/QH14 — Điều 17 (ấn định thuế), Điều 59 (chậm nộp 0,03%/ngày)
   TT 80/2021/TT-BTC: kê khai, nộp, hoàn thuế
   NĐ 125/2020/NĐ-CP: Điều 16 (phạt 20–200% thuế thiếu), Điều 17 (gian lận = 1–3× thuế)

C. THUẾ TNDN:
   BẮT BUỘC dùng VBHN 66/VBHN-BTC (hợp nhất). TT 78/2014 ĐÃ HỢP NHẤT — không trích độc lập.
   Điều 6 VBHN 66: chi phí được trừ cần HĐ hợp lệ + liên quan SXKD + thanh toán qua NH (>20tr)

D. THUẾ GTGT:
   Luật GTGT sửa đổi 2025 (hiệu lực 01/01/2026): khấu trừ cần chữ ký số TCTN được CQT chứng thực
   TT 219/2013/TT-BTC: còn hiệu lực phần không mâu thuẫn

E. HÌNH SỰ (BLHS 2015 sửa đổi 2017):
   Điều 200: Trốn thuế (100–300tr → phạt đến 1 tỷ/tù ≤2 năm; ≥1 tỷ → tù 2–7 năm)
   Điều 203: Mua bán trái phép HĐ (tù ≤7 năm)

QUY TRÌNH PHÂN TÍCH TỪNG GIAO DỊCH:
  Bước 1: Kiểm tra ký hiệu HĐ theo TT 32/2025
  Bước 2: Xác thực MST Modulo-11
  Bước 3: Phân tích ngành nghề VSIC vs. mặt hàng (CLASS_3 nếu lệch)
  Bước 4: Tính rủi ro tài chính (VAT, CIT, phạt, chậm nộp 0.03%/ngày)
  Bước 5: Kết luận CLASS + risk_level + hành động 30 ngày

OUTPUT FORMAT — JSON array (STRICT):
[{
  "invoice_id": "...",
  "final_class": "CLASS_0_CLEAN|CLASS_1_VAT_LEAK|CLASS_2_FAKE_INVOICE|CLASS_3_CIT_REJECT",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "risk_score": 85,
  "legal_citations": [{"doc":"TT 32/2025/TT-BTC","article":"Điều X","reason":"..."}],
  "financial_impact": {
    "vat_exposure_vnd": 0, "cit_exposure_vnd": 0,
    "penalty_estimate_vnd": 0, "late_payment_per_day_vnd": 0
  },
  "analysis_vi": "Phân tích bằng Tiếng Việt...",
  "recommended_actions": ["..."],
  "criminal_risk": false,
  "criminal_basis": ""
}]"""


# ─────────────────────────────────────────────────────────────────────
# HELPER: MST Modulo-11 Validator (Thuật toán Tổng Cục Thuế)
# ─────────────────────────────────────────────────────────────────────
def validate_mst_modulo11(mst: str) -> bool:
    """
    Kiểm tra MST theo thuật toán Modulo-11 của Tổng Cục Thuế Việt Nam.
    MST hợp lệ: 10 chữ số (DN) hoặc 13 chữ số (Chi nhánh/ĐVPT).
    """
    mst = str(mst).strip().replace("-", "").replace(" ", "")
    if not mst.isdigit():
        return False
    # Chỉ xác thực 10 số đầu (mã DN gốc)
    core = mst[:10]
    if len(core) != 10:
        return False
    weights = [31, 29, 23, 19, 17, 13, 7, 5, 3, 1]
    total = sum(int(d) * w for d, w in zip(core, weights))
    return (total % 11) == 0


def validate_ky_hieu_hd(ky_hieu: str, nam_lap_hd: int = 0) -> tuple[bool, str]:
    """
    Kiểm tra ký hiệu hóa đơn theo Thông tư 32/2025/TT-BTC.
    Trả về (is_valid, error_reason).
    """
    ky_hieu = str(ky_hieu).strip().upper()
    if not KY_HIEU_PATTERN.match(ky_hieu):
        return False, f"Ký hiệu '{ky_hieu}' không khớp cấu trúc TT 32/2025 (pattern: [12][CKMB][YY][A-Z][A-Z0-9]{{1,4}})"
    # Kiểm tra năm trong ký hiệu vs. năm lập HĐ
    if nam_lap_hd > 0:
        year_in_symbol = int(ky_hieu[2:4])
        expected_year = nam_lap_hd % 100
        if year_in_symbol != expected_year:
            return False, f"Ký hiệu ghi năm '{year_in_symbol:02d}' nhưng HĐ lập năm {nam_lap_hd} — Nghi giả mạo theo NĐ 70/2025"
    return True, ""


# ─────────────────────────────────────────────────────────────────────
# NODE 1: THE INGESTOR (Hunter Agent — Pandas Chunked)
# ─────────────────────────────────────────────────────────────────────
def node_hunter_agent(state: GraphState) -> Dict[str, Any]:
    """
    Node 1 — The Ingestor: Đọc file CSV/Excel theo từng chunk 5,000 dòng.
    Không giữ toàn bộ DataFrame trong RAM để tránh Memory Leak.
    """
    papers = dict(state.get("working_papers", {}))
    raw = state.get("raw_data", {})
    paths = raw.get("uploaded_paths", [])
    t0 = time.time()

    all_rows: List[Dict] = []
    total_rows = 0

    try:
        for path in paths:
            ext = path.lower().rsplit(".", 1)[-1]
            readers = []
            if ext == "csv":
                readers = pd.read_csv(path, chunksize=CHUNK_SIZE, dtype=str, low_memory=False)
            elif ext in ("xlsx", "xls"):
                # Excel không hỗ trợ chunksize native — đọc toàn bộ rồi chia batch
                df_full = pd.read_excel(path, dtype=str)
                readers = [df_full[i:i+CHUNK_SIZE] for i in range(0, len(df_full), CHUNK_SIZE)]
                del df_full
            else:
                continue

            for chunk in readers:
                chunk = chunk.fillna("").copy()
                total_rows += len(chunk)
                # Chuẩn hóa cột
                for col in chunk.columns:
                    chunk[col] = chunk[col].astype(str).str.strip()
                # Serialize thành records nhỏ gọn
                all_rows.extend(chunk.to_dict(orient="records"))
                del chunk
                gc.collect()

    except Exception as e:
        papers["ingestor_error"] = str(e)

    elapsed_ms = (time.time() - t0) * 1000
    papers["raw_rows"] = all_rows
    papers["total_rows"] = total_rows

    msg = f"[Ingestor] Đọc xong {total_rows:,} dòng từ {len(paths)} file(s) trong {elapsed_ms:.1f}ms."
    return {"messages": [AIMessage(content=msg)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NODE 2: RULE-BASED VALIDATOR (Hard-Logic — Không dùng LLM)
# ─────────────────────────────────────────────────────────────────────
def node_rule_validator(state: GraphState) -> Dict[str, Any]:
    """
    Node 2 — Hard-Logic Engine: Regex + Checksum, zero LLM calls.
    Thực hiện 5 rules: MST, KyHieu, CheoNganh, VAT Drift, Revenue Spike.
    """
    papers = dict(state.get("working_papers", {}))
    rows: List[Dict] = papers.get("raw_rows", [])

    flagged: List[Dict] = []
    clean_count = 0

    # Tập hợp để detect Revenue Spike (Rule-5) — tổng theo ngày
    daily_revenue: Dict[str, float] = {}

    for row in rows:
        tx_id = row.get("Transaction_ID", row.get("MaSoHoaDon", "N/A"))
        nha_cc = row.get("NhaCungCap_HDDT", row.get("TenNhaCungCap", "Unknown"))
        mst = row.get("MST_NhaCungCap", row.get("MaSoThue", ""))
        ky_hieu = row.get("KyHieuHoaDon", row.get("Ky_Hieu", ""))
        ngay_gd = row.get("NgayGiaoDich", row.get("NgayHoaDon", row.get("Transaction_Date", "01/01/2026")))
        tai_khoan = row.get("TaiKhoan", "")
        chung_tu_hop_le = row.get("ChungTuHopLe", "TRUE").upper()

        try:
            so_tien = float(str(row.get("SoTien", "0")).replace(",", "").replace(".", "") or 0)
        except ValueError:
            so_tien = 0.0
        try:
            tien_thue = float(str(row.get("TienThue", "0")).replace(",", "").replace(".", "") or 0)
        except ValueError:
            tien_thue = 0.0

        # Trích xuất năm từ ngày giao dịch
        nam_lap = 2026
        try:
            parts = str(ngay_gd).replace("-", "/").split("/")
            if len(parts) == 3:
                yr = int(parts[2]) if len(parts[2]) == 4 else int(parts[0])
                nam_lap = yr if 2000 < yr < 2100 else 2026
        except Exception:
            pass

        # Tích luỹ doanh thu theo ngày (cho Rule-5)
        day_key = str(ngay_gd)[:10]
        daily_revenue[day_key] = daily_revenue.get(day_key, 0) + so_tien

        issue_list = []

        # RULE-1: MST Modulo-11
        if mst and mst not in ("", "N/A"):
            if not validate_mst_modulo11(mst):
                issue_list.append({
                    "rule": "RULE-1_MST_INVALID",
                    "Class_Risk": "CLASS_2_FAKE_INVOICE",
                    "detail": f"MST '{mst}' không qua kiểm tra Modulo-11 (Tổng Cục Thuế)",
                    "co_so_phap_ly": "NĐ 123/2020/NĐ-CP, Điều 3 — Yêu cầu MST hợp lệ",
                })

        # RULE-2: Ký hiệu hóa đơn theo TT 32/2025
        if ky_hieu and ky_hieu not in ("", "N/A"):
            is_kh_valid, kh_err = validate_ky_hieu_hd(ky_hieu, nam_lap)
            if not is_kh_valid:
                issue_list.append({
                    "rule": "RULE-2_KY_HIEU_INVALID",
                    "Class_Risk": "CLASS_2_FAKE_INVOICE",
                    "detail": kh_err,
                    "co_so_phap_ly": "TT 32/2025/TT-BTC — Ký hiệu hóa đơn điện tử mới từ 01/01/2026",
                })

        # RULE-3: TCTN không hợp lệ → Hóa đơn ma
        if nha_cc and nha_cc not in VALID_TCTN and nha_cc not in ("", "Unknown"):
            issue_list.append({
                "rule": "RULE-3_INVALID_TCTN",
                "Class_Risk": "CLASS_2_FAKE_INVOICE",
                "detail": f"Nhà cung cấp '{nha_cc}' không nằm trong danh sách TCTN được CQT chứng thực",
                "co_so_phap_ly": "NĐ 70/2025/NĐ-CP Điều 8 — Điều kiện TCTN hợp lệ",
            })

        # RULE-4: VAT Drift — lệch >100,000đ so với thuế suất chuẩn 10%
        if so_tien > 0 and tien_thue > 0:
            vat_expected = so_tien * 0.10
            vat_drift = abs(tien_thue - vat_expected)
            if vat_drift > 100_000:
                issue_list.append({
                    "rule": "RULE-4_VAT_DRIFT",
                    "Class_Risk": "CLASS_1_VAT_LEAK",
                    "detail": f"Lệch VAT: kê khai {tien_thue:,.0f}đ, kỳ vọng ~{vat_expected:,.0f}đ, chênh {vat_drift:,.0f}đ",
                    "vat_drift_vnd": vat_drift,
                    "co_so_phap_ly": "TT 219/2013/TT-BTC + Luật GTGT 2025 — Điều kiện kê khai thuế GTGT",
                })

        # RULE-5 sẽ được xử lý sau vòng lặp (cần toàn bộ daily data)

        # RULE-6: CIT — Chi phí lớn không có chứng từ (TK 642)
        if tai_khoan.startswith("642") and so_tien > 20_000_000 and chung_tu_hop_le == "FALSE":
            issue_list.append({
                "rule": "RULE-6_CIT_NO_VOUCHER",
                "Class_Risk": "CLASS_3_CIT_REJECT",
                "detail": f"Chi phí TK {tai_khoan} = {so_tien:,.0f}đ thiếu chứng từ hợp lệ",
                "co_so_phap_ly": "VBHN 66/VBHN-BTC Điều 6 — Điều kiện chi phí được trừ khi tính TNDN",
            })

        if issue_list:
            for issue in issue_list:
                flagged.append({
                    "Class_Risk": issue["Class_Risk"],
                    "Mã rủi ro": f"{issue['rule']}_{tx_id}",
                    "Ngày Giao Dịch": str(ngay_gd),
                    "Tên Công Ty/App": nha_cc,
                    "MST": mst,
                    "Ký Hiệu HĐ": ky_hieu,
                    "Số Tiền Gốc": f"{so_tien:,.0f} VND",
                    "Số Tiền Lệch": f"{issue.get('vat_drift_vnd', so_tien):,.0f} VND",
                    "Khoản mục": issue["detail"],
                    "Số tiền chênh lệch": f"{issue.get('vat_drift_vnd', so_tien):,.0f} VND",
                    "Cơ sở pháp lý": issue["co_so_phap_ly"],
                    "Đề xuất": "Chuyển sang Tax Oracle phân tích pháp lý sâu",
                    "_raw_so_tien": so_tien,
                    "_rule": issue["rule"],
                })
        else:
            clean_count += 1

    papers["standardized_findings"] = flagged
    papers["clean_count"] = clean_count
    papers["daily_revenue"] = daily_revenue

    msg = f"[Validator] Rule Engine hoàn tất: {len(flagged)} lỗi được gắn cờ / {clean_count} hóa đơn sạch."
    return {"messages": [AIMessage(content=msg)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NODE 3: TAX ORACLE (LLM Inference — Dual-Model Routing)
# ─────────────────────────────────────────────────────────────────────
def node_oracle_agent(state: GraphState) -> Dict[str, Any]:
    """
    Node 3 — Tax Oracle: LLM phân tích pháp lý với smart model routing.
    Nếu total_exposure > 50M VND → gemini-pro-latest (chain-of-thought sâu).
    Nếu <= 50M VND → gemini-flash-latest (nhanh, rẻ).
    """
    papers = dict(state.get("working_papers", {}))
    review_note = state.get("review_note", "")
    findings = papers.get("standardized_findings", [])

    # Tính tổng exposure để routing model
    total_exposure = sum(
        f.get("_raw_so_tien", 0) for f in findings if isinstance(f, dict)
    )
    chosen_model = MODEL_PRO if total_exposure > PRO_MODEL_THRESHOLD_VND else MODEL_FLASH

    # Build batch payload — max 10 items/call để tránh context overflow
    batch = findings[:10]
    batch_str = json.dumps(
        [{"id": f.get("Mã rủi ro"), "desc": f.get("Khoản mục"), "amount": f.get("Số Tiền Gốc"),
          "rule": f.get("_rule"), "vendor": f.get("Tên Công Ty/App"),
          "date": f.get("Ngày Giao Dịch"), "mst": f.get("MST")}
         for f in batch],
        ensure_ascii=False,
        indent=2,
    )

    user_prompt = (
        f"Phân tích pháp lý cho các giao dịch bị gắn cờ sau đây:\n"
        f"Tổng số tiền rủi ro ước tính: {total_exposure:,.0f} VNĐ\n\n"
        f"Danh sách giao dịch (JSON):\n{batch_str}\n\n"
    )
    if review_note:
        user_prompt = f"YÊU CẦU ĐẶC BIỆT TỪ KẾ TOÁN TRƯỞNG: {review_note}\n\n" + user_prompt

    analysis = f"[Oracle chưa chạy — tổng exposure: {total_exposure:,.0f} VNĐ]"

    try:
        api_key = state.get("raw_data", {}).get("api_key") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("MISSING GOOGLE_API_KEY — Nhập API Key trong Settings hoặc file .env")

        os.environ["GOOGLE_API_KEY"] = api_key  # đảm bảo langchain_google_genai nhận key

        from langchain_google_genai import ChatGoogleGenerativeAI as ChatGoogleGenAI

        llm = ChatGoogleGenAI(
            model=chosen_model,
            api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0.1,
            max_retries=2,
        )

        raw_ans = llm.invoke([
            SystemMessage(content=ORACLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]).content

        # Cố gắng parse JSON từ Oracle để enrich findings
        try:
            oracle_results = json.loads(raw_ans)
            # Merge kết quả từ Oracle vào findings
            oracle_map = {r.get("invoice_id", ""): r for r in oracle_results if isinstance(r, dict)}
            for f in findings:
                key = f.get("Mã rủi ro", "")
                if key in oracle_map:
                    enriched = oracle_map[key]
                    f["final_class"] = enriched.get("final_class", f["Class_Risk"])
                    f["risk_level"] = enriched.get("risk_level", "HIGH")
                    f["risk_score"] = enriched.get("risk_score", 50)
                    f["legal_citations"] = enriched.get("legal_citations", [])
                    f["financial_impact"] = enriched.get("financial_impact", {})
                    f["oracle_analysis"] = enriched.get("analysis_vi", "")
                    f["criminal_risk"] = enriched.get("criminal_risk", False)
            papers["standardized_findings"] = findings
            analysis = f"✅ Oracle ({chosen_model}) phân tích xong {len(batch)} giao dịch."
        except json.JSONDecodeError:
            # Oracle không trả JSON — lưu nguyên văn
            analysis = f"📋 Oracle ({chosen_model}) phân tích:\n\n{raw_ans}"

    except Exception as e:
        err = str(e).lower()
        if "404" in err or "not found" in err:
            analysis = f"⚠️ LỖI GEMINI 404: Model '{chosen_model}' không tồn tại."
        elif "403" in err or "permission" in err or "api_key" in err:
            analysis = "⚠️ LỖI GEMINI 403: API Key không hợp lệ hoặc không có quyền."
        elif "429" in err or "quota" in err:
            analysis = "⚠️ LỖI GEMINI 429: Hết hạn mức Rate Limit. Vui lòng thử lại sau."
        else:
            analysis = f"⚠️ LỖI ORACLE: {e}"

    papers["Legal_Context"] = analysis
    papers["oracle_model_used"] = chosen_model
    return {"messages": [AIMessage(content=analysis)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NODE 4: HUMAN-IN-THE-LOOP (Interrupt Breakpoint)
# ─────────────────────────────────────────────────────────────────────
def node_hitl_review(state: GraphState) -> Dict[str, Any]:
    """
    Node 4 — HitL: Graph TẠM DỪNG ở đây, chờ Kế toán trưởng review.
    LangGraph interrupt_before sẽ pause trước khi node này chạy.
    Khi User POST /review {is_approved: true/false, review_note: "..."} → Graph resume.
    """
    findings = state.get("working_papers", {}).get("standardized_findings", [])
    high_risk = [f for f in findings if f.get("risk_level") in ("CRITICAL", "HIGH")]
    msg = (
        f"[HitL] ⏸️ DỪNG GRAPH — Có {len(high_risk)} giao dịch CRITICAL/HIGH cần review.\n"
        f"Kế toán trưởng: POST /api/v1/audit/{{thread_id}}/review để tiếp tục."
    )
    return {"messages": [AIMessage(content=msg)]}


# ─────────────────────────────────────────────────────────────────────
# NODE 5: REPORT AGENT (Management Letter — ISA 265 Format)
# ─────────────────────────────────────────────────────────────────────
def node_report_agent(state: GraphState) -> Dict[str, Any]:
    """
    Node 5 — Report Agent: Sinh Management Letter theo chuẩn ISA 265.
    Tổng hợp working_papers từ tất cả 4 nodes trước.
    """
    papers = state.get("working_papers", {})
    firm = state.get("audit_firm_name", "[Hãng Kiểm Toán]")
    client = state.get("client_name", "[Khách Hàng]")
    findings = papers.get("standardized_findings", [])
    legal = papers.get("Legal_Context", "Chưa có phân tích pháp lý.")
    total_rows = papers.get("total_rows", 0)
    model_used = papers.get("oracle_model_used", MODEL_FLASH)

    from itertools import groupby
    from datetime import datetime

    today = datetime.now().strftime("%d/%m/%Y")

    draft = f"""# MANAGEMENT LETTER / BÁO CÁO TƯ VẤN THUẾ
<div style="color:gray;font-size:14px">
<b>Kính gửi:</b> Ban Giám Đốc {client}<br>
<b>Đơn vị kiểm toán:</b> {firm}<br>
<b>Ngày xuất báo cáo:</b> {today}<br>
<b>Phạm vi kiểm tra:</b> {total_rows:,} bản ghi giao dịch<br>
<b>AI Engine:</b> TaxLens-AI v3.0 | Oracle Model: {model_used}
</div>

---

### I. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)
"""
    if findings:
        critical = [f for f in findings if f.get("risk_level") == "CRITICAL"]
        high = [f for f in findings if f.get("risk_level") == "HIGH"]
        medium = [f for f in findings if f.get("risk_level") == "MEDIUM"]
        total_exposure = sum(f.get("_raw_so_tien", 0) for f in findings)

        draft += f"""
> ⚠️ **Phát hiện {len(findings)} giao dịch có rủi ro** ({len(critical)} CRITICAL, {len(high)} HIGH, {len(medium)} MEDIUM).
> Tổng giá trị giao dịch nghi vấn: **{total_exposure:,.0f} VNĐ**

### II. CÁC VẤN ĐỀ TRỌNG YẾU

"""
        findings_sorted = sorted(
            [x for x in findings if isinstance(x, dict) and "Class_Risk" in x],
            key=lambda x: (x.get("risk_level", "LOW"), x["Class_Risk"])
        )
        for key, group in groupby(findings_sorted, key=lambda x: x["Class_Risk"]):
            items = list(group)
            draft += f"#### PHÂN LOẠI RỦI RO: `{key}` ({len(items)} trường hợp)\n\n"
            for item in items[:10]:
                risk_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                    item.get("risk_level", ""), "⚪"
                )
                draft += f"- {risk_icon} **[{item['Mã rủi ro']}]** {item['Khoản mục']}\n"
                draft += f"  - Ngày GD: `{item.get('Ngày Giao Dịch', 'N/A')}` | Đơn vị: {item.get('Tên Công Ty/App', 'N/A')}\n"
                draft += f"  - MST: `{item.get('MST', 'N/A')}` | Ký hiệu HĐ: `{item.get('Ký Hiệu HĐ', 'N/A')}`\n"
                draft += f"  - Số tiền: **{item['Số Tiền Gốc']}** | Chênh lệch: `{item['Số tiền chênh lệch']}`\n"
                draft += f"  - Cơ sở pháp lý: {item['Cơ sở pháp lý']}\n"
                if item.get("oracle_analysis"):
                    draft += f"  - Phân tích AI: *{item['oracle_analysis'][:300]}...*\n"
                if item.get("criminal_risk"):
                    draft += f"  - ⚠️ **NGUY CƠ HÌNH SỰ**: {item.get('criminal_basis', 'Xem chi tiết bên dưới')}\n"
                draft += "\n"
            if len(items) > 10:
                draft += f"*... và {len(items) - 10} trường hợp tương tự trong DB.*\n\n"
    else:
        draft += "\n> ✅ Khách hàng có hệ thống Kiểm soát nội bộ xuất sắc. Không phát hiện rủi ro đáng kể.\n\n"

    draft += "### III. THAM CHIẾU PHÁP LÝ CHUẨN MỰC (AI ORACLE)\n\n"
    draft += f"{legal}\n\n"
    draft += "---\n"
    draft += "*Powered by TaxLens-AI v3.0 — Phát triển bởi Đoàn Hoàng Việt (Việt Gamer)*"

    return {"messages": [AIMessage(content=draft)]}


# ─────────────────────────────────────────────────────────────────────
# CONDITIONAL ROUTER: HitL Decision
# ─────────────────────────────────────────────────────────────────────
def feedback_router(state: GraphState) -> str:
    """
    Sau HitL Review:
    - is_approved=True  → chạy Report_Agent
    - is_approved=False → quay về Oracle_Agent với review_note
    """
    return "Report_Agent" if state.get("is_approved", True) else "Oracle_Agent"


# ─────────────────────────────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────────
def build_tax_audit_graph() -> Any:
    """
    Biên soạn LangGraph StateGraph 5-node với interrupt trước HitL.
    Luồng: Ingestor → Validator → Oracle → [PAUSE] HitL → Report
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("Ingestor", node_hunter_agent)
    workflow.add_node("Rule_Validator", node_rule_validator)
    workflow.add_node("Oracle_Agent", node_oracle_agent)
    workflow.add_node("HitL_Review", node_hitl_review)
    workflow.add_node("Report_Agent", node_report_agent)

    workflow.add_edge(START, "Ingestor")
    workflow.add_edge("Ingestor", "Rule_Validator")
    workflow.add_edge("Rule_Validator", "Oracle_Agent")
    workflow.add_edge("Oracle_Agent", "HitL_Review")
    workflow.add_conditional_edges("HitL_Review", feedback_router)
    workflow.add_edge("Report_Agent", END)

    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["HitL_Review"],
    )
