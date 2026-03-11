# 📈 Smart Advisor Bot - Tối ưu hóa đầu tư VN30 (Entrade X by DNSE)

![C++](https://img.shields.io/badge/C++-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![SQL Server](https://img.shields.io/badge/SQL_Server-CC292B?style=for-the-badge&logo=microsoft-sql-server&logoColor=white)
![Visual Studio](https://img.shields.io/badge/Visual_Studio-5C2D91?style=for-the-badge&logo=visual-studio&logoColor=white)
![Status](https://img.shields.io/badge/Status-Completed-brightgreen?style=for-the-badge)

## 💡 Giới thiệu dự án
Đây là một **Hệ chuyên gia tư vấn đầu tư (Rule-based Expert System)** được thiết kế độc quyền cho thao tác giao dịch trên ứng dụng **Entrade X by DNSE**. 

Dự án này giải quyết bài toán cá nhân của mình: Tối ưu hóa lợi nhuận cho chiến lược đầu tư thụ động (DCA) vào chứng chỉ quỹ ETF mô phỏng chỉ số VN30 (E1VFVN30). Thay vì trung bình giá mù quáng, Bot sẽ phân tích vĩ mô để hướng dẫn mình cách đi tiền thông minh nhất.

> 🔥 **Bản cập nhật V3.0 (SENIOR EDITION):** Nâng cấp toàn diện với giao diện Menu tương tác, tích hợp **SQL Server** để lưu trữ nhật ký tự động. Đặc biệt, dự án áp dụng trực tiếp Cấu trúc dữ liệu & Thuật toán (**DSA**): Dùng **Stack** để xây dựng tính năng Hoàn tác (Undo) và tuyệt kỹ **Two Pointers** để phân tích chu kỳ tích lũy tối ưu dài hạn.

> **🤖 Vibe Coding & AI Collaboration:** > Dự án này được phát triển theo phong cách **Vibe Coding**. Mình (với kiến thức của một sinh viên CNTT năm nhất) chịu trách nhiệm thiết kế logic hệ thống, luật đầu tư (Smart DCA), và luồng UI/UX. Toàn bộ mã nguồn C++, kiến trúc Lập trình hướng đối tượng (OOP), Cấu trúc dữ liệu và kiến thức tài chính vĩ mô được hiện thực hóa với sự trợ giúp đắc lực của **Google Gemini**.

## 🧠 Tính năng cốt lõi (V3.0)

### 1. Cơ chế tư vấn (Smart DCA Logic) & Quét CSV
Hệ thống sử dụng P/E của VN-Index và Lãi suất ngân hàng để tự động phân bổ tỷ trọng vốn:
- 🟢 **Thị trường bò (Bull Market) - Ổn định (11 <= P/E <= 15):** Khuyên giải ngân 80% ngân sách.
- 🟡 **Thị trường bong bóng (Bubble) - Hưng phấn (P/E > 15):** Khuyên chỉ giải ngân 40%, phòng thủ.
- 🔴 **Thị trường gấu (Bear Market) - Hoảng loạn (P/E < 11 hoặc Lãi suất > 8%):** Bắt đáy kịch kim (x2 ngân sách).
*Bot tự động đọc file `.csv` xuất từ Entrade X để tính toán Giá vốn trung bình và số lượng CCQ đang nắm giữ, giúp lời khuyên bám sát thực tế.*

### 2. Quản lý Lịch sử bằng SQL Server
Thay vì ghi ra file text đơn thuần, mọi điều kiện thị trường và lời khuyên của Bot đều được lưu trữ trực tiếp vào CSDL SQL Server (bảng `Market_Condition` và `Bot_Advice`) thông qua kết nối ODBC C++, sẵn sàng cho việc query và thống kê sau này.

### 3. Thực chiến Cấu trúc dữ liệu & Thuật toán (DSA)
- **Hoàn tác quyết định (Undo with Stack):** Lưu vết các thao tác của người dùng vào `std::stack`. Nếu chọn sai, có thể dễ dàng quay lui (pop) trạng thái trước đó.
- **Phân tích chu kỳ tối ưu (Two Pointers):** Quét mảng dữ liệu P/E lịch sử bằng 2 con trỏ (Left, Right) để tìm ra "cửa sổ" (Window) thời gian gom hàng an toàn dài nhất (P/E liên tục duy trì dưới 15).

## 🏗️ Kiến trúc Hệ thống
- **OOP:** `MarketDataFetcher` (Lấy dữ liệu vĩ mô & giá), `SmartAdvisorBot` (Não bộ xử lý logic, kết nối DB, thực thi thuật toán).
- **DBMS:** Cơ sở dữ liệu quan hệ SQL Server.

## ⚙️ Hướng dẫn cài đặt & Chạy dự án
### Bước 1: Khởi tạo Cơ sở dữ liệu
1. Mở **SQL Server Management Studio (SSMS)**.
2. Mở file `EntradeX-Advisor.sql` đính kèm trong thư mục.
3. Bấm `Execute` để chạy script. Script sẽ tự tạo Database `EntradeX_Advisor` và 2 bảng liên quan.

### Bước 2: Chuẩn bị dữ liệu lịch sử Entrade X (Tùy chọn)
1. Xuất file lịch sử khớp lệnh từ Entrade X (dạng `.xlsx`), lưu lại (Save As) dưới định dạng **CSV (Comma delimited) (*.csv)**.
2. **QUAN TRỌNG:** Mở file CSV, đổi định dạng cột Khối lượng/Giá khớp về Number, xóa bỏ dấu phẩy ngăn cách hàng nghìn (VD: `36,430` $\rightarrow$ `36430`).
3. Dán các file `.csv` vào chung thư mục chứa file `main.cpp`. *(Lưu ý: `.gitignore` đã chặn upload file CSV, dữ liệu tài chính của bạn hoàn toàn bảo mật tại máy).*

### Bước 3: Build & Run
1. Đảm bảo máy đã cài đặt **ODBC Driver 17 for SQL Server**.
2. Clone dự án, mở file `EntradeX-Advisor.slnx` bằng Visual Studio.
3. Chỉnh sửa chuỗi kết nối (Connection String) trong file `SmartAdvisorBot.cpp` nếu Tên Server của bạn khác với `.\SQLEXPRESS`.
4. Bấm `F5` chạy chương trình và trải nghiệm qua Menu Tương tác!

---
*Developed by Đoàn Hoàng Việt (Việt Gamer) - Sinh viên UIT (Trường đại học Công nghệ Thông tin - ĐHQG TP.HCM).*
