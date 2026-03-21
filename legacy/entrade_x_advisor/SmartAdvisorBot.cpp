#include "SmartAdvisorBot.h"
#include <iostream>
#include <iomanip>
#include <fstream>
#include <sstream>
#include <filesystem>

namespace fs = std::filesystem;
using namespace std;

SmartAdvisorBot::SmartAdvisorBot(double budget) : baseBudget(budget), isDbConnected(false), giaVonTrungBinh(0), tongSoCCQ(0) {
    connectDatabase();
    if (isDbConnected) autoMigrateDatabase();
}

SmartAdvisorBot::~SmartAdvisorBot() {
    if (isDbConnected) {
        SQLDisconnect(dbc);
        SQLFreeHandle(SQL_HANDLE_DBC, dbc);
        SQLFreeHandle(SQL_HANDLE_ENV, env);
    }
}

void SmartAdvisorBot::setBudget(double budget) {
    baseBudget = budget;
}

void SmartAdvisorBot::connectDatabase() {
    SQLAllocHandle(SQL_HANDLE_ENV, SQL_NULL_HANDLE, &env);
    SQLSetEnvAttr(env, SQL_ATTR_ODBC_VERSION, (void*)SQL_OV_ODBC3, 0);
    SQLAllocHandle(SQL_HANDLE_DBC, env, &dbc);
    SQLWCHAR connStr[] = L"DRIVER={ODBC Driver 17 for SQL Server};SERVER=.\\SQLEXPRESS;Trusted_Connection=yes;";
    SQLWCHAR outStr[1024];
    SQLSMALLINT outLen;
    SQLRETURN ret = SQLDriverConnect(dbc, NULL, connStr, SQL_NTS, outStr, sizeof(outStr) / sizeof(SQLWCHAR), &outLen, SQL_DRIVER_NOPROMPT);
    if (SQL_SUCCEEDED(ret)) {
        isDbConnected = true;
    }
}

void SmartAdvisorBot::executeSQL(string query) {
    if (!isDbConnected) return;
    SQLHSTMT stmt;
    SQLAllocHandle(SQL_HANDLE_STMT, dbc, &stmt);
    SQLExecDirectA(stmt, (SQLCHAR*)query.c_str(), SQL_NTS);
    SQLFreeHandle(SQL_HANDLE_STMT, stmt);
}

void SmartAdvisorBot::autoMigrateDatabase() {
    executeSQL("IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'EntradeX_Advisor') CREATE DATABASE EntradeX_Advisor;");
    executeSQL("USE EntradeX_Advisor;");
    string createTableSQL =
        "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Market_Condition') "
        "CREATE TABLE Market_Condition (LogID INT IDENTITY(1,1) PRIMARY KEY, LogDate DATE DEFAULT GETDATE(), PERatio FLOAT, InterestRate FLOAT); "
        "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Bot_Advice') "
        "CREATE TABLE Bot_Advice (RecID INT IDENTITY(1,1) PRIMARY KEY, LogID INT, Suggested_Action NVARCHAR(100), Volume INT);";
    executeSQL(createTableSQL);
}

void SmartAdvisorBot::docLichSuKhopLenh() {
    int tongKhoiLuong = 0;
    double tongTien = 0;
    int soFileDaDoc = 0;
    if (!fs::exists("LichSuCSV")) {
        fs::create_directory("LichSuCSV");
    }
    for (const auto& entry : fs::directory_iterator("LichSuCSV")) {
        if (entry.path().extension() == ".csv") {
            ifstream file(entry.path());
            if (!file.is_open()) continue;
            string line;
            soFileDaDoc++;
            while (getline(file, line)) {
                stringstream ss(line);
                string dataCell;
                string cot[20];
                int index = 0;
                while (getline(ss, dataCell, ',')) {
                    cot[index] = dataCell;
                    index++;
                }
                if (index >= 7 && cot[2] == "MUA" && cot[3] == "E1VFVN30") {
                    try {
                        int khoiLuong = stoi(cot[5]);
                        double giaKhop = stod(cot[6]);
                        tongKhoiLuong += khoiLuong;
                        tongTien += (khoiLuong * giaKhop);
                    }
                    catch (...) {
                        continue;
                    }
                }
            }
            file.close();
        }
    }
    this->tongSoCCQ = tongKhoiLuong;
    if (this->tongSoCCQ > 0) {
        this->giaVonTrungBinh = tongTien / tongKhoiLuong;
        cout << "=> Da quet thanh cong " << soFileDaDoc << " file lich su giao dich." << endl;
        cout << "=> Tong so ETF dang nam giu: " << this->tongSoCCQ << " ccq" << endl;
        cout << "=> GIA VON TRUNG BINH CUA BAN: " << fixed << setprecision(0) << this->giaVonTrungBinh << " VND" << endl;
    }
    else {
        cout << "=> Chua tim thay lich su MUA E1VFVN30 hoac chua co file CSV." << endl;
    }
}

