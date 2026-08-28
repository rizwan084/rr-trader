# Strict QuantEdge Roadmap

1. Foundation: monorepo, config, logging, errors, health, Docker, CI.
2. Auth: registration, login, sessions, roles and protected routes.
3. Users: profile, preferences, audit history.
4. Subscriptions: plans, entitlements and limits.
5. Access Keys: encrypted server-side exchange credentials.
6. Payments: provider abstraction, checkout and subscription state.
7. Market Data: normalized Spot/Futures data, REST + WebSocket, caching and rate limits.
8. Exchanges: Binance, Bybit, OKX, Kraken adapters.
9. Signals: multi-factor scanner, confidence framework, LONG/SHORT/NO_TRADE, entry/SL/targets/reasons.
10. Watchlists: symbols, alerts and personalized scanning.
11. Notifications: in-app, email/webhook-ready event model.
12. Workers: scheduled scanning, persistence and notification jobs.
13. Admin: users, plans, keys, signals, jobs, audit and health.

All modules are designed together around this roadmap; no legacy RR Trader implementation is retained as the architecture of record.
