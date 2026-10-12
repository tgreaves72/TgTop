const {app,BrowserWindow,ipcMain,Notification,shell,dialog}=require('electron');
const {spawn}=require('child_process');
const path=require('path');
const fs=require('fs');
const {randomUUID}=require('crypto');
const {LOCAL,serviceUrl,checkService}=require('./connection.cjs');
let server,win,origin='http://127.0.0.1:8765';
// Keep account data and Chromium session cookies stable across installs and launches.
app.setPath('userData',path.join(app.getPath('appData'),'TgTop'));
const primaryInstance=app.requestSingleInstanceLock();
if(!primaryInstance)app.quit();
app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.show();win.focus()}});
app.setAppUserModelId('com.tgtop.desktop');
function isAllowed(url){try{const u=new URL(url);return u.origin===origin}catch{return false}}
function openWindow(){win=new BrowserWindow({width:1440,height:960,minWidth:720,minHeight:600,title:'TgTop',backgroundColor:'#f4f7fc',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});win.removeMenu();win.webContents.setWindowOpenHandler(({url})=>{if(url.startsWith('https://'))shell.openExternal(url);return {action:'deny'}});win.webContents.on('will-navigate',(e,url)=>{if(!isAllowed(url))e.preventDefault()});win.webContents.on('did-fail-load',async(event,code,description,url,isMainFrame)=>{if(!isMainFrame||code===-3||origin===LOCAL)return;const choice=await dialog.showMessageBox(win,{type:'warning',title:'Cloud service unavailable',message:'TgTop could not reach your cloud workspace.',detail:'Your cloud data remains on the server. Check your connection and try again, or open this PC’s separate local workspace.',buttons:['Try again','Use local workspace'],defaultId:0,cancelId:0});if(choice.response===1){const config=path.join(app.getPath('userData'),'connection.json');if(fs.existsSync(config))fs.unlinkSync(config);app.relaunch();app.quit()}else win.loadURL(origin)});win.loadURL(origin)}
app.whenReady().then(async()=>{
 if(!primaryInstance)return;
 const config=path.join(app.getPath('userData'),'connection.json');
 if(fs.existsSync(config)){try{const value=JSON.parse(fs.readFileSync(config,'utf8')).url;origin=serviceUrl(value)}catch{}}
 if(origin==='http://127.0.0.1:8765'){
  const instanceId=randomUUID();
  const cmd=app.isPackaged?path.join(process.resourcesPath,'server','tgtop-server.exe'):'python';
  const args=app.isPackaged?[]:[path.join(__dirname,'..','run.py')];
  server=spawn(cmd,args,{cwd:app.isPackaged?app.getPath('userData'):path.join(__dirname,'..'),windowsHide:true,env:{...process.env,TGTOP_DATA:path.join(app.getPath('home'),'.tgtop','data'),TGTOP_INSTANCE:instanceId,TGTOP_ORIGIN:origin,TGTOP_HOST:'127.0.0.1',TGTOP_PORT:'8765'},stdio:'ignore'});
  let ready=false;
  for(let n=0;n<60;n++){try{const r=await fetch(origin+'/api/status');if(r.ok&&(await r.json()).instance===instanceId){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,250))}
  if(!ready){dialog.showErrorBox('TgTop could not start','Check that port 8765 is available. Development builds require Python and requirements.txt.');app.quit();return}
 }
 ipcMain.handle('notify',(event,title,body)=>{if(!isAllowed(event.senderFrame.url)||typeof title!=='string'||typeof body!=='string')return false;if(!Notification.isSupported())return false;new Notification({title:title.slice(0,100),body:body.slice(0,300)}).show();return true});
 ipcMain.handle('connect',async(event,url)=>{if(!isAllowed(event.senderFrame.url))throw Error('Unauthorized caller');const next=await checkService(url);const pending=config+'.pending';fs.writeFileSync(pending,JSON.stringify({url:next}));fs.renameSync(pending,config);origin=next;await win.loadURL(origin);return true});
 ipcMain.handle('local-service',(event)=>{if(!isAllowed(event.senderFrame.url))throw Error('Unauthorized caller');if(fs.existsSync(config))fs.unlinkSync(config);app.relaunch();app.quit();return true});
 ipcMain.handle('chatgpt-signin',async(event,url)=>{if(!isAllowed(event.senderFrame.url))throw Error('Unauthorized caller');const u=new URL(url);if(u.origin!=='https://auth.openai.com'||u.pathname!=='/api/accounts/authorize')throw Error('Invalid authorization destination');await shell.openExternal(u.href);return true});
 openWindow();
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',()=>{if(server)server.kill()});
