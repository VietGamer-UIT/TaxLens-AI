#include <iostream>
#include "SmartAdvisorBot.h"

using namespace std;

static void hienThiMenu() {
    cout << "\n======================================================";
    cout << "\n        ENTRADE X ADVISOR V3.0 - SENIOR EDITION       ";
    cout << "\n======================================================";
    cout << "\n [1]. Chay thuat toan Tu van DCA thang nay & Ghi Log SQL";
    cout << "\n [2]. Hoan tac (Undo) quyet dinh vua chay (DSA Stack)";
    cout << "\n [3]. Phan tich Chu ky toi uu (DSA Two Pointers)";
    cout << "\n [0]. Thoat he thong";
    cout << "\n======================================================";
    cout << "\n=> Vui long chon chuc nang (0-3): ";
}

int main() {
    cout << "Khoi dong He chuyen gia Entrade X... Xin chao!\n";
    SmartAdvisorBot myBot(500000);
    int luaChon;
    while (true) {
        hienThiMenu();
        cin >> luaChon;
        system("cls");
        if (luaChon == 1) {
            double budget;
            cout << "\n--- CHUC NANG 1: TU VAN DAU TU ---\n";
            cout << "=> Nhap ngan sach dau tu thang nay (VND): ";
            cin >> budget;
            myBot.setBudget(budget);
            cout << "\n[He thong] Dang quet du lieu lich su giao dich...\n";
            myBot.docLichSuKhopLenh();
            myBot.advise();
        }
        else if (luaChon == 2) {
            cout << "\n--- CHUC NANG 2: HOAN TAC LICH SU ---\n";
            myBot.undoLastAction();
        }
        else if (luaChon == 3) {
            myBot.analyzeHistoryTwoPointers();
        }
        else if (luaChon == 0) {
            cout << "\n[He thong] Dang ngat ket noi CSDL... Tam biet!\n";
            break;
        }
        else {
            cout << "\n[Loi] Lua chon khong hop le!\n";
        }
    }
    return 0;
}