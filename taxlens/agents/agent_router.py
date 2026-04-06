"""
TaxLens-AI v3.1 — Multi-Format Forensic Accounting LangGraph
Pipeline: Ingestor (CSV/XML/JSON/PDF/Image) → Validator → Oracle → HitL → Report
Phát triển bởi Đoàn Hoàng Việt (Việt Gamer)
"""
from __future__ import annotations

import base64
import gc
import json
import operator
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

import pandas as pd
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────
CHUNK_SIZE = 5_000          # Rows per Pandas CSV chunk
MAX_ORACLE_BATCH = 10       # Max items per LLM batch call
PRO_MODEL_THRESHOLD_VND = 50_000_000

MODEL_FLASH = "gemini-flash-latest"
MODEL_PRO   = "gemini-pro-latest"

AUDIT_FIRM_NAME = "TaxLens-AI B2B Partner"

# Danh sách TCTN được Tổng cục Thuế chứng thực (cập nhật 2026)
VALID_TCTN = {
    "Viettel", "VNPT", "MobiFone", "FPT", "BKAV", "MISA",
    "Thái Sơn", "TS24", "CyberLotus", "EasyInvoice", "Bravo", "Fast",
}

# Regex ký hiệu HĐ theo TT 32/2025/TT-BTC
KY_HIEU_PATTERN = re.compile(r"^[12][CKMB]\d{2}[A-Z][A-Z0-9]{1,4}$")

# VSIC codes considered financial/services (allowed to purchase misc goods)
BUSINESS_SERVICE_VSIC = {"K", "M", "N", "J", "P", "Q"}

# Supported file extensions and their human-readable type
FILE_TYPE_MAP = {
    "csv":  "CSV",
    "xlsx": "Excel",
    "xls":  "Excel",
    "xml":  "XML Hóa Đơn",
    "json": "JSON",
    "pdf":  "PDF",
    "png":  "Image (PNG)",
    "jpg":  "Image (JPG)",
    "jpeg": "Image (JPEG)",
}


# ─────────────────────────────────────────────────────────────────────
# GRAPH STATE
# ─────────────────────────────────────────────────────────────────────
class GraphState(TypedDict):
    messages:        Annotated[Sequence[BaseMessage], operator.add]
    raw_data:        Dict[str, Any]
    working_papers:  Dict[str, Any]
    audit_firm_name: str
    client_name:     str
    review_note:     str
    is_approved:     bool


# ─────────────────────────────────────────────────────────────────────
# ORACLE SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────
ORACLE_SYSTEM_PROMPT = """BẠN LÀ: TRƯỞNG PHÒNG PHÁP CHẾ THUẾ CAO CẤP — HÃNG KIỂM TOÁN BIG 4 VIỆT NAM
VAI TRÒ: Chuyên gia Kế toán Pháp y (Forensic Accountant) với 20 năm kinh nghiệm.

NGUYÊN TẮC BẤT HOẠI:
[RULE-ZERO] NGHIÊM CẤM bịa đặt điều khoản. Không chắc → "cần xác minh thêm với CQT".
[RULE-ONE]  Mọi kết luận BẮT BUỘC trích dẫn: [Tên văn bản / Số hiệu / Điều-Khoản].
[RULE-TWO]  Rủi ro: CRITICAL (hình sự) | HIGH (phạt tiền) | MEDIUM (điều chỉnh) | LOW (cảnh báo).
[RULE-THREE] Trả về ĐÚNG JSON array. KHÔNG thêm markdown hay text ngoài JSON.

KHUNG PHÁP LÝ (01/01/2026):
A. NĐ 123/2020 + TT 78/2021 + NĐ 70/2025 + TT 32/2025 (ký hiệu HĐ mới)
B. Luật QLThuế 38/2019 Điều 17, 59 | NĐ 125/2020 Điều 16–17 | TT 80/2021
C. VBHN 66/VBHN-BTC (TNDN hợp nhất) Điều 6 — không trích TT 78/2014 riêng lẻ
D. Luật GTGT 2025 + TT 219/2013 (phần không mâu thuẫn)
E. BLHS 2015 sửa đổi 2017: Điều 200 (trốn thuế), 203 (HĐ giả), 206 (tài chính)

OUTPUT FORMAT — JSON array (STRICT):
[{
  "invoice_id": "...",
  "final_class": "CLASS_0_CLEAN|CLASS_1_VAT_LEAK|CLASS_2_FAKE_INVOICE|CLASS_3_CIT_REJECT",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "risk_score": 85,
  "legal_citations": [{"doc":"...","article":"...","reason":"..."}],
  "financial_impact": {
    "vat_exposure_vnd": 0, "cit_exposure_vnd": 0,
    "penalty_estimate_vnd": 0, "late_payment_per_day_vnd": 0
  },
  "analysis_vi": "...",
  "recommended_actions": ["..."],
  "criminal_risk": false,
  "criminal_basis": ""
}]"""


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────
def validate_mst_modulo11(mst: str) -> bool:
    mst = str(mst).strip().replace("-", "").replace(" ", "")
    if not mst.isdigit():
        return False
    core = mst[:10]
    if len(core) != 10:
        return False
    weights = [31, 29, 23, 19, 17, 13, 7, 5, 3, 1]
    total = sum(int(d) * w for d, w in zip(core, weights))
    return (total % 11) == 0


