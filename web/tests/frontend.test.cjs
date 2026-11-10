const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const html = fs.readFileSync('frontend/index.html','utf8');
const code = fs.readFileSync('frontend/app.js','utf8');
const config = {
  defaults:[
    {id:'units',title:'160 units',description:'Minimum',strength:'hard',source:'default',source_urls:['https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/'],rules:[{type:'min_total_units',units:160}]},
    {id:'pair',title:'Grouped rule',description:'Two rules',strength:'hard',source:'default',rules:[{type:'prerequisites'},{type:'corequisites'}]},
    {id:'duration',title:'8 semesters',description:'Prefer',strength:'soft',source:'default',rules:[{type:'finish_by',semester:8}]},
  ], catalogue:[{code:'CS2102',title:'Database Systems',units:4,placeholder:false,semesters:[1,2]},{code:'CS1231S',title:'Discrete Structures',units:4,placeholder:false,semesters:[1,2]},
    {code:'DTK1234',title:'Design Thinking',units:4,placeholder:false,semesters:[1,2],categories:['ID'],source_urls:['https://www.comp.nus.edu.sg/cug/soc-22-23/']}],
  focus_areas:['Artificial Intelligence'],reference_year:'2026-2027',
  minors:[{id:'mathematics',name:'Mathematics',summary:'20 units; grouped courses and sharing caps.',source_urls:['https://www.math.nus.edu.sg/ug/majmin/minors/mamin/']},
    {id:'quantitative_finance',name:'Quantitative Finance',summary:'QF1100, QF2104 and QF3101.',source_urls:['https://www.math.nus.edu.sg/ug/majmin/minors/qfmin/']}],
};
const plan = {
  status:'feasible',total_units:4,last_semester:3,elapsed_seconds:1,optimal:true,
  exportable:true,academic_audit:{status:'passed',missing_foundation_courses:[],prerequisite_violations:[]},
  unmet_preferences:[],warnings:['Prototype'],semesters:Array.from({length:10},(_,i)=>({
    number:i+1,year_of_study:Math.floor(i/2)+1,semester:i%2+1,academic_year:`${2026+Math.floor(i/2)}-${2027+Math.floor(i/2)}`,
    units:i===2?4:0,courses:i===2?[config.catalogue[0]]:[],
  })),nusmods_planner:{minYear:'2026-2027',maxYear:'2027-2028',iblocs:false,modules:{},custom:{}},
};
async function until(predicate) {
  for(let i=0;i<80;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,5));}
  throw new Error('DOM condition did not become true');
}
async function setup(handler,{motion=false,savedDraft,expectedCards=2}={}) {
  const dom=new JSDOM(html,{url:'http://localhost:8000',runScripts:'outside-only'});
  const {window}=dom;const calls=[],animations=[];
  window.matchMedia=()=>({matches:!motion});
  window.HTMLElement.prototype.animate=function(frames,options){animations.push({card:this.dataset.card,className:this.className,frames,options});return{finished:Promise.resolve()};};
  window.structuredClone=structuredClone;
  window.HTMLElement.prototype.scrollIntoView=function(){};
  window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
  window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
  window.fetch=async(path,options)=>{
    const body=options?.body?JSON.parse(options.body):undefined;calls.push({path,body});
    const response=handler?await handler(path,body):undefined;
    const data=response ?? (path==='/api/config'?config:path==='/api/health'?{model_configured:true,model:'test'}:path==='/api/plans'?plan:{});
    return {ok:true,json:async()=>structuredClone(data)};
  };
  if(savedDraft!==undefined)window.localStorage.setItem('cs3263.pathway.v1',JSON.stringify(savedDraft));
  await window.eval(code);
  await until(()=>window.document.querySelectorAll('.constraint-card').length===expectedCards);
  return {dom,window,document:window.document,calls,animations,click:selector=>window.document.querySelector(selector).click()};
}
test('Study plan minor prompts add an optional hard rule under Minors and removal reaches the solver',async()=>{
  const t=await setup();try {
    assert.equal(t.document.querySelectorAll('.minor-option').length,2);
    t.click('[data-minor-prompt="quantitative_finance"]');
    assert.match(t.document.querySelector('#chat-input').value,/Minor in Quantitative Finance/);
    assert.equal(t.calls.filter(c=>c.path==='/api/preferences').length,0);
    t.click('[data-add-minor="mathematics"]');
    assert.equal(t.document.querySelector('#tab-minor').getAttribute('aria-selected'),'true');
    assert.equal(t.document.querySelector('#minor-count').textContent,'1');
    assert.equal(t.document.querySelector('#hard-count').textContent,'2');
    assert.match(t.document.querySelector('.constraint-card h3').textContent,/Minor in Mathematics/);
    assert.match(t.document.querySelector('.requirement-sources a').href,/mamin/);
    const remove=t.document.querySelector('[data-remove]');remove.click();
    assert.equal(t.document.querySelector('#minor-count').textContent,'0');
    t.click('#generate');await until(()=>t.calls.some(c=>c.path==='/api/plans'));
    assert.ok(!t.calls.find(c=>c.path==='/api/plans').body.cards.flatMap(c=>c.rules).some(r=>r.type==='minor_programme'));
    await until(()=>!t.document.querySelector('#generate').disabled);
  } finally {t.dom.window.close();}
});
test('removing a card removes every nested solver rule; reset restores defaults',async()=>{
  const t=await setup();
  try {
    t.click('[data-remove="pair"]');
    assert.equal(t.document.querySelectorAll('.constraint-card').length,1);
    t.click('#generate');await until(()=>t.calls.some(c=>c.path==='/api/plans'));
    const sent=t.calls.find(c=>c.path==='/api/plans').body;
    assert.deepEqual(sent.cards.map(c=>c.id),['units','duration']);
    assert.ok(!sent.cards.flatMap(c=>c.rules).some(r=>['prerequisites','corequisites'].includes(r.type)));
    await until(()=>!t.document.querySelector('#generate').disabled);
    t.click('#reset');
    assert.equal(t.document.querySelectorAll('.constraint-card').length,2);
    assert.equal(t.document.querySelector('#export').disabled,true);
    assert.match(t.document.querySelector('#plan-status').textContent,/changed/);
    assert.equal(JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1')).cards.length,3);
  } finally {t.dom.window.close();}
});
test('natural language creates a grouped card and deleting it reaches the next solve',async()=>{
  const t=await setup(path=>path==='/api/preferences'?{
    reply:'已添加第三学期偏好。',needs_clarification:false,cards:[{id:'user_group',title:'CS2102 in semester 3',description:'Your choice',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3},{type:'exclude_courses',courses:['CS1231S']}]}],
  }:undefined);
  try {
    t.document.querySelector('#chat-input').value='第三学期上CS2102';
    t.document.querySelector('#chat-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    await until(()=>t.document.querySelector('[data-card="user_group"]'));
    assert.match(t.document.querySelector('[data-card="user_group"] summary').textContent,/2 solver rules/);
    assert.match(t.document.querySelector('#messages').textContent,/已添加/);
    t.click('[data-remove="user_group"]');t.click('#generate');
    await until(()=>t.calls.some(c=>c.path==='/api/plans'));
    assert.ok(!t.calls.find(c=>c.path==='/api/plans').body.cards.some(c=>c.id==='user_group'));
    await until(()=>!t.document.querySelector('#generate').disabled);
  } finally {t.dom.window.close();}
});
test('manual input validates catalogue and supports a precise semester assignment',async()=>{
  const t=await setup();
  try {
    t.click('#add-constraint');
    t.document.querySelector('#field-course').value='CS9999';
    t.document.querySelector('#constraint-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    assert.match(t.document.querySelector('#rule-error').textContent,/not in the project catalogue/);
    t.document.querySelector('#field-course').value='CS2102';
    t.document.querySelector('#field-semester').value='3';
    t.document.querySelector('#constraint-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    assert.ok([...t.document.querySelectorAll('.constraint-card')].some(c=>c.textContent.includes('Take CS2102 in semester 3')));
    t.click('#generate');await until(()=>t.calls.some(c=>c.path==='/api/plans'));
    assert.ok(t.calls.find(c=>c.path==='/api/plans').body.cards.some(c=>c.rules.some(r=>r.course==='CS2102'&&r.semester===3)));
    await until(()=>!t.document.querySelector('#generate').disabled);
  } finally {t.dom.window.close();}
});
test('model results are discarded if constraints change while parsing',async()=>{
  let release;
  const t=await setup(path=>path==='/api/preferences'?new Promise(resolve=>{release=resolve;}):undefined);
  try {
    t.document.querySelector('#chat-input').value='CS2102 semester 3';
    t.document.querySelector('#chat-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    await until(()=>release);t.click('#reset');
    release({reply:'Added',cards:[{id:'late',title:'Late card',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3}]}]});
    await until(()=>!t.document.querySelector('#send').disabled);
    assert.equal(t.document.querySelector('[data-card="late"]'),null);
    assert.match(t.document.querySelector('#messages').textContent,/changed while/);
  } finally {t.dom.window.close();}
});
test('weekly view loads lessons and a real-shaped NUSMods share URL',async()=>{
  const t=await setup(path=>path==='/api/timetable'?{status:'feasible',lessons:[{course:'CS2102',day:'Monday',startTime:'1000',endTime:'1200',lessonType:'Lecture',classNo:'1',venue:'LT19',weeks:[1,2]}],warnings:[],exams:[],share_url:'https://nusmods.com/timetable/sem-1/share?CS2102=LEC:1'}:undefined);
  try {
    t.click('#generate');await until(()=>t.document.querySelector('[data-timetable="3"]'));
    t.click('[data-timetable="3"]');
    await until(()=>t.document.querySelectorAll('.lesson').length===1);
    assert.match(t.document.querySelector('.lesson').textContent,/CS2102/);
    assert.match(t.document.querySelector('#timetable-share').href,/CS2102=LEC:1/);
    assert.deepEqual(t.calls.find(c=>c.path==='/api/timetable').body,{courses:['CS2102'],semester:1,academic_year:'2026-2027'});
  } finally {t.dom.window.close();}
});

test('mixed agent results keep the current category and insert new cards at the front',async()=>{
  const t=await setup(path=>path==='/api/preferences'?{reply:'Added both.',cards:[
    {id:'new_soft',title:'Prefer 7 semesters',description:'Preference',strength:'soft',source:'user',rules:[{type:'finish_by',semester:7}]},
    {id:'new_hard',title:'Take CS2102 in semester 3',description:'Requirement',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3}]},
  ]}:undefined);
  try {
    t.document.querySelector('#chat-input').value='Mixed preferences';
    t.document.querySelector('#chat-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    await until(()=>!t.document.querySelector('#send').disabled);
    assert.equal(t.document.querySelector('#tab-hard').getAttribute('aria-selected'),'true');
    assert.equal(t.document.querySelector('.constraint-card').dataset.card,'new_hard');
    assert.ok(t.document.querySelector('[data-card="new_hard"]').classList.contains('card-new'));
    assert.equal(t.document.querySelectorAll('.card-label').length,0);
    assert.ok(t.document.querySelector('#tab-soft').classList.contains('tab-arrival'));
    t.click('#tab-soft');
    assert.ok(t.document.querySelector('[data-card="new_soft"]').classList.contains('card-new'));
  }finally{t.dom.window.close();}
});

