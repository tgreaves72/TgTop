const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const dialog={open:false,innerHTML:'',close(){this.open=false}};
let resolveFetch,jsonReads=0;
const context=vm.createContext({console,FormData,URL,TextEncoder,TextDecoder,MutationObserver:class{observe(){}},
 indexedDB:{open(){return {}}},document:{querySelector(){return dialog},addEventListener(){},body:{classList:{add(){},toggle(){}}}},
 window:{addEventListener(){}},navigator:{},location:{origin:'http://127.0.0.1:8765'},
 localStorage:{getItem(){return null}},setInterval(){},clearInterval(){},setTimeout(){},clearTimeout(){},
 fetch(){return new Promise(resolve=>{resolveFetch=resolve})}});
const source=fs.readFileSync('web/app.js','utf8').split('\n').filter(line=>!line.startsWith('(async()=>')).join('\n');
vm.runInContext('let calendarMonth=null,resumeDocument=null,resumeDirty=false;\n'+source,context);
(async()=>{
 vm.runInContext("resumeDocument={private:'old resume'};chat=[{text:'old private reply'}];queue=[{private:'old edit'}];",context);
 const pending=vm.runInContext("api('/state')",context);
 vm.runInContext('resetAccountView()',context);
 resolveFetch({status:200,ok:true,headers:{get(){return 'application/json'}},json(){jsonReads++;return {private:'old account'}}});
 await assert.rejects(pending,/Account changed/);assert.equal(jsonReads,0);
 assert.equal(vm.runInContext('resumeDocument===null&&chat.length===0&&queue.length===0&&localKey===null',context),true);
 const first=vm.runInContext("cacheUser='tyler';cacheKey('cache')",context);
 const second=vm.runInContext("cacheUser='alex';cacheKey('cache')",context);
 assert.notEqual(first,second);
 console.log('UI account isolation: late responses discarded, private context cleared, offline storage separated.');
})().catch(e=>{console.error(e);process.exitCode=1});