void SmartAdvisorBot::xacNhanGiaoDichThucTe(int volume, double price) {
    if (!fs::exists("LichSuCSV")) {
        fs::create_directory("LichSuCSV");
    }
    ofstream file("LichSuCSV/GiaoDich_TuDong.csv", ios::app);
    if (file.is_open()) {
        file << "1,TuDong_HomNay,MUA,E1VFVN30,AutoLog," << volume << "," << fixed << setprecision(0) << price << "\n";
        file.close();
        cout << ">> [Cap nhat] Da luu giao dich thuc te vao thu muc 'LichSuCSV'.\n";
    }
}

void SmartAdvisorBot::advise() {
    cout << "\n======================================================\n";
    cout << "       [ ENTRADE X by DNSE - SMART ADVISOR ]          \n";
    cout << "======================================================\n";
    double currentPE = dataFetcher.fetchPE();
    double currentRate = dataFetcher.fetchInterestRate();
    double currentPrice = dataFetcher.fetchE1Price();
    if (this->tongSoCCQ > 0) {
        double giaTriHienTai = this->tongSoCCQ * currentPrice;
        double tongVon = this->tongSoCCQ * this->giaVonTrungBinh;
        double laiLoVal = giaTriHienTai - tongVon;
        double phanTramLaiLo = (laiLoVal / tongVon) * 100;

        cout << "\n------------------------------------------------------\n";
        cout << "          [BAO CAO TAI SAN - PORTFOLIO]               \n";
        cout << "------------------------------------------------------\n";
        cout << " Tong so CCQ dang co : " << this->tongSoCCQ << " E1VFVN30\n";
        cout << " Gia von trung binh  : " << fixed << setprecision(0) << this->giaVonTrungBinh << " VND\n";
        cout << " Gia tri thi truong  : " << giaTriHienTai << " VND\n";
        if (laiLoVal >= 0)
            cout << " Lai/Lo tam tinh     : +" << laiLoVal << " VND (+" << setprecision(2) << phanTramLaiLo << "%)\n";
        else
            cout << " Lai/Lo tam tinh     : " << laiLoVal << " VND (" << setprecision(2) << phanTramLaiLo << "%)\n";

        cout << "------------------------------------------------------\n";
    }
    if (this->giaVonTrungBinh > 0) {
        double tySuatLoiNhuan = ((currentPrice - this->giaVonTrungBinh) / this->giaVonTrungBinh) * 100;
        cout << "\n[Hệ thống] Hieu suat danh muc hien tai: ";
        if (tySuatLoiNhuan > 0) cout << "+" << fixed << setprecision(2) << tySuatLoiNhuan << "% (DANG LAI) \n";
        else cout << fixed << setprecision(2) << tySuatLoiNhuan << "% (DANG LO) \n";
    }
    cout << "\n[Hệ thống] Dang dong bo du lieu vi mo & Giai thuat Smart DCA...\n";
    double moneyToInvest = 0;
    string actionType = "";
    //Logic cốt lõi
    if (currentPE < 11.0 || currentRate > 8.0) {
        cout << ">> TIN HIEU: THI TRUONG GAU (BEAR MARKET) - DINH GIA RE!\n";
        moneyToInvest = baseBudget * 2;
        actionType = "Bat Day X2";
    }
    else if (currentPE >= 11.0 && currentPE <= 15.0) {
        cout << ">> TIN HIEU: THI TRUONG BO (BULL MARKET) - ON DINH.\n";
        moneyToInvest = baseBudget * 0.8;
        actionType = "DCA Tieu Chuan";
    }
    else {
        cout << ">> TIN HIEU: THI TRUONG BONG BONG - CAN PHONG THU.\n";
        moneyToInvest = baseBudget * 0.4;
        actionType = "DCA Phong Thu";
    }
    int volumeToBuy = moneyToInvest / currentPrice;
    double actualCost = volumeToBuy * currentPrice;
    double moneyToSave = baseBudget - actualCost;
    // IN RA GIAO DIỆN BIÊN LAI ĐẶT LỆNH ĐỘC QUYỀN ENTRADE X
    cout << "\n------------------------------------------------------\n";
    cout << "      [PHIEU LENH KHUYEN NGHI - ENTRADE X APP]        \n";
    cout << "------------------------------------------------------\n";
    cout << " Tieu khoan       : Thuong (Duoi 1)\n";
    cout << " Ma chung khoan   : E1VFVN30 (VN30 ETF)\n";
    cout << " Loai lenh        : MUA (Ho tro Khop lenh Lo le)\n";
    cout << " Khoi luong Mua   : " << volumeToBuy << " ccq (chung chi quy)\n";
    cout << " Gia dat (Tam tinh): " << fixed << setprecision(0) << currentPrice << " VND\n";
    cout << " Phi giao dich    : 0 VND (Mien phi tron doi)\n";
    cout << " Thue (Mua)       : 0 VND\n";
    cout << "------------------------------------------------------\n";
    cout << " TONG GIA TRI LENH: " << actualCost << " VND\n";
    if (actualCost < baseBudget) {
        cout << " TIEN DU PHONG    : " << moneyToSave << " VND\n";
        cout << " (=> So tien nay duoc tu dong Sinh lai qua dem tren app)\n";
    }
    else {
        cout << " [!] DCA TANG TOC : Can bo sung them tien tu Quy du phong!\n";
    }
    cout << "======================================================\n";
    cout << "Thao tac tiep theo: Mo app Entrade X -> Tim ma E1VFVN30 -> Nhap so luong -> MUA.\n";
    if (isDbConnected) {
        stringstream ss1;
        ss1 << "INSERT INTO Market_Condition (PERatio, InterestRate) VALUES (" << currentPE << ", " << currentRate << ");";
        executeSQL(ss1.str());
        stringstream ss2;
        ss2 << "DECLARE @lastID INT = IDENT_CURRENT('Market_Condition'); "
            << "INSERT INTO Bot_Advice (LogID, Suggested_Action, Volume) VALUES (@lastID, '" << actionType << "', " << volumeToBuy << ");";
        executeSQL(ss2.str());
        actionHistory.push("DELETE FROM Bot_Advice WHERE RecID = IDENT_CURRENT('Bot_Advice'); "
            "DELETE FROM Market_Condition WHERE LogID = IDENT_CURRENT('Market_Condition');");
        cout << ">> [He thong] Da Dong Bo Auto-Migration vao SQL Server!\n";
    }
}

