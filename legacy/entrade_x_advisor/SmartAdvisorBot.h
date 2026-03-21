#pragma once
#include "MarketDataFetcher.h"
#include <windows.h>
#include <sqlext.h>
#include <string>
#include <stack>

class SmartAdvisorBot {
private:
    double baseBudget;
    double giaVonTrungBinh;
    int tongSoCCQ;
    MarketDataFetcher dataFetcher;
    SQLHENV env;
    SQLHDBC dbc;
    bool isDbConnected;
    std::stack<std::string> actionHistory;
    void connectDatabase();
    void executeSQL(std::string query);
    void autoMigrateDatabase();

public:
    SmartAdvisorBot(double budget);
    ~SmartAdvisorBot();
    void setBudget(double budget);
    void advise();
    void docLichSuKhopLenh();
    void undoLastAction();
    void analyzeHistoryTwoPointers() const;
    void xacNhanGiaoDichThucTe(int volume, double price);
};