test('catalogue search finds ID courses by title and adds their real code to the form',async()=>{
  const t=await setup();
  try{
    t.click('#browse-courses');
    t.document.querySelector('#catalogue-search').value='design thinking';
    t.document.querySelector('#catalogue-search').dispatchEvent(new t.window.Event('input'));
    assert.equal(t.document.querySelectorAll('.catalogue-result').length,1);
    assert.match(t.document.querySelector('.catalogue-result').textContent,/DTK1234/);
    assert.ok(t.document.querySelector('.catalogue-result a[href*="soc-22-23"]'));
    t.click('[data-choose-course="DTK1234"]');
    assert.equal(t.document.querySelector('#field-course').value,'DTK1234');
    assert.equal(t.document.querySelector('#catalogue-dialog').hasAttribute('open'),false);
    assert.ok(t.document.querySelector('[data-card="units"] a[href*="cs-26-27"]'));
    assert.equal(t.document.querySelector('#open-bridge'),null);
  }finally{t.dom.window.close();}
});

test('legacy saved defaults migrate to 160 units and retain user instructions',async()=>{
  const saved={cards:[{...config.defaults[0],title:'120 units',rules:[{type:'min_total_units',units:120}]},
    {id:'user_pin',title:'User choice',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3}]}]};
  const t=await setup(path=>{
    if(path==='/api/config')return config;
  });
  try{
    t.window.localStorage.setItem('cs3263.pathway.v1',JSON.stringify(saved));
    t.window.eval('init()');
    await until(()=>t.document.querySelector('[data-card="user_pin"]'));
    assert.match(t.document.querySelector('[data-card="units"]').textContent,/160 units/);
    assert.equal(JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1')).catalogueVersion,2);
  }finally{t.dom.window.close();}
});