def validate_ky_hieu_hd(ky_hieu: str, nam_lap_hd: int = 0) -> tuple[bool, str]:
    ky_hieu = str(ky_hieu).strip().upper()
    if not KY_HIEU_PATTERN.match(ky_hieu):
        return False, f"Ký hiệu '{ky_hieu}' không khớp cấu trúc TT 32/2025"
    if nam_lap_hd > 0:
        year_in_symbol = int(ky_hieu[2:4])
        expected_year = nam_lap_hd % 100
        if year_in_symbol != expected_year:
            return False, (
                f"Ký hiệu ghi năm '{year_in_symbol:02d}' nhưng HĐ lập năm "
                f"{nam_lap_hd} — Nghi giả mạo theo NĐ 70/2025"
            )
    return True, ""


def _extract_year(date_str: str) -> int:
    try:
        parts = str(date_str).replace("-", "/").split("/")
        if len(parts) == 3:
            yr = int(parts[2]) if len(parts[2]) == 4 else int(parts[0])
            return yr if 2000 < yr < 2100 else 2026
    except Exception:
        pass
    return 2026


def _safe_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", "").replace(".", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────
# PARSERS — one per file type
# ─────────────────────────────────────────────────────────────────────

def parse_csv(path: str, status_cb=None) -> List[Dict]:
    """Chunked CSV reader — memory-safe for 100k+ rows."""
    rows: List[Dict] = []
    for chunk in pd.read_csv(path, chunksize=CHUNK_SIZE, dtype=str, low_memory=False):
        chunk = chunk.fillna("").copy()
        for col in chunk.columns:
            chunk[col] = chunk[col].astype(str).str.strip()
        rows.extend(chunk.to_dict(orient="records"))
        del chunk
        gc.collect()
    return rows


def parse_excel(path: str, status_cb=None) -> List[Dict]:
    """Excel reader with chunking emulation."""
    rows: List[Dict] = []
    df = pd.read_excel(path, dtype=str, engine="openpyxl")
    df = df.fillna("")
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    rows = df.to_dict(orient="records")
    del df
    gc.collect()
    return rows


def parse_xml(path: str, status_cb=None) -> List[Dict]:
    """
    Parser for Vietnamese e-invoice XML (NĐ 123/2020, TT 78/2021).
    Supports both Viettel/FPT schema and generic flat XML records.
    """
    rows: List[Dict] = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        # Strip namespace prefixes for easier XPath
        def strip_ns(tag: str) -> str:
            return tag.split("}")[-1] if "}" in tag else tag

        def elem_to_dict(elem) -> Dict:
            d: Dict = {}
            for child in elem:
                key = strip_ns(child.tag)
                text = (child.text or "").strip()
                d[key] = text
            return d

        # Try known Vietnamese invoice schemas
        invoice_tags = {"HoaDon", "Invoice", "InvoiceData", "HDon", "invoiceItem", "RECORD"}
        found_invoices = False
        for elem in root.iter():
            tag = strip_ns(elem.tag)
            if tag in invoice_tags:
                row = elem_to_dict(elem)
                if row:
                    rows.append(row)
                    found_invoices = True

        # Fallback: flatten all leaf nodes of each direct child
        if not found_invoices:
            for child in root:
                row = elem_to_dict(child)
                if row:
                    rows.append(row)

    except Exception as e:
        rows.append({"_parse_error": f"XML parse failed: {e}", "source_file": path})
    return rows


