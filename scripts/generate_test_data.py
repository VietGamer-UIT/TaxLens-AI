import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_mock_data():
    os.makedirs("sample_data", exist_ok=True)
    
    # Danh sách Tổ chức truyền nhận (TCTN) Hợp Lệ
    VALID_TCTN = ["Viettel", "VNPT", "MobiFone", "FPT", "BKAV", "MISA", "Thái Sơn", "TS24", "CyberLotus"]
    FAKE_TCTN = ["PhanMemHoaDonGia", "TaxCloneApp", "UnregisteredSoft", "SuperInvoicePro"]
    
    data = []
    base_date = datetime(2026, 1, 1)
    
    for i in range(1, 5001):
        ngay = base_date + timedelta(days=random.randint(0, 360))
        ngay_str = ngay.strftime("%d/%m/%Y")
        
        # Random probabilities cho 4 Multi-class Labels
        rand = random.random()
        if rand < 0.85:
            risk_label = "CLASS_0_SAFE"
        elif rand < 0.90:
            risk_label = "CLASS_1_VAT_LEAK"
        elif rand < 0.95:
            risk_label = "CLASS_2_FAKE_INVOICE"
        else:
            risk_label = "CLASS_3_CIT_REJECT"
            
        # Default Normal Transaction
        nha_cung_cap = random.choice(VALID_TCTN)
        ma_so_thue = f"{random.randint(1000000000, 9999999999)}"
        so_tien = random.randint(1000000, 20000000)
        tien_thue = so_tien * 0.10
        tai_khoan = random.choice(["111", "112", "152", "156", "331", "511", "1331"])
        chung_tu = True
        
        # Inject Risk Properties based on Class
        if risk_label == "CLASS_1_VAT_LEAK":
            tai_khoan = "1331"
            tien_thue = so_tien * random.choice([0.05, 0.08, 0.12]) # Độ lệch VAT bất thường (VD: 5%, 8%, 12%)
        elif risk_label == "CLASS_2_FAKE_INVOICE":
            nha_cung_cap = random.choice(FAKE_TCTN)
        elif risk_label == "CLASS_3_CIT_REJECT":
            tai_khoan = "642"
            so_tien = random.randint(25000000, 100000000) # Số tiền cực lớn
            chung_tu = False # Không có chứng từ
            
        data.append({
            "Transaction_ID": f"TX_{i}",
            "NgayGhiSo": ngay_str,
            "TaiKhoan": tai_khoan,
            "MaSoThue": ma_so_thue,
            "NhaCungCap_HDDT": nha_cung_cap,
            "SoTien": so_tien,
            "TienThue": tien_thue,
            "ChungTuHopLe": chung_tu,
            "Risk_Label_True": risk_label # Cột chân lý để Machine Learning đối chiếu (Agent sẽ tự dự đoán mà không nhìn cờ này)
        })
        
    df = pd.DataFrame(data)
    df.to_csv("sample_data/dataset_5000_audit.csv", index=False, encoding="utf-8-sig")
    print(f"[SUCCESS] Đã sinh xong Dataset Machine Learning: dataset_5000_audit.csv ({len(df)} dòng, 8 features, 4 multi-class labels).")

if __name__ == "__main__":
    generate_mock_data()
