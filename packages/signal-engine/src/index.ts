import type {Candle,Direction,Signal,SetupState} from "@quantedge/shared";
const ema=(a:number[],n:number)=>{if(!a.length)return 0;if(a.length<n)return a.at(-1)??0;const k=2/(n+1);let e=a.slice(0,n).reduce((x,y)=>x+y,0)/n;for(const v of a.slice(n))e=v*k+e*(1-k);return e};
const atr=(c:Candle[],n=14)=>{if(c.length<n+1)return 0;const tr=c.slice(1).map((x,i)=>Math.max(x.high-x.low,Math.abs(x.high-c[i].close),Math.abs(x.low-c[i].close)));return tr.slice(-n).reduce((a,b)=>a+b,0)/Math.min(n,tr.length)};
const slope=(v:number[])=>v.length<4?0:v.at(-1)!-v.at(-4)!;
const fmt=(n:number)=>Number(n.toFixed(8));
export function analyze(symbol:string,candles:Candle[],minConfidence=85):Omit<Signal,"exchange"|"market"|"createdAt">{
 const clean=candles.filter(c=>Number.isFinite(c.close)&&c.high>=c.low&&c.volume>=0);
 if(clean.length<60)return {symbol,direction:"NO_TRADE",setupState:"NO_TRADE",confidence:0,entry:0,stopLoss:0,targets:[],riskReward:0,reasons:["Insufficient clean candle history"],confirmations:[],invalidation:"Need at least 60 valid candles"};
 const closes=clean.map(c=>c.close),last=closes.at(-1)!;const e20=ema(closes,20),e50=ema(closes,50),e200=ema(closes,200),a=atr(clean);
 const recent=clean.slice(-30),prior=clean.slice(-60,-30),high=Math.max(...recent.map(x=>x.high)),low=Math.min(...recent.map(x=>x.low)),priorHigh=Math.max(...prior.map(x=>x.high)),priorLow=Math.min(...prior.map(x=>x.low));
 const avgVol=recent.reduce((s,x)=>s+x.volume,0)/recent.length,volNow=clean.at(-1)!.volume;
 const bullishTrend=last>e20&&e20>e50&&last>e200,bearishTrend=last<e20&&e20<e50&&last<e200;
 const breakoutLong=last>priorHigh&&last>=high*.995,breakoutShort=last<priorLow&&last<=low*1.005,volumeOk=volNow>=avgVol*1.15;
 const momentumLong=slope(closes.slice(-8))>0,momentumShort=slope(closes.slice(-8))<0;
 const range=Math.max(a,last*.004);let direction:Direction="NO_TRADE",setupState:SetupState="FORMING",score=0;
 const confirmations:string[]=[],reasons:string[]=[];
 if(bullishTrend){score+=25;confirmations.push("Trend aligned bullish");reasons.push("Price is above EMA20 and EMA50");}
 if(bearishTrend){score+=25;confirmations.push("Trend aligned bearish");reasons.push("Price is below EMA20 and EMA50");}
 if(breakoutLong){direction="LONG";score+=20;confirmations.push("Breakout trigger confirmed");reasons.push("Price cleared recent range high");}
 else if(breakoutShort){direction="SHORT";score+=20;confirmations.push("Breakdown trigger confirmed");reasons.push("Price cleared recent range low");}
 if(volumeOk){score+=15;confirmations.push("Volume expansion");reasons.push("Volume is above recent average");}
 if((direction==="LONG"&&momentumLong)||(direction==="SHORT"&&momentumShort)){score+=15;confirmations.push("Momentum aligned");}else reasons.push("Momentum confirmation is weak");
 const confidence=Math.min(100,score);
 if(direction!=="NO_TRADE"&&confidence>=minConfidence)setupState="TRIGGERED";else if(direction!=="NO_TRADE"){setupState="FORMING";direction="NO_TRADE";}
 const entry=last,stopLoss=direction==="LONG"?last-Math.max(range*.7,a*1.1):direction==="SHORT"?last+Math.max(range*.7,a*1.1):last,risk=Math.abs(entry-stopLoss);
 const targets=direction==="LONG"?[last+risk,last+risk*2,last+risk*3]:direction==="SHORT"?[last-risk,last-risk*2,last-risk*3]:[];
 const rr=risk?Math.abs((targets[1]??entry)-entry)/risk:0;
 const invalidation=direction==="LONG"?"Close below EMA20 or setup low invalidates":direction==="SHORT"?"Close above EMA20 or setup high invalidates":"No active trade until trigger confirmations align";
 return {symbol,direction,setupState,confidence:fmt(confidence),entry:fmt(entry),stopLoss:fmt(stopLoss),targets:targets.map(fmt),riskReward:fmt(rr),reasons,confirmations,invalidation};
}
