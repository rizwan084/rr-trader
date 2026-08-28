import Fastify from "fastify"; import websocket from "@fastify/websocket"; import {binanceCandles,binanceTicker} from "@quantedge/market-data"; import {analyze} from "@quantedge/signal-engine";
const app=Fastify({logger:true}); await app.register(websocket);
app.get("/healthz",async()=>({ok:true,service:"quantedge-api",time:new Date().toISOString()}));
app.get("/api/v1/markets/:symbol",async(req:any)=>{const market=req.query?.market==="spot"?"spot":"futures"; return binanceTicker(req.params.symbol.toUpperCase(),market)});
app.get("/api/v1/signals/:symbol",async(req:any)=>{const market=req.query?.market==="spot"?"spot":"futures"; const candles=await binanceCandles(req.params.symbol.toUpperCase(),market,req.query?.interval||"15m",200); return analyze(req.params.symbol.toUpperCase(),candles,Number(process.env.MIN_CONFIDENCE||85));});
app.get("/api/v1/candles/:symbol",async(req:any)=>{const market=req.query?.market==="spot"?"spot":"futures"; return binanceCandles(req.params.symbol.toUpperCase(),market,req.query?.interval||"15m",Math.min(1000,Number(req.query?.limit||200)))});
app.get("/ws",{websocket:true},socket=>socket.send(JSON.stringify({type:"connected",timestamp:Date.now()})));
app.setErrorHandler((e,_q,r)=>{app.log.error(e);r.code(500).send({success:false,error:"INTERNAL_ERROR",message:e.message})}); await app.listen({host:"0.0.0.0",port:Number(process.env.API_PORT||4000)});
