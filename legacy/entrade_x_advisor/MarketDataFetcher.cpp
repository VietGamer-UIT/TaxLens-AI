#include "MarketDataFetcher.h"
#include <iostream>
using namespace std;

double MarketDataFetcher::fetchPE() {
    double pe;
    cout << "=> 1. Nhap chi so P/E hien tai cua VN-Index (vd: 14.5): ";
    cin >> pe;
    return pe;
}

double MarketDataFetcher::fetchInterestRate() {
    double rate;
    cout << "=> 2. Nhap lai suat huy dong 12 thang cua cac Ngan hang lon (%, vd: 5.0): ";
    cin >> rate;
    return rate;
}

double MarketDataFetcher::fetchE1Price() {
    double price;
    cout << "=> 3. Mo app Entrade X by DNSE, nhap gia E1VFVN30 hien tai (vd: 21500): ";
    cin >> price;
    return price;
}