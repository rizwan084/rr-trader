# QuantEdge

A production-oriented crypto market intelligence platform rebuilt from RR Trader around a clean monorepo.

## Stack
Next.js + TypeScript frontend, Fastify + WebSocket API, PostgreSQL, Redis, exchange adapters, signal engine, workers and admin controls.

## Build order
Foundation → Auth → Market Data → Signal Engine → Realtime → Dashboard → Exchange Connections → Billing → Notifications → Admin → Production.

## Rule
No demo market data in production paths. Exchange credentials stay server-side and are never committed.
