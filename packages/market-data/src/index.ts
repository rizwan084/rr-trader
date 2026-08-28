export type ExchangeName="binance"|"bybit"|"okx"|"kraken";
export interface Candle{openTime:number;open:number;high:number;low:number;close:number;volume:number;closeTime:number}
export interface Ticker{symbol:string;last:number;bid:number;ask:number;volume24h:number;change24h:number}
export interface MarketAdapter{readonly name:ExchangeName;getMarkets():Promise<string[]>;getTicker(symbol:string):Promise<Ticker>;getCandles(symbol:string,interval:string,limit?:number):Promise<Candle[]>;connect?():Promise<void>;disconnect?():Promise<void>}
