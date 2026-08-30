"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {Activity,ArrowUpRight,CircleDot,RefreshCw,ShieldCheck,Sparkles,TrendingDown,TrendingUp,Zap} from "lucide-react";
const API=process.env.NEXT_PUBLIC_API_URL||"https://rr-trader-1.onrender.com";
const coins=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"];
type Market={symbol:string;last?:number;change24h?:number;volume24h?:number};

export default function Page(){
 const[data,setData]=useState<Market[]>([]),[loading,setLoading]=useState(true),[updated,setUpdated]=useState("");
 async function load(){
  setLoading(true);
  const rows=await Promise.all(coins.map(async s=>{try{const r=await fetch(API+"/api/v1/markets/"+s+"?market=futures",{cache:"no-store"});return await r.json()}catch{return {symbol:s}}}));
  setData(rows);setUpdated(new Date().toLocaleTimeString());setLoading(false);
 }
 useEffect(()=>{load();const id=setInterval(load,30000);return()=>clearInterval(id)},[]);
 const positive=data.filter(x=>(x.change24h||0)>=0).length;
 return <section className="page-content">
  <section className="hero hero-premium"><div><div className="eyebrow-row"><span className="eyebrow">QUANTEDGE / COMMAND CENTER</span><span className="live-dot"><i/> REAL-TIME</span></div><h1>Trade with <em>clarity.</em></h1><p className="hero-copy">One premium workspace for live markets, multi-timeframe confirmation, validated setups and execution-ready intelligence.</p></div><div className="hero-actions"><Link className="button" href="/markets">Explore Markets <ArrowUpRight size={15}/></Link><Link className="primary" href="/scanner"><Zap size={15}/> Run Scanner</Link></div></section>
  <section className="stats">
   <div className="card kpi accent"><div className="kpi-top"><span>ENGINE</span><span className="status-ok">ONLINE</span></div><strong>LIVE</strong><small>Binance market feed connected</small></div>
   <div className="card kpi"><div className="kpi-top"><span>CONFIRMATION</span><span>85%+</span></div><strong>15M / 1H / 4H</strong><small>Higher-timeframe alignment required</small></div>
   <div className="card kpi"><div className="kpi-top"><span>MARKETS</span><span>BINANCE</span></div><strong>SPOT + FUTURES</strong><small>Market mode available per analysis</small></div>
   <div className="card kpi"><div className="kpi-top"><span>RISK ENGINE</span><span>ACTIVE</span></div><strong><ShieldCheck size={19}/> PROTECTED</strong><small>Invalidation and target logic enabled</small></div>
  </section>
  <section className="dashboard-grid">
   <div className="card section-card setup-panel"><div className="section-head"><div><div className="title-with-icon"><Sparkles size={17}/><h2>Active Trade Setups</h2></div><span>Only validated opportunities reach this feed</span></div><Link className="text-link" href="/signals">View signals →</Link></div>
    <div className="setup-empty"><div className="radar"><span/><span/><span/></div><h3>No validated setup right now</h3><p>Scanner is monitoring the market. A trade appears only when structure, momentum and multi-timeframe confirmation align.</p><Link className="primary" href="/scanner">Analyze a Pair</Link></div>
   </div>
   <div className="card section-card"><div className="section-head"><div><h2>Market Pulse</h2><span>Live futures snapshot</span></div><button className="icon-btn small" onClick={load}><RefreshCw size={14}/></button></div>
    <div className="pulse-list">{data.slice(0,5).map(x=><Link className="pulse-row" key={x.symbol} href={"/charts?symbol="+x.symbol}><span className="coin-avatar">{x.symbol[0]}</span><span><b>{x.symbol.replace("USDT","")}</b><small>USDT Perpetual</small></span><strong>{x.last?Number(x.last).toLocaleString(undefined,{maximumFractionDigits:6}):"—"}</strong><b className={(x.change24h||0)>=0?"positive":"negative"}>{x.change24h!=null?(x.change24h>=0?"+":"")+Number(x.change24h).toFixed(2)+"%":"—"}</b></Link>)}</div>
   </div>
  </section>
  <section className="card section-card market-table"><div className="section-head"><div><div className="title-with-icon"><CircleDot size={17}/><h2>Live Market Overview</h2></div><span>{positive} of {data.length||coins.length} tracked pairs positive · Updated {updated||"—"}</span></div><Link className="button" href="/markets">Full Markets</Link></div>
   <div className="table-wrap"><table className="table"><thead><tr><th>Asset</th><th>Last Price</th><th>24h Change</th><th>24h Volume</th><th>Trend</th><th></th></tr></thead><tbody>{data.map(x=><tr key={x.symbol}><td><Link className="coin-link" href={"/charts?symbol="+x.symbol}><span className="coin-dot">{x.symbol[0]}</span><span>{x.symbol.replace("USDT","")} <small>/ USDT</small></span></Link></td><td className="mono">{x.last?Number(x.last).toLocaleString(undefined,{maximumFractionDigits:8}):"—"}</td><td className={(x.change24h||0)>=0?"positive":"negative"}>{x.change24h!=null?(x.change24h>=0?"+":"")+Number(x.change24h).toFixed(2)+"%":"—"}</td><td className="mono">{x.volume24h?Number(x.volume24h).toLocaleString(undefined,{maximumFractionDigits:0}):"—"}</td><td><span className={(x.change24h||0)>=0?"trend up":"trend down"}>{(x.change24h||0)>=0?<TrendingUp size={14}/>:<TrendingDown size={14}/>} {(x.change24h||0)>=0?"Bullish":"Bearish"}</span></td><td><Link className="row-action" href={"/charts?symbol="+x.symbol}>Chart <ArrowUpRight size={14}/></Link></td></tr>)}</tbody></table></div>
  </section>
  {loading&&<div className="loading-line">Refreshing market intelligence…</div>}
 </section>
}