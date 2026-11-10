const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
const html=fs.readFileSync('frontend/chat.html','utf8');
const script=fs.readFileSync('frontend/chat.js','utf8');
const config={model:'same-model',configured:true,provider:'SoCLaaS',temperature:0,max_tokens:3500,max_messages:61,max_characters:80000,
  prompt_cards:[
    {id:'units',title:'Complete at least 160 units',description:'Minimum total units.',strength:'hard',prompt:'Complete at least 160 units. Minimum total units.'},
    {id:'core',title:'Complete foundation courses',description:'CS1101S and CS1231S.',strength:'hard',prompt:'Complete foundation courses. Required courses: CS1101S, CS1231S.'},
    {id:'duration',title:'Prefer finishing within 8 semesters',description:'A four-year plan.',strength:'soft',prompt:'Prefer finishing within 8 semesters. A four-year plan.'},
  ],minor_prompt_cards:[{id:'minor_mathematics',title:'Complete a Mathematics minor',description:'20 units and sharing caps.',strength:'hard',prompt_category:'minor',prompt:'Include a Mathematics minor with at least 12 distinct units.'},
    {id:'minor_quantitative_finance',title:'Complete a Quantitative Finance minor',description:'QF course groups.',strength:'hard',prompt_category:'minor',prompt:'Include a Quantitative Finance minor.'}]};
const models=[{id:'same-model',name:'Default model',mode:'chat',vision:false},
  {id:'vision-model',name:'Vision model',mode:'chat',vision:true},
  {id:'embedding-model',name:'Embeddings',mode:'embeddings',vision:false},
  {id:'audio-model',name:'Whisper',mode:'transcription',vision:false}];
