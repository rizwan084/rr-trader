import Fastify from "fastify";
import websocket from "@fastify/websocket";
const app=Fastify({logger:true});
await app.register(websocket);
app.get("/healthz",async()=>({ok:true,service:"quantedge-api",timestamp:new Date().toISOString()}));
app.get("/api/v1/health",async()=>({success:true,status:"online",version:"0.1.0"}));
app.get("/ws",{websocket:true},socket=>socket.send(JSON.stringify({type:"connected",service:"quantedge"})));
app.setErrorHandler((error,_request,reply)=>{app.log.error(error);reply.code(500).send({success:false,error:"INTERNAL_ERROR"});});
await app.listen({host:"0.0.0.0",port:Number(process.env.API_PORT||4000)});