test('enabled motion shrinks removed cards and sends agent cards toward both categories',async()=>{
  const t=await setup(path=>path==='/api/preferences'?{reply:'New constraints',cards:[
    {id:'flight_hard',title:'Course timing',description:'',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3}]},
    {id:'flight_soft',title:'Finish earlier',description:'',strength:'soft',source:'user',rules:[{type:'finish_by',semester:7}]},
  ]}:undefined,{motion:true});
  try{
    t.click('[data-remove="pair"]');await until(()=>!t.document.querySelector('[data-card="pair"]'));
    assert.ok(t.animations.some(a=>a.card==='pair'&&a.frames.some(f=>f.transform?.includes('scale(.65)'))));
    t.document.querySelector('#chat-input').value='Add both';
    t.document.querySelector('#chat-form').dispatchEvent(new t.window.Event('submit',{cancelable:true}));
    await until(()=>!t.document.querySelector('#send').disabled);
    assert.equal(t.animations.filter(a=>a.className.includes('constraint-flight')).length,2);
    assert.equal(t.document.querySelector('#tab-hard').getAttribute('aria-selected'),'true');
  }finally{t.dom.window.close();}
});

test('invalid academic previews list the unmet prerequisites and cannot open export',async()=>{
  const invalid=structuredClone(plan);invalid.exportable=false;delete invalid.nusmods_planner;
  invalid.academic_audit={status:'failed',missing_foundation_courses:['CS1231S'],prerequisite_violations:[
    {course:'CS2102',semester:3,requirement:'CS1231S AND CS2030S'}]};
  const t=await setup(path=>path==='/api/plans'?invalid:undefined);
  try{
    t.click('#generate');await until(()=>!t.document.querySelector('#generate').disabled);
    assert.equal(t.document.querySelector('#export').disabled,true);
    assert.match(t.document.querySelector('#academic-audit').textContent,/CS1231S/);
    assert.match(t.document.querySelector('#academic-audit').textContent,/CS2030S/);
    assert.match(t.document.querySelector('#plan-caption').textContent,/preview/i);
    assert.ok(t.document.querySelector('.course.prereq-invalid'));
    assert.ok(!t.document.querySelector('#export-dialog').hasAttribute('open'));
  }finally{t.dom.window.close();}
});

