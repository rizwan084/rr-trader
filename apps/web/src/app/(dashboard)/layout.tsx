"use client";
import Link from "next/link";
import {usePathname} from "next/navigation";
import {ReactNode} from "react";
import {Activity,BarChart3,Bell,CandlestickChart,ChevronRight,LayoutDashboard,Search,Settings,Star,User,Wallet,Wifi,Zap} from "lucide-react";

const nav=[
 ["Overview","/dashboard",LayoutDashboard],["Markets","/markets",BarChart3],["Scanner","/scanner",Search],
 ["Signals","/signals",Activity],["Charts","/charts?symbol=BTCUSDT",CandlestickChart],["Watchlist","/watchlist",Star]
] as const;
const account=[["Premium","/subscription",Wallet],["Exchange","/exchange-connections",Wifi],["Profile","/profile",User],["Settings","/settings",Settings]] as const;

export default function Layout({children}:{children:ReactNode}){
 const path=usePathname();
 return <main className="shell"><div className="app-layout">
  <aside className="sidebar">
   <Link className="brand" href="/dashboard"><span className="brand-mark">Q</span><span><b>QUANTEDGE</b><small>AI TRADING TERMINAL</small></span></Link>
   <div className="nav-label">COMMAND CENTER</div>
   <nav className="side-nav">{nav.map(([label,href,Icon])=><Link key={label} className={path===href.split("?")[0]?"nav-item active":"nav-item"} href={href}><span className="nav-icon"><Icon size={16}/></span><span>{label}</span>{path===href.split("?")[0]&&<ChevronRight size={13} className="nav-arrow"/>}</Link>)}</nav>
   <div className="nav-label">ACCOUNT</div>
   <nav className="side-nav">{account.map(([label,href,Icon])=><Link key={label} className={path===href?"nav-item active":"nav-item"} href={href}><span className="nav-icon"><Icon size={16}/></span><span>{label}</span></Link>)}</nav>
   <div className="sidebar-footer"><span className="premium-chip">PREMIUM</span><strong>Pro workspace</strong><small>Live intelligence enabled</small></div>
  </aside>
  <div className="main">
   <header className="topbar"><div className="mobile-title"><span className="brand-mark mini">Q</span><b>QUANTEDGE</b></div><div className="top-search"><Search size={15}/><span>Search markets, symbols...</span></div><div className="top-actions"><span className="system-live"><i/> LIVE SYSTEM</span><button className="icon-btn"><Bell size={17}/></button><span className="avatar">R</span></div></header>
   <div className="mobile-nav">{nav.slice(0,5).map(([label,href,Icon])=><Link key={label} href={href}><Icon size={17}/><span>{label}</span></Link>)}</div>
   {children}
  </div>
 </div></main>
}