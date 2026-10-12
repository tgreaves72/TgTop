const assert=require('node:assert/strict');
const {serviceUrl,checkService}=require('../desktop/connection.cjs');
(async()=>{
 for(const url of ['http://example.com','https://a:b@example.com','https://example.com/path','https://example.com/?token=secret','https://example.com/#fragment'])assert.throws(()=>serviceUrl(url));
 assert.equal(serviceUrl('https://example.com'),'https://example.com');
 let options;
 assert.equal(await checkService('https://example.com',async(url,o)=>{options=o;assert.equal(url,'https://example.com/api/status');return {ok:true,json:async()=>({setup:false,version:'0.1.0',mode:'live'})}}),'https://example.com');
 assert.equal(options.redirect,'error');assert.equal(options.credentials,'omit');
 await assert.rejects(checkService('https://example.com',async()=>({ok:false})),/unavailable/);
 await assert.rejects(checkService('https://example.com',async()=>({ok:true,json:async()=>({})})),/TgTop service/);
 console.log('Cloud connection checks passed: HTTPS validation, service probe, no credentials, no redirects, failure rejection.');
})().catch(e=>{console.error(e);process.exitCode=1});
