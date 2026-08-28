# QuantEdge

QuantEdge is the complete replacement architecture for RR Trader: a production-oriented crypto market intelligence, scanning, signal and trading workspace.

## Non-negotiable roadmap
Foundation → Auth → Users → Subscriptions → Access Keys → Payments → Market Data → Exchanges → Signals → Watchlists → Notifications → Workers → Admin, with Next.js web, Fastify/WebSocket API, PostgreSQL, Redis and shared packages.

## Exchanges
Binance Spot/Futures first-class; adapter contract also supports Bybit, OKX and Kraken.

## Run
pnpm install
cp .env.example .env
pnpm dev