const frame=(kind,data)=>`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`;
function stream(text='Hello 世界',extra={}) {
  const data=frame('meta',config)+frame('delta',{text})+frame('done',{...config,elapsed_seconds:1.25,finish_reason:'stop',usage:{total_tokens:20},...extra});
  const bytes=new TextEncoder().encode(data);
  return {ok:true,body:new ReadableStream({start(controller){
    // Split multibyte UTF-8 as well as event boundaries.
    for(let offset=0;offset<bytes.length;offset+=7)controller.enqueue(bytes.slice(offset,offset+7));controller.close();
  }})};
}
async function until(predicate) {
  for(let i=0;i<120;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,5));}
  throw new Error('Expected chat state did not appear');
}
async function setup(handler, saved) {
  const dom=new JSDOM(html,{url:'http://localhost:8000/chat',runScripts:'outside-only'}),{window}=dom,calls=[],downloads=[];
  window.TextEncoder=TextEncoder;window.TextDecoder=TextDecoder;
  window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
  window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
  window.URL.createObjectURL=blob=>{downloads.push(blob);return 'blob:test';};window.URL.revokeObjectURL=()=>{};
  window.HTMLAnchorElement.prototype.click=function(){};
  window.fetch=async(path,options)=>{
    const body=options?.body?JSON.parse(options.body):undefined;calls.push({path,body});
    if(path==='/api/chat/config')return {ok:true,json:async()=>config};
    if(path==='/api/chat/models')return {ok:true,json:async()=>({models})};
    return handler?handler(body,options):stream();
  };
  if(saved)window.localStorage.setItem('cs3263.soclaas-chat.v1',JSON.stringify(saved));
  window.eval(script);await until(()=>window.document.querySelector('#model-name').textContent===config.model);
  const click=s=>window.document.querySelector(s).click();
  const submit=async text=>{
    const input=window.document.querySelector('#chat-input');input.value=text;input.dispatchEvent(new window.Event('input'));
    window.document.querySelector('#chat-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    await until(()=>!window.document.querySelector('#stop').hidden);
    await until(()=>window.document.querySelector('#stop').hidden);
  };
  const state=()=>JSON.parse(window.localStorage.getItem('cs3263.soclaas-chat.v1'));
  return {dom,window,document:window.document,calls,click,submit,state,downloads};
}
test('streams UTF-8 and forwards exact multi-turn conversation without planner context',async()=>{
  const t=await setup();try {
    await t.submit('请帮我规划课程');
    assert.match(t.document.querySelector('#messages').textContent,/Hello 世界/);
    await t.submit('What comes next?');
    const requests=t.calls.filter(c=>c.path==='/api/chat');
    assert.deepEqual(requests[0].body,{model:'same-model',messages:[{role:'user',content:'请帮我规划课程'}]});
    assert.deepEqual(requests[1].body.messages,[{role:'user',content:'请帮我规划课程'},{role:'assistant',content:'Hello 世界'},{role:'user',content:'What comes next?'}]);
    assert.ok(t.document.querySelector('#welcome').hidden);
    assert.equal(t.state().chats[0].messages[3].metadata.usage.total_tokens,20);
    assert.match(t.document.querySelector('.run-details').textContent,/1.3s/);
    assert.ok(!t.calls.some(c=>['/api/config','/api/plans','/api/preferences'].includes(c.path)));
  } finally {t.dom.window.close();}
});
test('simplified interface has no settings or system prompt and exports exact requests',async()=>{
  const t=await setup();try {
    assert.equal(t.document.querySelector('#settings-button'),null);
    assert.equal(t.document.querySelector('#prompt-button'),null);
    assert.match(t.document.querySelector('.wordmark').textContent,/SoCLaaS Interface/);
    assert.match(t.document.querySelector('#welcome').textContent,/LLM or CSP/);
    await t.submit('Make a plan');
    assert.equal(t.calls.find(c=>c.path==='/api/chat').body.system_prompt,undefined);
    t.click('#export-chat');
    assert.equal(t.downloads.length,1);
    const json=await new Promise(resolve=>{const reader=new t.window.FileReader();reader.onload=()=>resolve(reader.result);reader.readAsText(t.downloads[0]);});
    const exported=JSON.parse(json);assert.equal(exported.automatic_context,false);
    assert.equal(exported.chat.system_prompt,undefined);
    assert.deepEqual(exported.chat.messages[1].request,t.calls.find(c=>c.path==='/api/chat').body);
    assert.equal(exported.chat.messages[1].metadata.model,'same-model');
  } finally {t.dom.window.close();}
});
test('failed or incomplete output stays visible but is excluded from future context',async()=>{
  let count=0;
  const t=await setup(()=>++count===1?{ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(frame('delta',{text:'partial'})));c.close();}})}:stream('complete'));
  try {
    await t.submit('First prompt');assert.match(t.document.querySelector('.message-error').textContent,/ended/);
    assert.equal(t.state().chats[0].messages[1].status,'error');
    await t.submit('Second prompt');
    assert.deepEqual(t.calls.filter(c=>c.path==='/api/chat')[1].body.messages,[{role:'user',content:'Second prompt'}]);
    assert.match(t.document.querySelector('#messages').textContent,/partial/);
  } finally {t.dom.window.close();}
});
test('stop cancels the request and retry uses the original user message once',async()=>{
  let count=0;
  const t=await setup((body,options)=>{
    if(++count>1)return stream('Retried');
    return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
  });
  try {
    t.document.querySelector('#chat-input').value='Stop me';
    t.document.querySelector('#chat-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    await until(()=>!t.document.querySelector('#stop').hidden);t.click('#stop');
    await until(()=>t.document.querySelector('#stop').hidden);
    assert.equal(t.state().chats[0].messages[1].status,'interrupted');
    const retry=[...t.document.querySelectorAll('.message-actions button')].find(b=>b.textContent==='Retry');retry.click();
    await until(()=>t.calls.filter(c=>c.path==='/api/chat').length===2&&t.document.querySelector('#stop').hidden);
    assert.deepEqual(t.calls.filter(c=>c.path==='/api/chat')[1].body.messages,[{role:'user',content:'Stop me'}]);
    assert.equal(t.state().chats[0].messages.length,2);
  } finally {t.dom.window.close();}
});
test('model output is safe text; tables and code render without executing HTML',async()=>{
  const t=await setup(()=>stream('# Plan\n**Bold** <img src=x onerror="alert(1)">\n\n| Course | Semester |\n| --- | --- |\n| CS1231S | 1 |\n\n```html\n<script>alert(1)</script>\n```'));
  try {
    await t.submit('Test formatting');
    assert.equal(t.document.querySelectorAll('.message-body img,.message-body script').length,0);
    assert.equal(t.document.querySelectorAll('.message-body table tbody tr').length,1);
    assert.match(t.document.querySelector('.code-block').textContent,/<script>/);
    assert.equal(t.document.querySelector('.message-body strong').textContent,'Bold');
  } finally {t.dom.window.close();}
});
test('new chat, history navigation and deleting current conversation preserve other chats',async()=>{
  const t=await setup();try {
    await t.submit('First conversation');t.click('#new-chat');await t.submit('Second conversation');
    assert.equal(t.document.querySelectorAll('.history-item').length,2);
    [...t.document.querySelectorAll('.history-select')].find(b=>b.textContent==='First conversation').click();
    assert.match(t.document.querySelector('#messages').textContent,/First conversation/);
    t.click('.history-item.active .history-delete');
    assert.equal(t.state().chats.length,1);assert.match(t.document.querySelector('#messages').textContent,/Second conversation/);
  } finally {t.dom.window.close();}
});
test('selecting another model immediately changes the request and comparison label',async()=>{
  const t=await setup();try {
    await until(()=>t.document.querySelectorAll('.model-option').length===4);
    assert.equal(t.document.querySelector('#comparison-note').hidden,false);
    t.click('[data-model="vision-model"]');
    assert.equal(t.document.querySelector('#model-name').textContent,'vision-model');
    assert.equal(t.document.querySelector('#model-kind').textContent,'VLM');
    assert.ok(t.document.querySelector('#comparison-note').hidden);
    await t.submit('Fresh experiment');assert.equal(t.calls.find(c=>c.path==='/api/chat').body.model,'vision-model');
    t.click('[data-model="same-model"]');await t.submit('Back to default');
    assert.equal(t.calls.filter(c=>c.path==='/api/chat')[1].body.model,'same-model');
    assert.equal(t.document.querySelector('#comparison-note').hidden,false);
  } finally {t.dom.window.close();}
});
test('reloading an unfinished run marks it interrupted and preserves its draft',async()=>{
  const saved={version:1,active:'run',chats:[{id:'run',title:'Interrupted run',system_prompt:'',draft:'My next question',messages:[
    {role:'user',content:'original'}, {role:'assistant',content:'partial',status:'streaming'}]}]};
  const t=await setup(undefined,saved);try {
    assert.equal(t.document.querySelector('#chat-input').value,'My next question');
    assert.match(t.document.querySelector('.message-error').textContent,/page closed/);
    await t.submit('New question');
    assert.deepEqual(t.calls.find(c=>c.path==='/api/chat').body.messages,[{role:'user',content:'New question'}]);
  } finally {t.dom.window.close();}
});
test('legacy custom prompts cannot silently apply after settings UI is removed',async()=>{
  const saved={version:1,active:'old',chats:[{id:'old',title:'Old run',system_prompt:'Secret old instructions',messages:[]}]};
  const t=await setup(undefined,saved);try {
    assert.ok(t.document.querySelector('#chat-input').disabled);
    assert.match(t.document.querySelector('#run-status').textContent,/custom system prompt/);
    t.click('#new-chat');await t.submit('Clean prompt');
    assert.equal(t.calls.find(c=>c.path==='/api/chat').body.system_prompt,undefined);
  } finally {t.dom.window.close();}
});
test('image attachment previews and travels with the selected VLM request',async()=>{
  const t=await setup();try {
    await until(()=>t.document.querySelectorAll('.model-option').length===4);
    t.click('[data-model="vision-model"]');
    const file=new t.window.File(['image-bytes'],'plan.png',{type:'image/png'});
    Object.defineProperty(t.document.querySelector('#file-input'),'files',{value:[file],configurable:true});
    t.document.querySelector('#file-input').dispatchEvent(new t.window.Event('change'));
    await until(()=>t.document.querySelector('#attachments img'));
    await t.submit('Describe my plan');
    const request=t.calls.find(c=>c.path==='/api/chat').body;
    assert.equal(request.model,'vision-model');
    assert.match(request.messages[0].attachments[0].data_url,/^data:image\/png;base64,/);
    assert.equal(t.document.querySelectorAll('#messages .attachments img').length,1);
    assert.ok(t.document.querySelector('#attachments').hidden);
  } finally {t.dom.window.close();}
});
test('embedding selection sends only current input instead of chat history',async()=>{
  const t=await setup();try {
    await t.submit('Earlier chat');t.click('[data-model="embedding-model"]');
    await t.submit('Text to embed');
    const request=t.calls.filter(c=>c.path==='/api/chat')[1].body;
    assert.deepEqual(request,{model:'embedding-model',messages:[{role:'user',content:'Text to embed'}]});
    assert.ok(t.document.querySelector('#attach-file').hidden);
  } finally {t.dom.window.close();}
});
test('audio models accept an audio attachment with no typed prompt',async()=>{
  const t=await setup();try {
    await until(()=>t.document.querySelectorAll('.model-option').length===4);
    t.click('[data-model="audio-model"]');
    const file=new t.window.File(['audio-bytes'],'recording.wav',{type:'audio/wav'});
    Object.defineProperty(t.document.querySelector('#file-input'),'files',{value:[file],configurable:true});
    t.document.querySelector('#file-input').dispatchEvent(new t.window.Event('change'));
    await until(()=>t.document.querySelector('#attachments .attachment'));
    await t.submit('');
    const request=t.calls.find(c=>c.path==='/api/chat').body;
    assert.equal(request.model,'audio-model');
    assert.equal(request.messages[0].content,'Transcribe this audio.');
    assert.match(request.messages[0].attachments[0].data_url,/^data:audio\/wav;base64,/);
  } finally {t.dom.window.close();}
});
test('gateway failure details remain visible and are preserved in the exported run',async()=>{
  const details={message:'same-model: The model service is temporarily unavailable on SoCLaaS (HTTP 503). Retry later.',http_status:503,code:'model_backend_unavailable',model:'same-model',retryable:true};
  const t=await setup(()=>({ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(frame('meta',config)+frame('error',details)));c.close();}})}));
  try {
    await t.submit('Plan courses');
    assert.match(t.document.querySelector('.message-error').textContent,/temporarily unavailable/);
    assert.deepEqual(t.state().chats[0].messages.at(-1).error_details,details);
    assert.equal(t.calls.filter(c=>c.path==='/api/chat').length,1);
  } finally {t.dom.window.close();}
});
test('default prompts follow requirement/preference categories and enter only the editable draft',async()=>{
  const t=await setup();try {
    await until(()=>t.document.querySelectorAll('.prompt-card').length===2);
    assert.equal(t.document.querySelector('#prompt-hard-count').textContent,'2');
    assert.equal(t.document.querySelector('#prompt-soft-count').textContent,'1');
    assert.ok(t.document.querySelector('.brand-logo'));
    t.click('[data-prompt-id="units"]');
    assert.match(t.document.querySelector('#chat-input').value,/Requirements:\n- Complete at least 160 units/);
    assert.equal(t.calls.filter(c=>c.path==='/api/chat').length,0);
    t.click('#prompt-tab-soft');
    assert.equal(t.document.querySelector('#prompt-tab-soft').getAttribute('aria-selected'),'true');
    assert.equal(t.document.querySelector('#prompt-cards').getAttribute('aria-labelledby'),'prompt-tab-soft');
    t.click('[data-prompt-id="duration"]');
    assert.match(t.document.querySelector('#chat-input').value,/Preferences:\n- Prefer finishing within 8 semesters/);
    t.click('#add-all-prompts');
    const draft=t.document.querySelector('#chat-input').value;
    for(const card of config.prompt_cards)assert.equal(draft.split(card.prompt).length-1,1);
    await t.submit(draft);
    assert.deepEqual(t.calls.find(c=>c.path==='/api/chat').body,{model:'same-model',messages:[{role:'user',content:draft}]});
  } finally {t.dom.window.close();}
});
test('minor prompts have their own category and are never added by Add all defaults',async()=>{
  const t=await setup();try {
    await until(()=>t.document.querySelector('#prompt-minor-count').textContent==='2');
    t.click('#add-all-prompts');
    assert.ok(!t.document.querySelector('#chat-input').value.includes('minor'));
    t.click('#prompt-tab-minor');assert.equal(t.document.querySelectorAll('.prompt-card').length,2);
    t.click('[data-prompt-id="minor_mathematics"]');
    assert.match(t.document.querySelector('#chat-input').value,/Minors:\n- Include a Mathematics minor/);
    assert.equal(t.calls.filter(c=>c.path==='/api/chat').length,0);
    assert.equal(t.document.querySelector('#prompt-tab-minor').getAttribute('aria-selected'),'true');
  } finally {t.dom.window.close();}
});
