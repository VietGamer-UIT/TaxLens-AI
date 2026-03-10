#pragma once
#include "MarketDataFetcher.h"

class SmartAdvisorBot {
private:
    double baseBudget;
    MarketDataFetcher dataFetcher;
public:
    SmartAdvisorBot(double budget);
    void advise();
	void docLichSuKhopLenh(); //Hàm đọc lịch sử khớp lệnh từ file (nếu cần thiết)
};