# RR Trader

RR Trader is a production-focused cryptocurrency trading intelligence platform for Binance Spot and Binance Futures.

## Master Architecture

```text
RR TRADER
│
├── Backend
│   ├── FastAPI
│   ├── Binance Client
│   │   ├── Spot
│   │   └── Futures
│   ├── Market Scanner
│   ├── 24-Point Analysis Engine
│   ├── Confidence Engine
│   ├── Trade Engine
│   ├── Risk Engine
│   ├── Signal Memory
│   ├── AI Engine
│   ├── Telegram
│   └── Scheduler
│
├── API
│   ├── /health
│   ├── /markets
│   ├── /search
│   ├── /analyze
│   ├── /scan
│   ├── /signals
│   ├── /trade/*
│   ├── /ai/*
│   └── /dashboard/*
│
└── Dashboard
    ├── Overview
    ├── Trade Opportunities
    ├── Market Search
    ├── Signals
    ├── AI Assistant
    ├── Charts
    ├── Paper Trading
    ├── History / Analytics
    └── Settings
