// Only private stdio connects this process to TgTop. No HTTP listener or secret logs.
import readline from 'node:readline';
import {Spectrum} from '@spectrum-ts/core';
import {imessage} from '@spectrum-ts/imessage';
const output = process.stdout.write.bind(process.stdout);
for (const method of ['log','info','warn','error','debug']) console[method]=()=>{};
const emit = value => output(JSON.stringify(value)+'\n');
let app;
const input=readline.createInterface({input:process.stdin,terminal:false});
for await (const line of input) {
  let request;
  try {
    request=JSON.parse(line);
    if(request.action==='start') {
      app=await Spectrum({projectId:request.project_id,projectSecret:request.project_secret,
        providers:[imessage.config()],telemetry:false,options:{logLevel:'error'}});
      emit({id:request.id,ok:true});
      (async()=>{for await(const [space,message] of app.messages){
        if(space.type==='dm' && message.direction==='inbound' && message.content.type==='text')
          emit({event:'incoming',guid:message.id,sender:message.sender?.address||message.sender?.id,
            timestamp:message.timestamp.getTime()/1000,text:message.content.text});
      }})().catch(()=>emit({event:'stream_failed'}));
    } else if(request.action==='send') {
      const space=await imessage(app).space.create(request.phone);
      const message=await space.send(request.text);
      if(!message?.id)throw Error();
      emit({id:request.id,ok:true,sid:message.id});
    } else if(request.action==='message') {
      const space=await imessage(app).space.create(request.phone);
      const message=await imessage(app).getMessage(space,request.guid);
      emit({id:request.id,ok:true,delivered:Boolean(message?.isDelivered)});
    } else throw Error();
  } catch {emit({id:request?.id,ok:false});}
}
await app?.stop();
process.exit(0);
