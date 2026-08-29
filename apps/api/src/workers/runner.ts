import {binanceTopUsdtSymbols} from "@quantedge/market-data";import {scanSymbol} from "./scanner.js";
const interval=Number(process.env.AUTO_SCAN_INTERVAL||60000),count=Number(process.env.AUTO_SCAN_COINS||6);
async function tick(){const symbols=await binanceTopUsdtSymbols("futures",Math.max(count,10));for(const symbol of symbols.slice(0,count)){try{const s=await scanSymbol(symbol,"futures");if(s.direction!=="NO_TRADE"||s.setupState==="FORMING")console.log(JSON.stringify({type:"signal_candidate",symbol,...s}))}catch(e){console.error("scan failed",symbol,e)}}}
async function main(){await tick();setInterval(()=>tick().catch(e=>console.error("scanner cycle failed",e)),interval)}
main().catch(e=>{console.error(e);process.exit(1)})