test('version 2 drafts recover absent prerequisite and core cards once without losing user preferences',async()=>{
  const fullConfig=structuredClone(config);
  fullConfig.foundation=['CS1231S'];
  fullConfig.defaults.push(
    {id:'core',title:'Foundation courses',strength:'hard',source:'default',rules:[{type:'require_courses',courses:['CS1231S']}]},
    {id:'prereqs',title:'Prerequisites first',strength:'hard',source:'default',rules:[{type:'prerequisites'}]},
  );
  const t=await setup();
  try{
    t.window.localStorage.setItem('cs3263.pathway.v1',JSON.stringify({catalogueVersion:2,cards:[
      {id:'user_timing',title:'My timing',strength:'hard',source:'user',rules:[{type:'course_in_semester',course:'CS2102',semester:3}]}]}));
    t.window.fetch=async(path)=>({ok:true,json:async()=>structuredClone(path==='/api/config'?fullConfig:{model_configured:false})});
    t.window.eval('init()');await until(()=>t.document.querySelector('[data-card="prereqs"]'));
    assert.ok(t.document.querySelector('[data-card="core"]'));
    assert.ok(t.document.querySelector('[data-card="user_timing"]'));
    assert.equal(JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1')).draftVersion,3);
    t.click('[data-remove="prereqs"]');
    assert.equal(t.document.querySelector('#academic-rule-notice').hidden,false);
    t.window.eval('init()');await new Promise(resolve=>setTimeout(resolve,20));
    assert.equal(t.document.querySelector('[data-card="prereqs"]'),null);
    t.click('#restore-academic');
    assert.ok(t.document.querySelector('[data-card="prereqs"]'));
    assert.ok(t.document.querySelector('[data-card="user_timing"]'));
  }finally{t.dom.window.close();}
});

test('a downloadable plan is rechecked through the backend export endpoint',async()=>{
  const t=await setup(path=>path==='/api/exports/nusmods'?{...plan.nusmods_planner,modules:{}}:undefined);
  try{
    let blobCount=0;
    t.window.URL.createObjectURL=()=>{blobCount++;return'blob:test';};
    t.window.URL.revokeObjectURL=()=>{};
    t.window.HTMLAnchorElement.prototype.click=function(){};
    t.click('#generate');await until(()=>!t.document.querySelector('#generate').disabled);
    t.click('#export');t.click('#download-plan');
    await until(()=>blobCount===1);
    const request=t.calls.find(c=>c.path==='/api/exports/nusmods');
    assert.deepEqual(request.body.assignments,{CS2102:3});
    assert.equal(request.body.start_year,2026);
  }finally{t.dom.window.close();}
});

test('a failed backend connection has a retry action that restores the planner',async()=>{
  const t=await setup();
  try{
    await until(()=>t.document.querySelector('#model-status').textContent.includes('server configured'));
    const workingFetch=t.window.fetch;
    t.window.fetch=async()=>{throw new t.window.TypeError('Failed to fetch');};
    await t.window.eval('init()');
    assert.equal(t.document.querySelector('#boot-error').hidden,false);
    assert.match(t.document.querySelector('#boot-error-message').textContent,/Cannot reach the local backend/);
    assert.equal(t.document.querySelector('#generate').disabled,true);
    assert.equal(t.document.querySelector('#retry-init').disabled,false);
    t.window.fetch=workingFetch;
    t.click('#retry-init');
    await until(()=>t.document.querySelector('#boot-error').hidden);
    assert.equal(t.document.querySelector('#generate').disabled,false);
    assert.equal(t.document.querySelectorAll('.constraint-card').length,2);
    assert.equal(t.document.querySelector('#reset').disabled,false);
  }finally{t.dom.window.close();}
});

test('an unmarked empty browser draft cannot overwrite the initial defaults',async()=>{
  const t=await setup(undefined,{savedDraft:{catalogueVersion:2,draftVersion:3,cards:[],horizon:8,
    messages:[{role:'user',text:'Keep my saved conversation'}]}});
  try{
    assert.equal(t.document.querySelector('#constraint-count').textContent,'3');
    assert.equal(t.document.querySelector('#hard-count').textContent,'2');
    assert.equal(t.document.querySelector('#soft-count').textContent,'1');
    assert.equal(t.document.querySelector('#horizon').value,'8');
    assert.match(t.document.querySelector('#messages').textContent,/Keep my saved conversation/);
    const saved=JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1'));
    assert.equal(saved.cards.length,3);
    assert.equal(saved.emptyDraftExplicit,false);
  }finally{t.dom.window.close();}
});

test('explicitly deleting all cards remains empty on reload and reset restores defaults',async()=>{
  const t=await setup();
  try{
    t.click('[data-remove="units"]');t.click('[data-remove="pair"]');
    t.click('#tab-soft');t.click('[data-remove="duration"]');
    const saved=JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1'));
    assert.equal(saved.cards.length,0);
    assert.equal(saved.emptyDraftExplicit,true);
    await t.window.eval('init()');
    assert.equal(t.document.querySelectorAll('.constraint-card').length,0);
    t.click('#reset');
    assert.equal(t.document.querySelector('#constraint-count').textContent,'3');
    assert.equal(JSON.parse(t.window.localStorage.getItem('cs3263.pathway.v1')).emptyDraftExplicit,false);
  }finally{t.dom.window.close();}
});
