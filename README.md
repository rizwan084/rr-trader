# RR Trader

RR Trader is being rebuilt as a production-grade crypto trading intelligence platform.

## Locked architecture

- Backend
  - FastAPI
  - Binance Client (Spot + Futures)
  - Market Scanner
  - 24-Point Analysis Engine
  - Confidence Engine
  - Trade Engine
  - Risk Engine
  - Signal Memory
  - AI Engine
  - Telegram
  - Scheduler
- API
  - `/api/health`
  - `/api/markets`
  - `/api/search`
  - `/api/analyze`
  - `/api/scan`
  - `/api/signals`
  - `/api/trade/*`
  - `/api/ai/*` (later phase)
  - `/api/dashboard/*` (later phase)
- Dashboard
  - Overview
  - Trade Opportunities
  - Market Search
  - Signals
  - AI Assistant
  - Charts
  - Paper Trading
  - History / Analytics
  - Settings

## Core MTF

15m + 1h + 4h.

## Safety

Live trading is disabled during development. Paper trading is the initial execution mode.
