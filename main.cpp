#include <iostream>
#include "SmartAdvisorBot.h"

using namespace std;

int main() {
    double userBudget;
    cout << "\n=> Vui long nhap ngan sach dau tu thang nay (VND): ";
    cin >> userBudget;
    SmartAdvisorBot myBot(userBudget);
    cout << "\n[He thong] Dang quet du lieu lich su giao dich...\n";
    myBot.docLichSuKhopLenh();
    myBot.advise();
    cout << "\n[He thong] Nhan Enter de ket thuc...";
    cin.ignore();
    cin.get();
    return 0;
}