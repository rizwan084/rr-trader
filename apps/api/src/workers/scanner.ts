import {binanceCandles} from "@quantedge/market-data"; import {analyze} from "@quantedge/signal-engine";
export async function scanSymbol(symbol:string){const candles=await binanceCandles(symbol,"futures","15m",200); return analyze(symbol,candles,Number(process.env.MIN_CONFIDENCE||85));}