def parse_json(path: str, status_cb=None) -> List[Dict]:
    """JSON list or single-object normalizer."""
    rows: List[Dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            rows = [r if isinstance(r, dict) else {"value": str(r)} for r in data]
        elif isinstance(data, dict):
            # Could be {invoices: [...]} or flat
            for key, val in data.items():
                if isinstance(val, list):
                    rows = [r if isinstance(r, dict) else {"value": str(r)} for r in val]
                    break
            if not rows:
                rows = [data]
    except Exception as e:
        rows.append({"_parse_error": f"JSON parse failed: {e}", "source_file": path})
    return rows


def parse_pdf(path: str, status_cb=None) -> List[Dict]:
    """
    pdfplumber-based table extractor.
    Extracts tables from each page; falls back to raw text lines if no tables found.
    """
    rows: List[Dict] = []
    try:
        import pdfplumber
    except ImportError:
        return [{"_parse_error": "pdfplumber not installed. Run: pip install pdfplumber", "source_file": path}]

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        if not table or not table[0]:
                            continue
                        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                        for data_row in table[1:]:
                            if data_row and any(cell for cell in data_row):
                                row_dict = {
                                    headers[i]: str(cell).strip() if cell else ""
                                    for i, cell in enumerate(data_row)
                                    if i < len(headers)
                                }
                                row_dict["_source_page"] = str(page_num)
                                rows.append(row_dict)
                else:
                    # No tables: extract text lines as key-value guesses
                    text = page.extract_text() or ""
                    rows.append({"_raw_text": text[:2000], "_source_page": str(page_num), "source_file": path})
    except Exception as e:
        rows.append({"_parse_error": f"PDF parse failed: {e}", "source_file": path})
    return rows


def parse_image_gemini_vision(path: str, api_key: str, status_cb=None) -> List[Dict]:
    """
    Uses Gemini Vision (gemini-flash-latest) to extract invoice data from PNG/JPG.
    Returns structured rows. Requires valid API key.
    """
    VISION_PROMPT = """Bạn nhận được ảnh một hóa đơn. Hãy trích xuất toàn bộ thông tin vào JSON array.
Mỗi phần tử của array là một dòng hàng hoá/dịch vụ trên hóa đơn.
Các trường cần trích xuất (nếu có): SoHoaDon, NgayHoaDon, MST_NhaCungCap, TenNhaCungCap, KyHieuHoaDon, TenHangHoa, SoLuong, DonGia, SoTien, TienThue, TongTien.
Trả về CHỈ JSON array. KHÔNG giải thích thêm."""
    rows: List[Dict] = []
    try:
        if not api_key:
            raise ValueError("API Key bị thiếu — không thể dùng Gemini Vision")

        with open(path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        ext = path.lower().rsplit(".", 1)[-1]
        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
        mime_type = mime_map.get(ext, "image/png")

        from google import genai as google_genai
        from google.genai import types as genai_types

        client = google_genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL_FLASH,
            contents=[
                genai_types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                VISION_PROMPT,
            ],
        )
        raw_text = response.text.strip()
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text).rstrip("`").strip()
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            rows = parsed
        elif isinstance(parsed, dict):
            rows = [parsed]
        for r in rows:
            r["_source_file"] = os.path.basename(path)
            r["_parser"] = "gemini-vision"
    except json.JSONDecodeError:
        # Vision returned text but not parseable JSON — store as raw
        rows.append({
            "_raw_text": raw_text[:1000] if "raw_text" in dir() else "No response",
            "_source_file": os.path.basename(path),
            "_parser": "gemini-vision-raw",
        })
    except Exception as e:
        rows.append({
            "_parse_error": f"Gemini Vision failed: {e}",
            "_source_file": os.path.basename(path),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────
# FILE-TYPE ROUTER  (used by node_hunter_agent)
# ─────────────────────────────────────────────────────────────────────
def route_and_parse_file(path: str, api_key: str = "") -> tuple[List[Dict], str]:
    """
    Determines file type and dispatches to correct parser.
    Returns (rows, human_readable_type).
    """
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else "csv"
    ftype = FILE_TYPE_MAP.get(ext, ext.upper())

    if ext == "csv":
        return parse_csv(path), ftype
    elif ext in ("xlsx", "xls"):
        return parse_excel(path), ftype
    elif ext == "xml":
        return parse_xml(path), ftype
    elif ext == "json":
        return parse_json(path), ftype
    elif ext == "pdf":
        return parse_pdf(path), ftype
    elif ext in ("png", "jpg", "jpeg"):
        return parse_image_gemini_vision(path, api_key), ftype
    else:
        return [{"_parse_error": f"Unsupported file type: .{ext}"}], ftype


# ─────────────────────────────────────────────────────────────────────
# NÚT 1: INGESTOR — Multi-Format, Parallel per file
# ─────────────────────────────────────────────────────────────────────
def node_hunter_agent(state: GraphState) -> Dict[str, Any]:
    """
    Node 1 — Ingestor: phát hiện loại file, parse đúng parser.
    CSV → chunked Pandas | XML → ElementTree | PDF → pdfplumber
    XLSX → openpyxl | JSON → json.load | Image → Gemini Vision
    Files được parse song song qua ThreadPoolExecutor.
    """
    papers = dict(state.get("working_papers", {}))
    raw = state.get("raw_data", {})
    paths: List[str] = raw.get("uploaded_paths", [])
    api_key: str = raw.get("api_key", "")
    t0 = time.time()

    all_rows: List[Dict] = []
    file_summary: List[Dict] = []

    def _parse(path: str):
        return path, *route_and_parse_file(path, api_key)

    # Parallel parse — ThreadPoolExecutor safe for IO+CPU mix
    with ThreadPoolExecutor(max_workers=min(len(paths), 4)) as executor:
        futures = {executor.submit(_parse, p): p for p in paths}
        for future in as_completed(futures):
            try:
                fpath, rows, ftype = future.result()
                all_rows.extend(rows)
                file_summary.append({
                    "file": os.path.basename(fpath),
                    "type": ftype,
                    "records": len(rows),
                })
            except Exception as e:
                file_summary.append({"file": str(futures[future]), "type": "ERROR", "error": str(e)})

    elapsed_ms = (time.time() - t0) * 1000

    # Build human‑readable ingest summary
    type_counts = {}
    for fs in file_summary:
        t = fs["type"]
        type_counts[t] = type_counts.get(t, 0) + fs.get("records", 0)
    summary_parts = [f"{v:,} dòng {k}" for k, v in type_counts.items()]
    summary_str = " | ".join(summary_parts) if summary_parts else "0 dòng"

    papers["raw_rows"] = all_rows
    papers["total_rows"] = len(all_rows)
    papers["file_summary"] = file_summary
    papers["ingest_elapsed_ms"] = round(elapsed_ms, 1)

    msg = f"[Ingestor] ✅ Đọc xong {len(all_rows):,} bản ghi từ {len(paths)} file(s) ({summary_str}) trong {elapsed_ms:.1f}ms."
    return {"messages": [AIMessage(content=msg)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NÚT 2: VALIDATOR — Hard-Logic, Parallel rules via ThreadPoolExecutor
# ─────────────────────────────────────────────────────────────────────
def _validate_single_row(row: Dict) -> Optional[List[Dict]]:
    """Validate one row, return list of issues or None if clean."""
    tx_id    = row.get("Transaction_ID") or row.get("MaSoHoaDon") or row.get("SoHoaDon", "N/A")
    nha_cc   = row.get("NhaCungCap_HDDT") or row.get("TenNhaCungCap") or row.get("TenNhaCungCap", "Unknown")
    mst      = row.get("MST_NhaCungCap") or row.get("MaSoThue", "")
    ky_hieu  = row.get("KyHieuHoaDon") or row.get("Ky_Hieu", "")
    ngay_gd  = (row.get("NgayGiaoDich") or row.get("NgayHoaDon") or
                row.get("Transaction_Date", "01/01/2026"))
    tai_khoan = row.get("TaiKhoan", "")
    chung_tu = row.get("ChungTuHopLe", "TRUE").upper()

    so_tien  = _safe_float(row.get("SoTien") or row.get("DonGia", "0"))
    tien_thue = _safe_float(row.get("TienThue", "0"))
    nam_lap  = _extract_year(str(ngay_gd))

    issues: List[Dict] = []

    # RULE-1: MST Modulo-11
    if mst and mst not in ("", "N/A"):
        if not validate_mst_modulo11(mst):
            issues.append({
                "rule": "RULE-1_MST_INVALID",
                "Class_Risk": "CLASS_2_FAKE_INVOICE",
                "detail": f"MST '{mst}' không qua kiểm tra Modulo-11",
                "co_so_phap_ly": "NĐ 123/2020/NĐ-CP Điều 3 — Yêu cầu MST hợp lệ",
                "vat_drift_vnd": so_tien,
            })

    # RULE-2: Ký hiệu HĐ theo TT 32/2025
    if ky_hieu and ky_hieu not in ("", "N/A"):
        ok, err = validate_ky_hieu_hd(ky_hieu, nam_lap)
        if not ok:
            issues.append({
                "rule": "RULE-2_KY_HIEU_INVALID",
                "Class_Risk": "CLASS_2_FAKE_INVOICE",
                "detail": err,
                "co_so_phap_ly": "TT 32/2025/TT-BTC — Ký hiệu hóa đơn điện tử từ 01/01/2026",
                "vat_drift_vnd": so_tien,
            })

    # RULE-3: TCTN không hợp lệ
    if nha_cc and nha_cc not in VALID_TCTN and nha_cc not in ("", "Unknown"):
        issues.append({
            "rule": "RULE-3_INVALID_TCTN",
            "Class_Risk": "CLASS_2_FAKE_INVOICE",
            "detail": f"Nhà cung cấp '{nha_cc}' không trong danh sách TCTN CQT chứng thực",
            "co_so_phap_ly": "NĐ 70/2025/NĐ-CP Điều 8 — Điều kiện TCTN hợp lệ",
            "vat_drift_vnd": so_tien,
        })

    # RULE-4: VAT Drift >100k
    if so_tien > 0 and tien_thue > 0:
        vat_expected = so_tien * 0.10
        drift = abs(tien_thue - vat_expected)
        if drift > 100_000:
            issues.append({
                "rule": "RULE-4_VAT_DRIFT",
                "Class_Risk": "CLASS_1_VAT_LEAK",
                "detail": f"Lệch VAT: kê khai {tien_thue:,.0f}đ, kỳ vọng ~{vat_expected:,.0f}đ, chênh {drift:,.0f}đ",
                "co_so_phap_ly": "TT 219/2013/TT-BTC + Luật GTGT 2025",
                "vat_drift_vnd": drift,
            })

    # RULE-5: CIT — chi phí TK 64x không có chứng từ
    if tai_khoan.startswith("64") and so_tien > 20_000_000 and chung_tu == "FALSE":
        issues.append({
            "rule": "RULE-5_CIT_NO_VOUCHER",
            "Class_Risk": "CLASS_3_CIT_REJECT",
            "detail": f"Chi phí TK {tai_khoan} = {so_tien:,.0f}đ thiếu chứng từ hợp lệ",
            "co_so_phap_ly": "VBHN 66/VBHN-BTC Điều 6 — Điều kiện chi phí được trừ TNDN",
            "vat_drift_vnd": so_tien,
        })

    # RULE-6: Thanh toán tiền mặt lớn >20tr (vi phạm điều kiện CIT)
    payment_method = str(row.get("PhuongThucThanhToan") or row.get("HinhThucThanhToan", "")).upper()
    if so_tien > 20_000_000 and any(kw in payment_method for kw in ("TIỀN MẶT", "CASH", "TM")):
        issues.append({
            "rule": "RULE-6_CASH_EXCEED_20M",
            "Class_Risk": "CLASS_3_CIT_REJECT",
            "detail": f"Thanh toán tiền mặt {so_tien:,.0f}đ (>20 triệu) — không được trừ khi tính TNDN",
            "co_so_phap_ly": "VBHN 66/VBHN-BTC Điều 6, Khoản 4 — Bắt buộc thanh toán không dùng tiền mặt",
            "vat_drift_vnd": so_tien,
        })

    if not issues:
        return None

    results = []
    for issue in issues:
        results.append({
            "Class_Risk":         issue["Class_Risk"],
            "Mã rủi ro":          f"{issue['rule']}_{tx_id}",
            "Ngày Giao Dịch":     str(ngay_gd),
            "Tên Công Ty/App":    nha_cc,
            "MST":                mst,
            "Ký Hiệu HĐ":        ky_hieu,
            "Số Tiền Gốc":        f"{so_tien:,.0f} VND",
            "Số Tiền Lệch":       f"{issue['vat_drift_vnd']:,.0f} VND",
            "Khoản mục":          issue["detail"],
            "Số tiền chênh lệch": f"{issue['vat_drift_vnd']:,.0f} VND",
            "Cơ sở pháp lý":      issue["co_so_phap_ly"],
            "Đề xuất":            "Chuyển sang Tax Oracle phân tích pháp lý sâu",
            "_raw_so_tien":       so_tien,
            "_rule":              issue["rule"],
        })
    return results


def node_rule_validator(state: GraphState) -> Dict[str, Any]:
    """
    Node 2 — Hard-Logic Engine: 6 rules, zero LLM calls.
    Rows validated in parallel via ThreadPoolExecutor (CPU-bound safe).
    """
    papers = dict(state.get("working_papers", {}))
    rows: List[Dict] = papers.get("raw_rows", [])

    flagged: List[Dict] = []
    clean_count = 0

    # Parallel validation — batch rows across CPU threads
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_validate_single_row, row) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            if result:
                flagged.extend(result)
            else:
                clean_count += 1

    papers["standardized_findings"] = flagged
    papers["clean_count"] = clean_count

    msg = f"[Validator] ⚡ Parallel Rule Engine hoàn tất: {len(flagged)} lỗi / {clean_count} sạch."
    return {"messages": [AIMessage(content=msg)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NÚT 3: ORACLE — Dual-Model Routing + LLM batch()
# ─────────────────────────────────────────────────────────────────────
def node_oracle_agent(state: GraphState) -> Dict[str, Any]:
    """
    Node 3 — Tax Oracle: Smart routing Flash/Pro, batch invoke for speed.
    """
    papers = dict(state.get("working_papers", {}))
    review_note = state.get("review_note", "")
    findings: List[Dict] = papers.get("standardized_findings", [])

    total_exposure = sum(f.get("_raw_so_tien", 0) for f in findings if isinstance(f, dict))
    chosen_model = MODEL_PRO if total_exposure > PRO_MODEL_THRESHOLD_VND else MODEL_FLASH

    analysis = f"[Oracle chưa chạy — exposure: {total_exposure:,.0f} VNĐ]"

    if not findings:
        analysis = "✅ Không có giao dịch nào bị gắn cờ. Hồ sơ sạch."
        papers["Legal_Context"] = analysis
        papers["oracle_model_used"] = chosen_model
        return {"messages": [AIMessage(content=analysis)], "working_papers": papers}

    try:
        api_key = state.get("raw_data", {}).get("api_key") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("MISSING GOOGLE_API_KEY — Nhập API Key trong Settings")

        os.environ["GOOGLE_API_KEY"] = api_key

        from langchain_google_genai import ChatGoogleGenerativeAI as ChatGoogleGenAI

        llm = ChatGoogleGenAI(
            model=chosen_model,
            api_key=api_key,
            temperature=0.1,
            max_retries=2,
        )

        # Batch processing — split findings into chunks of MAX_ORACLE_BATCH
        all_enriched: List[Dict] = []
        batches = [findings[i:i+MAX_ORACLE_BATCH] for i in range(0, len(findings), MAX_ORACLE_BATCH)]

        batch_messages = []
        for batch in batches:
            batch_payload = [
                {
                    "id": f.get("Mã rủi ro"),
                    "desc": f.get("Khoản mục"),
                    "amount": f.get("Số Tiền Gốc"),
                    "rule": f.get("_rule"),
                    "vendor": f.get("Tên Công Ty/App"),
                    "date": f.get("Ngày Giao Dịch"),
                    "mst": f.get("MST"),
                }
                for f in batch
            ]
            user_msg = (
                f"{'YÊU CẦU ĐẶC BIỆT: ' + review_note + chr(10) if review_note else ''}"
                f"Phân tích pháp lý. Tổng exposure: {total_exposure:,.0f} VNĐ.\n"
                f"Batch:\n{json.dumps(batch_payload, ensure_ascii=False, indent=2)}"
            )
            batch_messages.append([
                SystemMessage(content=ORACLE_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ])

        # Use batch() for parallel LLM calls across batches
        if len(batch_messages) == 1:
            responses = [llm.invoke(batch_messages[0])]
        else:
            responses = llm.batch(batch_messages)

        for resp, batch in zip(responses, batches):
            raw_ans = resp.content if hasattr(resp, "content") else str(resp)
            try:
                # Strip code fences
                cleaned = re.sub(r"^```[a-z]*\n?", "", raw_ans.strip()).rstrip("`").strip()
                oracle_results = json.loads(cleaned)
                oracle_map = {r.get("invoice_id", ""): r for r in oracle_results if isinstance(r, dict)}
                for finding in batch:
                    key = finding.get("Mã rủi ro", "")
                    if key in oracle_map:
                        enriched = oracle_map[key]
                        finding["final_class"]     = enriched.get("final_class", finding["Class_Risk"])
                        finding["risk_level"]      = enriched.get("risk_level", "HIGH")
                        finding["risk_score"]      = enriched.get("risk_score", 50)
                        finding["legal_citations"] = enriched.get("legal_citations", [])
                        finding["financial_impact"]= enriched.get("financial_impact", {})
                        finding["oracle_analysis"] = enriched.get("analysis_vi", "")
                        finding["criminal_risk"]   = enriched.get("criminal_risk", False)
                        finding["criminal_basis"]  = enriched.get("criminal_basis", "")
                all_enriched.extend(batch)
            except json.JSONDecodeError:
                for finding in batch:
                    finding["oracle_analysis"] = raw_ans[:500]
                all_enriched.extend(batch)

        papers["standardized_findings"] = all_enriched
        analysis = f"✅ Oracle ({chosen_model}) hoàn tất {len(findings)} giao dịch qua {len(batches)} batch(es)."

    except Exception as e:
        err = str(e).lower()
        if "404" in err or "not found" in err:
            analysis = f"⚠️ LỖI 404: Model '{chosen_model}' không tồn tại."
        elif "403" in err or "permission" in err or "api_key" in err or "key" in err:
            analysis = "⚠️ LỖI 403: API Key không hợp lệ hoặc thiếu quyền."
        elif "429" in err or "quota" in err:
            analysis = "⚠️ LỖI 429: Hết hạn mức Rate Limit. Thử lại sau."
        else:
            analysis = f"⚠️ LỖI ORACLE: {e}"

    papers["Legal_Context"] = analysis
    papers["oracle_model_used"] = chosen_model
    return {"messages": [AIMessage(content=analysis)], "working_papers": papers}


# ─────────────────────────────────────────────────────────────────────
# NÚT 4: HitL REVIEW
# ─────────────────────────────────────────────────────────────────────
def node_hitl_review(state: GraphState) -> Dict[str, Any]:
    findings = state.get("working_papers", {}).get("standardized_findings", [])
    high_risk = [f for f in findings if f.get("risk_level") in ("CRITICAL", "HIGH")]
    msg = (
        f"[HitL] ⏸️ DỪNG — {len(high_risk)} giao dịch CRITICAL/HIGH chờ review.\n"
        f"POST /api/v1/audit/{{thread_id}}/review để tiếp tục."
    )
    return {"messages": [AIMessage(content=msg)]}


# ─────────────────────────────────────────────────────────────────────
# NÚT 5: REPORT AGENT — ISA 265 Management Letter
# ─────────────────────────────────────────────────────────────────────
def node_report_agent(state: GraphState) -> Dict[str, Any]:
    papers  = state.get("working_papers", {})
    client  = state.get("client_name", "[Khách Hàng]")
    findings: List[Dict] = papers.get("standardized_findings", [])
    legal   = papers.get("Legal_Context", "Chưa có phân tích pháp lý.")
    total_rows = papers.get("total_rows", 0)
    model_used = papers.get("oracle_model_used", MODEL_FLASH)
    file_summary: List[Dict] = papers.get("file_summary", [])

    from itertools import groupby
    from datetime import datetime

    today = datetime.now().strftime("%d/%m/%Y")

    # File summary table
    file_rows = ""
    for fs in file_summary:
        file_rows += f"| {fs['file']} | {fs['type']} | {fs.get('records', 0):,} |\n"

    draft = f"""# MANAGEMENT LETTER / BÁO CÁO TƯ VẤN THUẾ
<div style="color:gray;font-size:14px">
<b>Kính gửi:</b> Ban Giám Đốc {client}<br>
<b>Đơn vị thực hiện:</b> {AUDIT_FIRM_NAME}<br>
<b>Ngày xuất báo cáo:</b> {today}<br>
<b>Phạm vi:</b> {total_rows:,} bản ghi | AI Engine: TaxLens-AI v3.1 | Oracle: {model_used}
</div>

---

### I. NGUỒN DỮ LIỆU KIỂM TOÁN

| File | Định dạng | Bản ghi |
|---|---|---|
{file_rows if file_rows else "| — | — | — |\n"}

### II. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)
"""
    if findings:
        critical  = [f for f in findings if f.get("risk_level") == "CRITICAL"]
        high      = [f for f in findings if f.get("risk_level") == "HIGH"]
        medium    = [f for f in findings if f.get("risk_level") == "MEDIUM"]
        total_exp = sum(f.get("_raw_so_tien", 0) for f in findings)

        draft += f"""
> ⚠️ **Phát hiện {len(findings)} giao dịch rủi ro** ({len(critical)} CRITICAL | {len(high)} HIGH | {len(medium)} MEDIUM).
> Tổng giá trị nghi vấn: **{total_exp:,.0f} VNĐ**

### III. CÁC VẤN ĐỀ TRỌNG YẾU

"""
        sorted_findings = sorted(
            [x for x in findings if isinstance(x, dict) and "Class_Risk" in x],
            key=lambda x: (x.get("risk_level", "LOW"), x["Class_Risk"])
        )
        for cls_key, group in groupby(sorted_findings, key=lambda x: x["Class_Risk"]):
            items = list(group)
            draft += f"#### PHÂN LOẠI: `{cls_key}` ({len(items)} trường hợp)\n\n"
            for item in items[:10]:
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                    item.get("risk_level", ""), "⚪"
                )
                draft += f"- {icon} **[{item['Mã rủi ro']}]** {item['Khoản mục']}\n"
                draft += f"  - 📅 Ngày: `{item.get('Ngày Giao Dịch', 'N/A')}` | 🏢 {item.get('Tên Công Ty/App', 'N/A')}\n"
                draft += f"  - MST: `{item.get('MST', 'N/A')}` | Ký hiệu: `{item.get('Ký Hiệu HĐ', 'N/A')}`\n"
                draft += f"  - 💰 {item['Số Tiền Gốc']} | Chênh lệch: `{item['Số tiền chênh lệch']}`\n"
                draft += f"  - ⚖️ {item['Cơ sở pháp lý']}\n"
                if item.get("oracle_analysis"):
                    draft += f"  - 🤖 *{item['oracle_analysis'][:300]}*\n"
                if item.get("criminal_risk"):
                    draft += f"  - ⚠️ **NGUY CƠ HÌNH SỰ**: {item.get('criminal_basis', '')}\n"
                draft += "\n"
            if len(items) > 10:
                draft += f"*... và {len(items) - 10} trường hợp khác.*\n\n"
    else:
        draft += "\n> ✅ Không phát hiện rủi ro đáng kể. Hồ sơ thuế sạch.\n\n"

    draft += "### IV. PHÂN TÍCH PHÁP LÝ (AI ORACLE)\n\n"
    draft += f"{legal}\n\n"
    draft += "---\n"
    draft += f"*Powered by TaxLens-AI v3.1 — Phát triển bởi Đoàn Hoàng Việt (Việt Gamer) | {AUDIT_FIRM_NAME}*"

    return {"messages": [AIMessage(content=draft)]}


# ─────────────────────────────────────────────────────────────────────
# ROUTER + GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────────
def feedback_router(state: GraphState) -> str:
    return "Report_Agent" if state.get("is_approved", True) else "Oracle_Agent"


def build_tax_audit_graph() -> Any:
    workflow = StateGraph(GraphState)
    workflow.add_node("Ingestor",       node_hunter_agent)
    workflow.add_node("Rule_Validator", node_rule_validator)
    workflow.add_node("Oracle_Agent",   node_oracle_agent)
    workflow.add_node("HitL_Review",    node_hitl_review)
    workflow.add_node("Report_Agent",   node_report_agent)

    workflow.add_edge(START, "Ingestor")
    workflow.add_edge("Ingestor",       "Rule_Validator")
    workflow.add_edge("Rule_Validator", "Oracle_Agent")
    workflow.add_edge("Oracle_Agent",   "HitL_Review")
    workflow.add_conditional_edges("HitL_Review", feedback_router)
    workflow.add_edge("Report_Agent", END)

    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["HitL_Review"],
    )