void SmartAdvisorBot::analyzeHistoryTwoPointers() const {
    cout << "\n--- PHAN TICH CHU KY BANG DSA TWO POINTERS ---\n";
    double peHistory[] = { 18.5, 16.2, 14.0, 11.5, 10.2, 12.0, 14.5, 17.0, 19.2, 15.0 };
    int n = 10;
    int left = 0;
    int maxWindowSize = 0;
    int bestStart = 0, bestEnd = 0;
    cout << "=> Dang quet mang du lieu P/E bang 2 con tro...\n";
    for (int right = 0; right < n; right++) {
        if (peHistory[right] >= 15.0) {
            left = right + 1;
        }
        else {
            if (right - left + 1 > maxWindowSize) {
                maxWindowSize = right - left + 1;
                bestStart = left;
                bestEnd = right;
            }
        }
    }
    if (maxWindowSize > 0) {
        cout << "=> [AI RESULT] Giai doan tich luy ETF tot nhat keo dai " << maxWindowSize << " nam.\n";
        cout << "=> Bien do P/E an toan thu nhat tu " << peHistory[bestStart] << " den " << peHistory[bestEnd] << ".\n";
    }
    else {
        cout << "=> Khong tim thay chu ky an toan nao ro ret!\n";
    }
}

void SmartAdvisorBot::undoLastAction() {
    if (actionHistory.empty()) {
        cout << "\n[!] Khong co hanh dong nao de Hoan tac (Undo).\n";
        return;
    }
    string undoQuery = actionHistory.top();
    executeSQL(undoQuery);
    actionHistory.pop();
    cout << "\n>> [Thanh cong] Da Hoan tac (Undo) xoa lich su giao dich gan nhat khoi Database!\n";
}