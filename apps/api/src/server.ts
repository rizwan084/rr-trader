import Fastify from "fastify";
import websocket from "@fastify/websocket";
import { binanceCandles, binanceTicker } from "@quantedge/market-data";
import { analyze } from "@quantedge/signal-engine";

const app = Fastify({ logger: true });

async function start() {
  await app.register(websocket);

  app.get("/healthz", async () => ({
    ok: true,
    service: "quantedge-api",
    time: new Date().toISOString()
  }));

  app.get("/api/v1/markets/:symbol", async (req: any) => {
    const market = req.query?.market === "spot" ? "spot" : "futures";
    return binanceTicker(req.params.symbol.toUpperCase(), market);
  });

  app.get("/api/v1/signals/:symbol", async (req: any) => {
    const symbol = req.params.symbol.toUpperCase();
    const market = req.query?.market === "spot" ? "spot" : "futures";
    const interval = req.query?.interval || "15m";
    const candles = await binanceCandles(symbol, market, interval, 200);
    return analyze(symbol, candles, Number(process.env.MIN_CONFIDENCE || 85));
  });

  app.get("/api/v1/candles/:symbol", async (req: any) => {
    const market = req.query?.market === "spot" ? "spot" : "futures";
    const interval = req.query?.interval || "15m";
    const limit = Math.min(1000, Number(req.query?.limit || 200));
    return binanceCandles(req.params.symbol.toUpperCase(), market, interval, limit);
  });

  app.get("/ws", { websocket: true }, (socket) => {
    socket.send(JSON.stringify({ type: "connected", timestamp: Date.now() }));
  });

  app.setErrorHandler((error: unknown, _request, reply) => {
    app.log.error(error);
    const message = error instanceof Error ? error.message : "Unknown server error";
    reply.code(500).send({
      success: false,
      error: "INTERNAL_ERROR",
      message
    });
  });

  await app.listen({
    host: "0.0.0.0",
    port: Number(process.env.API_PORT || process.env.PORT || 4000)
  });
}

start().catch((error: unknown) => {
  app.log.error(error);
  process.exit(1);
});
