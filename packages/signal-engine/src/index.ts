export type SignalDirection="LONG"|"SHORT"|"NO_TRADE";
export interface SignalResult{symbol:string;direction:SignalDirection;confidence:number;reasons:string[];entry?:number;stopLoss?:number;targets?:number[];riskReward?:number;publishable:boolean}
export interface SignalConfig{minConfidence:number;minRiskReward:number}
export function noTrade(symbol:string,reasons:string[]=[]):SignalResult{return{symbol,direction:"NO_TRADE",confidence:0,reasons,publishable:false}}