const LOCAL='http://127.0.0.1:8765';
function serviceUrl(value){
 const u=new URL(value);
 if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash||u.pathname!=='/')throw Error('Enter the HTTPS address of your TgTop service, without a path or password.');
 return u.origin;
}
async function checkService(value,fetcher=fetch){
 const url=serviceUrl(value);
 const r=await fetcher(url+'/api/status',{redirect:'error',credentials:'omit',signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw Error('The TgTop service is unavailable. Your current connection has not changed.');
 const status=await r.json();
 if(typeof status.setup!=='boolean'||typeof status.version!=='string'||!['development','live'].includes(status.mode))throw Error('This address did not return a TgTop service.');
 return url;
}
module.exports={LOCAL,serviceUrl,checkService};
