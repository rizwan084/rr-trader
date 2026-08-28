# Architecture

apps/web is the client. apps/api owns HTTP/WebSocket APIs and orchestration. packages/market-data normalizes exchange data. packages/signal-engine evaluates market conditions. packages/shared owns contracts.

Data flow: Exchange → adapter → normalized market data → scanner → signal engine → persisted signal → WebSocket event → dashboard/notification.

No UI component talks directly to exchange secrets. No signal is publishable unless it passes the configured confidence and validation rules.
