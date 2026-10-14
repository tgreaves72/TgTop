/* Codex-managed ChatGPT connection. Sign-in codes are shown only in this dialog. */
function bindCodex(){
  if(!['assistant','connections'].includes(view))return;
  const heading=document.querySelector('.heading');
  if(!heading||document.getElementById('codexSetup'))return;
  const button=document.createElement('button');button.id='codexSetup';button.textContent='Connect Codex with ChatGPT';button.onclick=()=>codexModal().catch(e=>toast(e.message));heading.appendChild(button);
  const cfg=state.chatgpt?.codex;
  if(view==='assistant'&&cfg?.enabled&&cfg?.connected){const banner=document.querySelector('.banner');if(banner)banner.textContent='Codex · '+(cfg.status==='ready'?'Checked':'Connected')+' · '+(cfg.model||'Choose a model')+'. '+(cfg.last_error||'Only authorized TgTop tools and sources are available.');button.textContent='Manage Codex connection'}
}
async function codexModal(){
  const cfg=await api('/codex');
  let models=[];if(cfg.connected){try{models=await api('/codex/models')}catch{}}
  modal('Codex with your ChatGPT plan',`<p>This separate connection uses the official Codex app-server. It can search authorized project context and create tasks and reminders. It has no shell, browser, or vault access. Your eligible ChatGPT plan covers usage subject to its limits; this connection does not use API billing.</p><p>${cfg.connected?'Connected · '+esc(cfg.model||'Choose a model'):'Not connected'}</p>${cfg.last_error?`<p role="alert">${esc(cfg.last_error)}</p>`:''}${cfg.status==='awaiting_signin'?`<p>Open the official sign-in page and enter this code yourself:</p><p><strong>${esc(cfg.user_code)}</strong></p><a href="https://auth.openai.com/codex/device" target="_blank" rel="noopener noreferrer">Open ChatGPT sign-in</a><p>Only approve the sign-in you just started from TgTop. Never send this code in chat.</p>`:'<button type="button" id="codexContinue">Sign in with ChatGPT</button>'}${models.length?`<label for="codexModel">Codex model catalog</label><select id="codexModel">${models.map(m=>`<option value="${esc(m.slug)}" ${m.slug===cfg.model?'selected':''}>${esc(m.display_name)}</option>`).join('')}</select><button type="button" id="codexSave">Save model</button><p><small>The catalog does not prove access. A completed assistant request verifies the selected model.</small></p>`:''}${cfg.connected?'<button type="button" id="codexDisconnect">Disconnect Codex</button>':''}<p><small>Credentials stay encrypted in your TgTop account. The server decrypts them briefly in private memory-backed storage for Codex to refresh and use them. Authorized source content goes to OpenAI. Existing project data and the previous ChatGPT connection remain saved.</small></p>`,null);
  on('codexContinue',async()=>{await api('/codex/start','POST',{});await codexModal()});
  on('codexSave',async()=>{await api('/codex/model','POST',{model:$('#codexModel').value});$('#dialog').close();await refresh();toast('Codex model saved')});
  on('codexDisconnect',async()=>{await api('/codex/disconnect','POST',{});$('#dialog').close();await refresh();toast('Codex disconnected')});
  if(cfg.status==='awaiting_signin'){
    const dialog=$('#dialog');let busy=false;const deadline=Date.now()+600000;
    const timer=setInterval(async()=>{if(!dialog.open||Date.now()>deadline){clearInterval(timer);return}if(busy)return;busy=true;try{const next=await api('/codex');if(next.status!=='awaiting_signin'){clearInterval(timer);dialog.close();await refresh();await codexModal()}}catch{}finally{busy=false}},2500);
    dialog.addEventListener('close',()=>clearInterval(timer),{once:true});
  }
}
