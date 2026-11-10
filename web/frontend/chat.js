const $ = selector => document.querySelector(selector);
const STORAGE_KEY = 'cs3263.soclaas-chat.v1';
const MAX_CHATS = 30;
let config = null, models = [], busy = false, loadingFiles = false, controller = null, toastTimer;
let promptCategory = 'hard', promptsExpanded = false;
let store = readStore();

function id() { return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`; }
function freshChat(model) { return {id:id(), title:'New chat', created_at:new Date().toISOString(), model, draft:'', attachments:[], messages:[]}; }
function readStore() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.version !== 1 || !Array.isArray(saved.chats)) throw new Error();
    const chats = saved.chats.filter(c => c && typeof c.id === 'string' && typeof c.title === 'string' &&
      (c.system_prompt === undefined || typeof c.system_prompt === 'string' && c.system_prompt.length <= 16000) && Array.isArray(c.messages) &&
      c.messages.length <= 200 && c.messages.every(m => m && ['user','assistant'].includes(m.role) && typeof m.content === 'string' && m.content.length <= 150000));
    for (const chat of chats) {
      for (const message of chat.messages) {
        if (message.role === 'assistant' && message.status === 'streaming') {
          message.status = 'interrupted'; message.error = 'Interrupted when the page closed. Retry this message.';
        }
      }
    }
    if (!chats.length) throw new Error();
    return {version:1, chats:chats.slice(0,MAX_CHATS), active:chats.some(c=>c.id===saved.active)?saved.active:chats[0].id};
  } catch {
    const chat = freshChat(); return {version:1, chats:[chat], active:chat.id};
  }
}
function currentChat() { return store.chats.find(c=>c.id===store.active); }
function selectedModel() {
  const name=currentChat().model || currentChat().settings?.model || config?.model;
  return models.find(m=>m.id===name);
}
function modelLabel(model) { return model?.mode==='embeddings'?'Embeddings':model?.mode==='transcription'?'Audio':model?.vision?'VLM':'LLM'; }
function renderModels() {
  const selected=selectedModel(), filter=$('#model-search').value.toLowerCase();
  $('#model-name').textContent=selected?.id || currentChat().model || config?.model || 'Select model';
  $('#model-kind').hidden=!selected;
  $('#model-kind').textContent=modelLabel(selected);
  $('#model-kind').className=`model-badge${selected?.vision?' vision':''}`;
  const canonical=m=>m?.alias_of || m?.id;
  $('#comparison-note').hidden=!selected || canonical(selected)!==canonical(models.find(m=>m.id===config?.model));
  $('#model-list').replaceChildren();
  for(const model of models.filter(m=>`${m.id} ${m.name} ${modelLabel(m)}`.toLowerCase().includes(filter))) {
    const button=element('button','model-option');button.type='button';button.disabled=busy || model.mode==='unsupported';
    button.dataset.model=model.id;button.setAttribute('aria-pressed',String(model.id===selected?.id));
    const info=element('span','model-option-info');info.append(element('strong','',model.name),element('small','',model.id));
    button.append(info,element('span',`model-badge${model.vision?' vision':''}`,modelLabel(model)),element('span','model-check',model.id===selected?.id?'✓':''));
    button.addEventListener('click',()=>{
      if(busy)return;
      currentChat().model=model.id;persist();$('#model-menu').removeAttribute('open');renderModels();updateControls();
    });
    $('#model-list').append(button);
  }
  $('#model-count').textContent=`${models.length} models`;
}
function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(store)); }
  catch { toast('Browser storage is full or unavailable. Export this conversation to keep a copy.'); }
}
function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(()=>{$('#toast').hidden=true;}, 3800);
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderHistory() {
  $('#history').replaceChildren();
  const chats = store.chats.filter(c=>c.messages.length || c.id===store.active);
  for (const chat of chats) {
    const row = element('div', `history-item${chat.id===store.active?' active':''}`);
    const select = element('button','history-select',chat.title);
    select.title=chat.title; select.disabled=busy;
    if (chat.id===store.active) select.setAttribute('aria-current','page');
    select.addEventListener('click',()=>{
      store.active=chat.id; persist(); renderChat(); closeSidebar();
    });
    const remove = element('button','history-delete','×');
    remove.setAttribute('aria-label',`Delete ${chat.title}`); remove.disabled=busy;
    remove.addEventListener('click',()=>{
      store.chats=store.chats.filter(c=>c.id!==chat.id);
      if (!store.chats.length) store.chats.push(freshChat());
      if (store.active===chat.id) store.active=store.chats[0].id;
      persist(); renderChat(); toast('Conversation deleted from this browser.');
    });
    row.append(select,remove); $('#history').append(row);
  }
}
function inlineMarkdown(parent, text) {
  // Render a deliberately small Markdown subset using text nodes only. Model HTML
  // and links never become executable markup or remote resources.
  const tokens = text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g);
  for (const token of tokens) {
    if (token.startsWith('`') && token.endsWith('`')) parent.append(element('code','',token.slice(1,-1)));
    else if (token.startsWith('**') && token.endsWith('**')) parent.append(element('strong','',token.slice(2,-2)));
    else parent.append(document.createTextNode(token));
  }
}
function tableCells(line) { return line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>c.trim()); }
function renderMarkdown(body, content, streaming=false) {
  body.replaceChildren();
  if (!content) {
    const dots=element('div','thinking'); dots.setAttribute('aria-label','Waiting for the model');
    for(let i=0;i<3;i++) dots.append(element('span')); body.append(dots); return;
  }
  const parts=content.split(/```/);
  parts.forEach((part,index)=>{
    if (index%2) {
      const newline=part.indexOf('\n'), language=newline>=0?part.slice(0,newline):'';
      const figure=element('figure','code-block');
      figure.append(element('figcaption','',language || 'code'));
      const pre=element('pre'); pre.append(element('code','',newline>=0?part.slice(newline+1):part));
      figure.append(pre); body.append(figure); return;
    }
    const lines=part.split('\n');
    let buffer=[];
    const flush=()=>{if(buffer.length){const prose=element('div','prose');inlineMarkdown(prose,buffer.join('\n'));body.append(prose);buffer=[];}};
    for(let i=0;i<lines.length;i++) {
      const line=lines[i], heading=line.match(/^(#{1,3})\s+(.+)/);
      if (heading) {flush();const h=element(`h${heading[1].length+1}`);inlineMarkdown(h,heading[2]);body.append(h);}
      else if (line.includes('|') && i+1<lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i+1]) && tableCells(lines[i+1]).every(c=>/^:?-{3,}:?$/.test(c))) {
        flush();const wrap=element('div','table-scroll'),table=element('table'),head=element('thead'),row=element('tr');
        for(const cell of tableCells(line)){const th=element('th');inlineMarkdown(th,cell);row.append(th);}head.append(row);table.append(head);i+=2;
        const tbody=element('tbody');
        for(;i<lines.length && lines[i].includes('|') && lines[i].trim();i++) {
          const tr=element('tr');for(const cell of tableCells(lines[i])){const td=element('td');inlineMarkdown(td,cell);tr.append(td);}tbody.append(tr);
        }
        i--;table.append(tbody);wrap.append(table);body.append(wrap);
      } else buffer.push(line);
    }
    flush();
  });
  body.parentElement?.classList.toggle('streaming',streaming);
}
function renderMessage(message, index) {
  const article=element('article',`message ${message.role}`);
  article.dataset.index=index;
  if (message.role==='assistant') {
    const heading=element('div','message-heading');heading.append(element('span','assistant-avatar','✳'),document.createTextNode(message.metadata?.model || 'SoCLaaS'));
    article.append(heading);
  }
  const body=element('div','message-body');
  if(message.attachments?.length)article.append(attachmentList(message.attachments));
  if (message.role==='user') body.textContent=message.content;
  else if (message.content || message.status==='streaming') renderMarkdown(body,message.content);
  else if(message.status==='complete')body.textContent='No speech detected.';
  article.append(body);
  if (message.error) article.append(element('div','message-error',message.error));
  if (message.role==='assistant' && message.status!=='streaming') {
    const actions=element('div','message-actions');
    if(message.content) {
      const copy=element('button','','Copy');copy.setAttribute('aria-label','Copy response');
      copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(message.content);toast('Response copied.');}catch{toast('Could not access the clipboard. Select the response text to copy.');}});
      actions.append(copy);
    }
    if(index===currentChat().messages.length-1) {
      const retry=element('button','',message.status==='complete'?'Regenerate':'Retry');retry.disabled=busy;
      retry.addEventListener('click',()=>generate(true));actions.append(retry);
    }
    if(message.metadata) {
      const m=message.metadata, info=[];
      if(Number.isFinite(m.elapsed_seconds)) info.push(`${m.elapsed_seconds.toFixed(1)}s`);
      if(Number.isFinite(m.usage?.total_tokens)) info.push(`${m.usage.total_tokens} tokens`);
      if(m.finish_reason==='length') info.push('Output limit reached');
      actions.append(element('span','run-details',info.join(' · ')));
    }
    article.append(actions);
  }
  return article;
}
function renderChat() {
  const chat=currentChat();
  setRunStatus();
  $('#welcome').hidden=chat.messages.length>0;
  $('#messages').replaceChildren(...chat.messages.map(renderMessage));
  $('#chat-input').value=chat.draft || ''; resizeInput();
  $('#export-chat').disabled=!chat.messages.length;
  renderHistory();renderModels();renderAttachments();updateControls();
}
function attachmentList(files, removable=false) {
  const list=element('div','attachments');
  files.forEach((file,index)=>{
    const item=element('div','attachment');
    if(/^data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$/.test(file.data_url)) {
      const img=element('img');img.src=file.data_url;img.alt=file.name;item.append(img);
    }
    item.append(element('span','attachment-name',file.name));
    if(removable) {
      const remove=element('button','','×');remove.type='button';remove.disabled=busy;remove.setAttribute('aria-label',`Remove ${file.name}`);
      remove.addEventListener('click',()=>{currentChat().attachments.splice(index,1);persist();renderAttachments();updateControls();});item.append(remove);
    }
    list.append(item);
  });return list;
}
function renderAttachments() {
  const files=currentChat().attachments || [];
  $('#attachments').hidden=!files.length;
  $('#attachments').replaceChildren(...attachmentList(files,true).children);
}
function updateControls() {
  const model=selectedModel(),legacyPrompt=!!currentChat().system_prompt,files=currentChat().attachments || [];
  const unavailable=!config?.configured || !model || model.mode==='unsupported';
  const blocked=busy || unavailable || legacyPrompt;
  $('#chat-input').disabled=blocked;
  $('#chat-input').placeholder=model?.mode==='embeddings'?'Text to embed':model?.mode==='transcription'?'Attach an audio file to transcribe':'Message SoCLaaS';
  $('#send').disabled=blocked || loadingFiles || (model?.mode==='transcription'?!files.length:!$('#chat-input').value.trim()&&!files.length);
  $('#send').hidden=busy; $('#stop').hidden=!busy; $('#new-chat').disabled=busy;
  $('#attach-file').hidden=!(model?.vision || model?.mode==='transcription');$('#attach-file').disabled=blocked || loadingFiles;
  $('#attach-file').setAttribute('aria-label',model?.mode==='transcription'?'Attach audio':'Attach image');
  $('#file-input').accept=model?.mode==='transcription'?'.wav,.mp3,.m4a,.mp4,.webm,.ogg,.flac,.aac':'image/png,image/jpeg,image/webp,image/gif';
  $('#file-input').multiple=!!model?.vision;
  $('#refresh-models').disabled=busy;
  document.querySelectorAll('.model-option').forEach(button=>button.disabled=busy || models.find(m=>m.id===button.dataset.model)?.mode==='unsupported');
  setRunStatus(legacyPrompt?'This older chat contains a custom system prompt. Start a new chat to use the simplified interface.':'');
  renderPrompts();
}
function promptIcon(index, soft) {
  const icon=element('span',`prompt-icon ${soft?'gold':['blue','gold','green','violet'][index%4]}`);
  icon.setAttribute('aria-hidden','true');
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  const shapes=['M5 5h14v14H5z M5 10h14 M10 5v14','m5 12 4 4L19 6 M5 5h6 M5 19h14',
    'M6 5h12a2 2 0 0 1 2 2v12H4V7a2 2 0 0 1 2-2Z M8 3v4 M16 3v4 M4 10h16',
    'm12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.4l6.1-.9Z'];
  path.setAttribute('d',shapes[soft?3:index%4]);svg.append(path);icon.append(svg);return icon;
}
function renderPrompts() {
  const cards=[...(config?.prompt_cards || []),...(config?.minor_prompt_cards || [])], filtered=cards.filter(c=>(c.prompt_category||c.strength)===promptCategory);
  const canUse=!!(config?.configured && selectedModel()?.mode==='chat' && !busy && !currentChat().system_prompt);
  const draft=$('#chat-input').value;
  for(const category of ['hard','soft','minor']) {
    const selected=category===promptCategory,tab=$(`#prompt-tab-${category}`);
    tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
    $(`#prompt-${category}-count`).textContent=cards.filter(c=>(c.prompt_category||c.strength)===category).length;
  }
  $('#prompt-cards').setAttribute('aria-labelledby',`prompt-tab-${promptCategory}`);
  $('#prompt-cards').replaceChildren();
  if(!cards.length)$('#prompt-cards').append(element('p','prompts-loading',config?'Planning prompts are unavailable. Retry the connection.':'Loading planning prompts…'));
  for(const [index,card] of (promptsExpanded?filtered:filtered.slice(0,4)).entries()) {
    const added=draft.includes(card.prompt),button=element('button',`prompt-card${added?' added':''}`);button.type='button';
    button.dataset.promptId=card.id;button.disabled=!canUse;button.setAttribute('aria-pressed',String(added));
    const top=element('span','prompt-card-top');top.append(promptIcon(index,card.strength==='soft'),element('span','prompt-add',added?'✓':'＋'));
    button.append(top,element('strong','prompt-title',card.title),element('span','prompt-description',card.description));
    button.addEventListener('click',()=>insertPrompts([card]));$('#prompt-cards').append(button);
  }
  $('#add-all-prompts').disabled=!canUse || !cards.length;
  $('#expand-prompts').hidden=filtered.length<=4;
  $('#expand-prompts').textContent=promptsExpanded?'Show fewer ↑':`Show all ${filtered.length} ${promptCategory==='hard'?'requirements':'preferences'} ↓`;
}
function insertPrompts(cards) {
  if(busy || !config?.configured || selectedModel()?.mode!=='chat' || currentChat().system_prompt)return;
  const input=$('#chat-input'),missing=cards.filter(c=>!input.value.includes(c.prompt));
  if(!missing.length){toast('These prompts are already in your draft.');return;}
  let draft=input.value.trim();
  if(!draft)draft='Plan a standard NUS Computer Science degree starting in AY2026/27. Assume the reference-year course offerings and timetables repeat in future years.';
  for(const category of ['hard','soft','minor']) {
    const selected=missing.filter(c=>(c.prompt_category||c.strength)===category);
    if(selected.length)draft+=`\n\n${category==='hard'?'Requirements':category==='soft'?'Preferences':'Minors'}:\n`+selected.map(c=>`- ${c.prompt}`).join('\n');
  }
  if(draft.length>input.maxLength){toast('Your draft is full. Send it or shorten it before adding more prompts.');return;}
  input.value=draft;currentChat().draft=draft;persist();resizeInput();updateControls();input.focus();
  toast(missing.length===1?'Prompt added to your draft.':'Default requirements and preferences added to your draft.');
}
function setRunStatus(message='') {$('#run-status').textContent=message;$('#run-status').hidden=!message;}
function scrollToEnd(force=false) {
  const area=$('#conversation-scroll');
  if(force || area.scrollHeight-area.scrollTop-area.clientHeight<200) area.scrollTop=area.scrollHeight;
}
function resizeInput() {const input=$('#chat-input');input.style.height='auto';input.style.height=`${Math.min(input.scrollHeight || 30,180)}px`;}
async function loadConfig() {
  try {
    const response=await fetch('/api/chat/config');if(!response.ok)throw new Error();config=await response.json();
    if(config.configured) {
      const result=await fetch('/api/chat/models');if(!result.ok)throw new Error();
      models=(await result.json()).models;
      if(!currentChat().model && !currentChat().settings?.model)currentChat().model=models.find(m=>m.id===config.model)?.id || models.find(m=>m.mode==='chat')?.id;
    }
    $('#connection-error').hidden=config.configured;
    if(!config.configured)$('#connection-error-text').textContent='Set SOCLAAS_API_KEY in .env, then restart the backend.';
  } catch {
    models=[];$('#connection-error').hidden=false;
    $('#connection-error-text').textContent='Could not load SoCLaaS models. Check the backend, your key and connection, then retry.';
  }
  renderModels();updateControls();
}
function requestHistory(messages) {
  // Failed/stopped model output is retained in the export, but never silently
  // treated as a completed answer in subsequent model context.
  const result=[];
  for(let i=0;i<messages.length-1;i++) {
    if(messages[i].role==='user' && messages[i+1]?.role==='assistant' && messages[i+1].status==='complete' &&
        (!messages[i+1].metadata?.mode || messages[i+1].metadata.mode==='chat') && messages[i+1].content) {
      result.push(messageInput(messages[i]),{role:'assistant',content:messages[i+1].content});i++;
    }
  }
  const last=messages[messages.length-1];
  if(last?.role==='user')result.push(messageInput(last));
  return result;
}
function messageInput(message) {
  return {role:message.role,content:message.content,...(message.attachments?.length?{attachments:message.attachments}:{})};
}
async function readStream(response, onEvent) {
  if(!response.body)throw new Error('Streaming is unavailable in this browser.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',doneEvent=false;
  const consume=()=>{
    let end;
    while((end=buffer.indexOf('\n\n'))>=0) {
      const frame=buffer.slice(0,end);buffer=buffer.slice(end+2);
      const lines=frame.split('\n'),kind=lines.find(l=>l.startsWith('event:'))?.slice(6).trim();
      const data=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');
      if(!kind || !data)continue;
      const parsed=JSON.parse(data);
      if(kind==='error') {
        const error=new Error(parsed.message || 'The model request failed.');error.details=parsed;throw error;
      }
      if(kind==='done')doneEvent=true;
      onEvent(kind,parsed);
    }
  };
  try {
    for(;;){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true}).replace(/\r/g,'');consume();}
    buffer+=decoder.decode();consume();
    if(!doneEvent)throw new Error('The connection ended before the response completed. Retry this message.');
  } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
}
async function generate(regenerate=false) {
  const model=selectedModel();
  if(busy || loadingFiles || !config?.configured || !model || currentChat().system_prompt)return;
  const chat=currentChat();
  let userText=$('#chat-input').value.trim();
  let nextMessages=chat.messages.slice();
  if(regenerate) {
    if(nextMessages.at(-1)?.role!=='assistant')return;
    nextMessages=nextMessages.slice(0,-1);
  } else {
    const files=chat.attachments || [];
    if(model.mode==='transcription'&&!files.length){setRunStatus('Attach one audio file to transcribe.');return;}
    if(!userText && !files.length)return;
    if(!userText)userText=model.mode==='transcription'?'Transcribe this audio.':'Describe this image.';
    nextMessages.push({role:'user',content:userText,...(files.length?{attachments:files}:{}),created_at:new Date().toISOString()});
  }
  const payload={model:model.id,messages:model.mode==='chat'?requestHistory(nextMessages):[messageInput(nextMessages.at(-1))]};
  const characters=payload.messages.reduce((n,m)=>n+m.content.length,0);
  if(payload.messages.length>config.max_messages || characters>config.max_characters || new TextEncoder().encode(JSON.stringify(payload)).length>(config.max_request_bytes || 12*1024*1024)-1024) {
    setRunStatus('This conversation is too long for one request. Export it and start a new chat.');return;
  }
  chat.messages=nextMessages;
  if(chat.title==='New chat')chat.title=chat.messages.find(m=>m.role==='user').content.replace(/\s+/g,' ').slice(0,52);
  chat.settings={model:model.id,temperature:config.temperature,max_tokens:config.max_tokens};chat.draft='';chat.attachments=[];
  const reply={role:'assistant',content:'',status:'streaming',created_at:new Date().toISOString(),request:payload};
  chat.messages.push(reply);busy=true;controller=new AbortController();
  setRunStatus();persist();renderChat();scrollToEnd(true);
  try {
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
    if(!response.ok)throw new Error(`Request rejected (HTTP ${response.status}). Check the conversation length and backend configuration.`);
    let lastPaint=0;
    await readStream(response,(kind,data)=>{
      if(kind==='meta')reply.metadata=data;
      if(kind==='delta') {
        reply.content+=data.text;
        if(performance.now()-lastPaint>45) {
          renderMarkdown($('#messages').lastElementChild.querySelector('.message-body'),reply.content,true);
          scrollToEnd();lastPaint=performance.now();
        }
      }
      if(kind==='done') {reply.metadata=data;reply.status='complete';}
    });
  } catch(error) {
    reply.status=error.name==='AbortError'?'interrupted':'error';
    reply.error=error.name==='AbortError'?'Generation stopped. Partial output is excluded from future context.':error.message;
    if(error.details)reply.error_details=error.details;
  } finally {
    busy=false;controller=null;persist();renderChat();scrollToEnd();$('#chat-input').focus();
  }
}
function closeSidebar() {document.body.classList.remove('sidebar-open');$('#sidebar-overlay').hidden=true;$('#open-sidebar').setAttribute('aria-expanded','false');}
$('#new-chat').addEventListener('click',()=>{
  if(busy)return;
  const chat=freshChat(selectedModel()?.id || config?.model);
  if(store.chats.length>=MAX_CHATS){toast('Conversation limit reached. Export and delete an older chat first.');return;}
  store.chats=store.chats.filter(c=>c.messages.length);store.chats.unshift(chat);store.active=chat.id;
  setRunStatus();persist();renderChat();closeSidebar();$('#chat-input').focus();
});
$('#chat-input').addEventListener('input',()=>{currentChat().draft=$('#chat-input').value;resizeInput();updateControls();persist();});
$('#chat-input').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();generate();}
});
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();generate();});
$('#stop').addEventListener('click',()=>controller?.abort());
$('#retry-connection').addEventListener('click',loadConfig);
$('#add-all-prompts').addEventListener('click',()=>insertPrompts(config?.prompt_cards || []));
$('#expand-prompts').addEventListener('click',()=>{promptsExpanded=!promptsExpanded;renderPrompts();});
document.querySelectorAll('[data-prompt-category]').forEach(button=>{
  button.addEventListener('click',()=>{promptCategory=button.dataset.promptCategory;promptsExpanded=false;renderPrompts();});
  button.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const categories=['hard','soft','minor'];promptCategory=event.key==='Home'?'hard':event.key==='End'?'minor':categories[(categories.indexOf(promptCategory)+(event.key==='ArrowRight'?1:2))%3];
    promptsExpanded=false;renderPrompts();$(`#prompt-tab-${promptCategory}`).focus();
  });
});
$('#refresh-models').addEventListener('click',loadConfig);
$('#model-search').addEventListener('input',renderModels);
$('#model-menu summary').addEventListener('click',event=>{if(busy)event.preventDefault();});
document.addEventListener('click',event=>{if(!$('#model-menu').contains(event.target))$('#model-menu').removeAttribute('open');});
$('#attach-file').addEventListener('click',()=>$('#file-input').click());
$('#file-input').addEventListener('change',async()=>{await addFiles([...$('#file-input').files]);$('#file-input').value='';});
$('#chat-input').addEventListener('paste',event=>{
  const files=[...(event.clipboardData?.files || [])];
  if(files.length){event.preventDefault();addFiles(files);}
});
async function addFiles(files) {
  const model=selectedModel(),chat=currentChat();
  if(busy || loadingFiles || !model || (!model.vision && model.mode!=='transcription'))return;
  const existing=chat.attachments || [];
  if(files.length+existing.length>(model.mode==='transcription'?1:4)){toast(model.mode==='transcription'?'Attach one audio file at a time.':'Attach up to four images at a time.');return;}
  loadingFiles=true;updateControls();
  try {
    const additions=[];
    for(const file of files) {
      if(file.size>(config.max_attachment_bytes || 6*1024*1024)){throw new Error('Each file must be 6 MB or smaller.');}
      const extension=file.name.split('.').at(-1).toLowerCase();
      const fallback={wav:'audio/wav',mp3:'audio/mpeg',m4a:'audio/mp4',mp4:'video/mp4',webm:'audio/webm',ogg:'audio/ogg',flac:'audio/flac',aac:'audio/aac'};
      const mime=file.type || fallback[extension];
      if(model.mode==='transcription'?!Object.values(fallback).concat(['audio/x-wav','audio/x-m4a','video/webm','audio/mp3']).includes(mime):!['image/png','image/jpeg','image/webp','image/gif'].includes(mime)) {
        throw new Error(model.mode==='transcription'?'Choose a supported audio file.':'Choose a PNG, JPEG, WebP or GIF image.');
      }
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Could not read this file.'));reader.readAsDataURL(file);});
      additions.push({name:file.name.slice(0,180),data_url:data.replace(/^data:[^;]*;/,`data:${mime};`)});
    }
    const sizeOf=a=>{const encoded=a.data_url.split(',')[1];return encoded.length*3/4-(encoded.length-encoded.replace(/=+$/,'').length);};
    if([...existing,...additions].reduce((n,a)=>n+sizeOf(a),0)>(config.max_attachment_bytes || 6*1024*1024))throw new Error('Combined attachments must be 6 MB or smaller.');
    if(chat.id!==currentChat().id || model.id!==selectedModel()?.id)return;
    chat.attachments=[...existing,...additions];persist();renderAttachments();
  } catch(error){toast(error.message);}
  finally{loadingFiles=false;updateControls();}
}
$('#open-sidebar').addEventListener('click',()=>{document.body.classList.add('sidebar-open');$('#sidebar-overlay').hidden=false;$('#open-sidebar').setAttribute('aria-expanded','true');});
$('#close-sidebar').addEventListener('click',closeSidebar);$('#sidebar-overlay').addEventListener('click',closeSidebar);
document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeSidebar();$('#model-menu').removeAttribute('open');}});
$('#export-chat').addEventListener('click',()=>{
  const chat=currentChat(),data={format:'soclaas-interface-chat',version:2,exported_at:new Date().toISOString(),
    provider:'SoCLaaS',mode:'direct-model',automatic_context:false,chat};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=`soclaas-chat-${chat.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Conversation and experiment metadata exported.');
});
renderChat();loadConfig();
