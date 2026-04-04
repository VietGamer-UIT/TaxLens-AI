import os
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_mock_data():
    os.makedirs("sample_data", exist_ok=True)
    
    # --- 1. SINH 1000 DÒNG SỔ CÁI BẰNG PANDAS ---
    data = []
    base_date = datetime(2026, 1, 1)
    
    for i in range(1000):
        # Ngày ngẫu nhiên trong năm 2026
        ngay = base_date + timedelta(days=random.randint(0, 360))
        ngay_str = ngay.strftime("%d/%m/%Y")
        
        # Quyết định dòng này có phải là vi phạm (5% chance)
        is_violation = random.random() < 0.05
        
        if is_violation:
            # Sinh dữ liệu rủi ro: Chi phí cực lớn nhưng thiếu chứng từ (TK 642)
            tai_khoan = "642"
            so_tien = random.randint(50000000, 200000000)
            dien_giai = "Chi phí hoa hồng môi giới (Không hợp lệ)"
            chung_tu = False
        else:
            # Dữ liệu 정상 (Normal)
            tai_khoan = random.choice(["111", "112", "152", "156", "331", "511", "641", "642", "1331"])
            so_tien = random.randint(1000000, 15000000)
            dien_giai = f"Giao dịch hợp lệ {i}"
            chung_tu = True
            
        data.append({
            "NgayGhiSo": ngay_str,
            "DienGiai": dien_giai,
            "TaiKhoan": tai_khoan,
            "SoTien": so_tien,
            "ChungTuHopLe": chung_tu
        })
        
    df = pd.DataFrame(data)
    df.to_csv("sample_data/so_cai_1000_dong.csv", index=False, encoding="utf-8-sig")
    
    # --- 2. SINH 5 FILE XML (2 LỖI) ---
    for i in range(1, 6):
        is_xml_error = (i > 3) # File 4 và 5 bị lỗi
        tien_chua_thue = 20000000
        tien_thue_dung = 2000000
        
        if is_xml_error:
            # Lỗi cố tình: Viết sai tiền thuế (cao hơn thực tế)
            tien_thue = 2500000 
            ghi_chu = "<!-- CẢNH BÁO LỖI: Thuế suất 10% nhưng tiền thuế ghi 2.5tr -->"
        else:
            tien_thue = tien_thue_dung
            ghi_chu = ""
            
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<HDon>
    <DLHDon>
        <NDHDon>
            <TienChuaThue>{tien_chua_thue}</TienChuaThue>
            <ThueSuat>10</ThueSuat>
            {ghi_chu}
            <TienThue>{tien_thue}</TienThue>
        </NDHDon>
    </DLHDon>
</HDon>
"""
        with open(f"sample_data/hoa_don_{i}.xml", "w", encoding="utf-8") as f:
            f.write(xml_content)
            
    print(f"[SUCCESS] Đã sinh thành công so_cai_1000_dong.csv ({len(df)} dòng) và 5 file XML chứa lỗi rải rác.")

if __name__ == "__main__":
    generate_mock_data()
