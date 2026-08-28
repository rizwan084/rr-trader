# QuantEdge Architecture

Web never owns exchange secrets. API owns authentication, authorization and orchestration. Market adapters normalize exchange-specific data. Signal engine is deterministic and receives normalized candles/tickers. Workers schedule scans. WebSocket broadcasts normalized events.

Flow: exchange REST/WS → market-data adapter → cache → scanner → signal-engine → signal repository → event bus → dashboard/notifications.
