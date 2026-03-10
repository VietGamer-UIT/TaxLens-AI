#include "SmartAdvisorBot.h"
#include <iostream>
#include <iomanip>
#include <fstream>
#include <string>
#include <sstream>
#include <filesystem>

namespace fs = std::filesystem;
using namespace std;

SmartAdvisorBot::SmartAdvisorBot(double budget) : baseBudget(budget) {};

void SmartAdvisorBot::docLichSuKhopLenh() {
    int tongKhoiLuong = 0;
    double tongTien = 0;
    int soFileDaDoc = 0;
    for (const auto& entry : fs::directory_iterator(".")) {
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
    if (tongKhoiLuong > 0) {
        cout << "=> Da quet thanh cong " << soFileDaDoc << " file lich su giao dich." << endl;
        double giaVonTrungBinh = tongTien / tongKhoiLuong;
        cout << "=> Tong so ETF dang nam giu: " << tongKhoiLuong << " ccq" << endl;
        cout << "=> GIA VON TRUNG BINH CUA BAN: " << fixed << setprecision(0) << giaVonTrungBinh << " VND" << endl;
    }
    else {
        cout << "=> Chua tim thay lich su MUA E1VFVN30 hoac chua co file CSV." << endl;
    }
}

void SmartAdvisorBot::advise() {
    cout << "\n======================================================\n";
    cout << "       [ ENTRADE X by DNSE - SMART ADVISOR ]          \n";
    cout << "======================================================\n";
    double currentPE = dataFetcher.fetchPE();
    double currentRate = dataFetcher.fetchInterestRate();
    double currentPrice = dataFetcher.fetchE1Price();
    cout << "\n[Hệ thống] Dang dong bo du lieu vi mo & Giai thuat Smart DCA...\n";
    double moneyToInvest = 0;
    //Logic cốt lõi
    if (currentPE < 11.0 || currentRate > 8.0) {
        cout << ">> TIN HIEU: THI TRUONG GAU (BEAR MARKET) - DINH GIA RE!\n";
        moneyToInvest = baseBudget * 2;
    }
    else if (currentPE >= 11.0 && currentPE <= 15.0) {
        cout << ">> TIN HIEU: THI TRUONG BO (BULL MARKET) - ON DINH.\n";
        moneyToInvest = baseBudget * 0.8;
    }
    else {
        cout << ">> TIN HIEU: THI TRUONG BONG BONG - CAN PHONG THU.\n";
        moneyToInvest = baseBudget * 0.4;
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
}