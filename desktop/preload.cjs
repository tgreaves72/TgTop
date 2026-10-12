const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('tgtop',{notify:(title,body)=>ipcRenderer.invoke('notify',title,body),localService:()=>ipcRenderer.invoke('local-service'),connect:url=>ipcRenderer.invoke('connect',url),chatgptSignIn:url=>ipcRenderer.invoke('chatgpt-signin',url)});
