import {Pool} from "pg";
import crypto from "node:crypto";
const ADDRESS=(process.env.CRYPTO_BEP20_RECEIVE_ADDRESS||"0x791715b994ba7D176af2630E8f655Ed037dc9999").toLowerCase();
const CONTRACT=(process.env.CRYPTO_USDT_CONTRACT||"0x55d398326f99059fF775485246999027B3197955").toLowerCase();
const RPC=process.env.CRYPTO_BSC_RPC_URL||"https://bsc-dataseed.binance.org";
const CHAIN_ID=56, DECIMALS=18, CONFIRMATIONS=Number(process.env.CRYPTO_CONFIRMATIONS||12);
const TRANSFER_TOPIC="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a7e5a7c6a3";
const memory=new Map<string,any>();const usedTx=new Set<string>();
const pool=process.env.DATABASE_URL?new Pool({connectionString:process.env.DATABASE_URL,ssl:process.env.DATABASE_URL.includes("localhost")?false:{rejectUnauthorized:false}}):null;
const now=()=>new Date();const id=()=>crypto.randomUUID();
const rpc=async(method:string,params:any[])=>{const r=await fetch(RPC,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({jsonrpc:"2.0",id:1,method,params})});if(!r.ok)throw new Error("BSC RPC HTTP "+r.status);const x:any=await r.json();if(x.error)throw new Error(x.error.message||"BSC RPC error");return x.result};
const hex=(n:number)=>"0x"+Math.max(0,n).toString(16);
const normalize=(v:string)=>v.toLowerCase();
async function init(){if(!pool)return;await pool.query(`create table if not exists crypto_invoices(id uuid primary key,user_id uuid,email text,plan_id text not null,network text not null,chain_id int not null,asset text not null,token_contract text not null,receive_address text not null,amount numeric(36,18) not null,status text not null default 'pending',tx_hash text unique,sender_address text,block_number bigint,confirmations int,paid_at timestamptz,expires_at timestamptz not null,created_at timestamptz not null default now(),updated_at timestamptz not null default now())`)}
function planAmount(planId:string){const p=planId==="pro"?Number(process.env.PRO_PRICE_USDT||29):Number(process.env.BASIC_PRICE_USDT||9);return Number.isFinite(p)&&p>0?p:29}
export async function createCryptoInvoice(input:{planId:string;email?:string;userId?:string}){await init();const invoice={id:id(),planId:input.planId, email:input.email||null,userId:input.userId||null,network:"BEP20",chainId:CHAIN_ID,asset:"USDT",tokenContract:CONTRACT,receiveAddress:ADDRESS,amount:planAmount(input.planId),status:"pending",expiresAt:new Date(Date.now()+30*60*1000).toISOString(),createdAt:now().toISOString()};if(pool){await pool.query("insert into crypto_invoices(id,user_id,email,plan_id,network,chain_id,asset,token_contract,receive_address,amount,status,expires_at) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",[invoice.id,input.userId||null,input.email||null,input.planId,"BEP20",56,"USDT",CONTRACT,ADDRESS,invoice.amount,"pending",invoice.expiresAt])}else memory.set(invoice.id,invoice);return invoice}
export async function getCryptoInvoice(invoiceId:string){if(pool){const r=await pool.query("select * from crypto_invoices where id=$1",[invoiceId]);return r.rows[0]||null}return memory.get(invoiceId)||null}
export async function verifyCryptoPayment(invoiceId:string,txHash:string){const invoice:any=await getCryptoInvoice(invoiceId);if(!invoice)throw new Error("INVOICE_NOT_FOUND");if(invoice.status==="paid")return invoice;if(new Date(invoice.expires_at||invoice.expiresAt)<now())throw new Error("INVOICE_EXPIRED");const hash=txHash.trim().toLowerCase();if(!/^0x[a-f0-9]{64}$/.test(hash))throw new Error("INVALID_TX_HASH");if(usedTx.has(hash))throw new Error("TX_ALREADY_USED");
const latestHex:string=await rpc("eth_blockNumber",[]);const latest=parseInt(latestHex,16);const logs:any[]=await rpc("eth_getLogs",[{fromBlock:hex(Math.max(0,latest-10000)),toBlock:"latest",address:CONTRACT,topics:[TRANSFER_TOPIC,null,"0x000000000000000000000000"+ADDRESS.slice(2)]}]);
const log=logs.find(x=>String(x.transactionHash).toLowerCase()===hash);if(!log)throw new Error("PAYMENT_NOT_FOUND");
const block=parseInt(log.blockNumber,16);const conf=Math.max(0,latest-block+1);if(conf<CONFIRMATIONS)throw new Error("WAITING_CONFIRMATIONS:"+conf);
const raw=BigInt(log.data);const expected=BigInt(Math.round(Number(invoice.amount)*1e6))*BigInt(10**12);if(raw<expected)throw new Error("AMOUNT_TOO_LOW");
const sender="0x"+String(log.topics[1]).slice(-40);usedTx.add(hash);
const paid={...invoice,status:"paid",txHash:hash,senderAddress:sender,blockNumber:block,confirmations:conf,paidAt:now().toISOString()};
if(pool){await pool.query("update crypto_invoices set status='paid',tx_hash=$2,sender_address=$3,block_number=$4,confirmations=$5,paid_at=now(),updated_at=now() where id=$1",[invoiceId,hash,sender,block,conf])}else memory.set(invoiceId,paid);return paid}
export function cryptoPaymentConfig(){return {network:"BEP20",chainId:CHAIN_ID,asset:"USDT",receiveAddress:ADDRESS,tokenContract:CONTRACT,confirmations:CONFIRMATIONS}}
