const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const STORAGE_KEY = 'cs3263.pathway.v1';
const CATALOGUE_VERSION = 2;
const DRAFT_VERSION = 3;
const state = {config:null, cards:[], messages:[], filter:'hard', plan:null, stale:false, busy:false, chatting:false, view:'degree', timetable:null, revision:0, timetableToken:0, editing:null, intentionallyEmpty:false};
let toastTimer;
const freshCards=new Map();
const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? true;
function animateElement(element, frames, options={}) {
  if (!element?.animate || prefersReducedMotion()) return null;
  return element.animate(frames,{duration:350,easing:'cubic-bezier(.2,.8,.2,1)',...options});
}
function cardPositions() {return new Map($$('.constraint-card').map(c=>[c.dataset.card,c.getBoundingClientRect()]));}
function highlightTab(strength) {
  const tab=$(`#tab-${strength}`);tab.classList.remove('tab-arrival');void tab.offsetWidth;tab.classList.add('tab-arrival');
  setTimeout(()=>tab.classList.remove('tab-arrival'),2000);
}
function flyConstraints(cards) {
  const source=$$('#messages .message.assistant:not(#thinking)').at(-1) || $('.chat-heading');
  const start=source.getBoundingClientRect();
  cards.forEach((card,index)=>{
    highlightTab(card.strength);
    const target=card.strength===state.filter ? $(`[data-card="${card.id}"]`) : $(`#tab-${card.strength}`);
    if (!target || prefersReducedMotion()) return;
    const end=target.getBoundingClientRect();
    const flight=document.createElement('div');flight.className=`constraint-flight ${card.strength}`;flight.setAttribute('aria-hidden','true');
    flight.textContent=card.title;flight.style.left=`${start.left+15}px`;flight.style.top=`${start.top+10}px`;document.body.append(flight);
    const dx=end.left-start.left,dy=end.top-start.top;
    const animation=animateElement(flight,[{transform:'translate(0,0) scale(.9)',opacity:0},{offset:.15,transform:'translate(-15px,-18px) scale(1)',opacity:1},{offset:.65,transform:`translate(${dx*.65}px,${dy*.65-55}px) scale(.8)`,opacity:.95},{transform:`translate(${dx}px,${dy}px) scale(.25)`,opacity:0}],{duration:800,delay:index*120});
    if(animation)animation.finished.catch(()=>{}).finally(()=>flight.remove());else flight.remove();
  });
}

function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 3500);
}
function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({catalogueVersion:CATALOGUE_VERSION,draftVersion:DRAFT_VERSION,emptyDraftExplicit:state.intentionallyEmpty&&state.cards.length===0,cards:state.cards, messages:state.messages.slice(-40), horizon:Number($('#horizon').value), startYear:Number($('#start-year').value),mathQualified:$('#math-qualified').checked,allowUnpublished:$('#allow-unpublished').checked}));
  } catch { $('#save-status').textContent = 'Browser storage unavailable'; }
}
function markChanged() {
  if(state.cards.length)state.intentionallyEmpty=false;
  state.revision++; state.stale = Boolean(state.plan); state.timetableToken++;
  $('#export').disabled = !canExportPlan();
  if (state.stale) showPlanStatus('Your constraints have changed. Generate a new plan before exporting or loading a timetable.');
  save();
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(e => e.msg).join('; ') : typeof detail==='object' ? detail.message || `Request failed (${response.status})` : detail || `Request failed (${response.status})`);
    error.academicAudit=detail?.academic_audit;
    throw error;
  }
  return body;
}
const cardIcons = {min_total_units:'◷', require_courses:'▤', exclude_courses:'⊖', prerequisites:'⇢', corequisites:'⇄', semester_availability:'▦', exam_clashes:'◴', semester_units:'◫', focus_area:'◎', finish_by:'⚑', workload_target:'≈', course_in_semester:'▦', blocked_semesters:'⊘',category_units:'◇',weekly_feasibility:'▦'};
function academicSolverCoverage() {
  const rules=state.cards.filter(c=>c.strength==='hard').flatMap(c=>c.rules);
  const required=new Set(rules.filter(r=>r.type==='require_courses').flatMap(r=>r.courses));
  return {prerequisites:rules.some(r=>r.type==='prerequisites'),foundation:(state.config.foundation||[]).every(code=>required.has(code))};
}
function restoreAcademicCards() {
  if(state.busy || !state.config)return;
  const defaults=state.config.defaults.filter(c=>['core','prereqs'].includes(c.id));
  const ids=new Set(defaults.map(c=>c.id));
  state.cards=[...structuredClone(defaults),...state.cards.filter(c=>!ids.has(c.id))];
  state.filter='hard';markChanged();renderCards({newIds:[...ids]});
  toast('Foundation and prerequisite rules restored. Generate a new plan.');
}
function canExportPlan() {
  return Boolean(state.plan && !state.stale && !state.busy && state.plan.exportable===true && state.plan.academic_audit?.status==='passed');
}
function renderAcademicAudit() {
  const audit=state.plan?.academic_audit,container=$('#academic-audit');
  container.hidden=!audit || audit.status==='passed';
  if(container.hidden){container.innerHTML='';return;}
  container.innerHTML=`<div class="notice error"><strong>Academic checks failed — preview only. Export is disabled.</strong>${audit.missing_foundation_courses?.length?`<p>Missing foundation courses: ${audit.missing_foundation_courses.map(escapeHTML).join(', ')}.</p>`:''}${audit.prerequisite_violations?.length?`<ul>${audit.prerequisite_violations.map(v=>`<li><strong>${escapeHTML(v.course)} · semester ${v.semester}</strong>: complete ${escapeHTML(v.requirement)} in earlier semesters.</li>`).join('')}</ul>`:''}<button class="secondary" id="restore-plan-academic">Restore core & prerequisites</button></div>`;
}
function renderCards({positions=cardPositions(),newIds=[]}={}) {
  newIds.forEach(id=>freshCards.set(id,Date.now()+30000));
  newIds=state.cards.filter(c=>(freshCards.get(c.id)||0)>Date.now()).map(c=>c.id);
  const hard = state.cards.filter(c => c.strength === 'hard').length;
  $('#constraint-count').textContent = state.cards.length; $('#hard-count').textContent = hard; $('#soft-count').textContent = state.cards.length - hard;
  $$('[data-filter]').forEach(button => {button.setAttribute('aria-selected',String(button.dataset.filter === state.filter)); button.tabIndex = button.dataset.filter === state.filter ? 0 : -1;});
  $('#constraint-list').setAttribute('aria-labelledby',`tab-${state.filter}`);
  const cards = state.cards.filter(c => c.strength === state.filter);
  $('#constraint-list').innerHTML = cards.length ? cards.map(card => {
    const editable = card.rules.length === 1 && ['min_total_units','course_in_semester','finish_by','semester_units','workload_target','focus_area','require_courses','exclude_courses','blocked_semesters'].includes(card.rules[0].type);
    const sources=(card.source_urls || []).filter(url=>{try{const u=new URL(url);return u.protocol==='https:' && (u.hostname==='nus.edu.sg'||u.hostname.endsWith('.nus.edu.sg')||['nusmods.com','api.nusmods.com'].includes(u.hostname));}catch{return false;}});
    return `<article class="constraint-card ${card.strength} ${newIds.includes(card.id)?'card-new':''}" data-card="${escapeHTML(card.id)}"><div class="card-top"><span class="card-icon" aria-hidden="true">${cardIcons[card.rules[0].type] || '◇'}</span></div>${editable ? `<button class="edit-card" data-edit="${escapeHTML(card.id)}" aria-label="Edit ${escapeHTML(card.title)}">Edit</button>` : ''}<button class="remove-card" data-remove="${escapeHTML(card.id)}" aria-label="Remove ${escapeHTML(card.title)}">×</button><h3>${escapeHTML(card.title)}</h3><p>${escapeHTML(card.description)}</p>${sources.length?`<div class="requirement-sources">${sources.map((url,i)=>`<a href="${escapeHTML(url)}" target="_blank" rel="noopener">${url.includes('api.nusmods')?'Course data':i?'More details':'Official requirement'} ↗</a>`).join('')}</div>`:''}<details><summary>${card.rules.length} solver rule${card.rules.length === 1 ? '' : 's'}</summary><pre>${escapeHTML(JSON.stringify(card.rules,null,2))}</pre></details></article>`;
  }).join('') : '<div class="empty-constraints">No constraints here yet.<br>Add one yourself or tell the assistant what matters.</div>';
  $$('.constraint-card').forEach(card=>{
    const old=positions.get(card.dataset.card),next=card.getBoundingClientRect();
    if(old)animateElement(card,[{transform:`translate(${old.left-next.left}px,${old.top-next.top}px)`},{transform:'translate(0,0)'}],{duration:420});
    else animateElement(card,[{opacity:0,transform:'translateY(-15px) scale(.94)'},{opacity:1,transform:'translateY(0) scale(1)'}]);
  });
  const coverage=academicSolverCoverage();
  $('#academic-rule-notice').hidden=coverage.prerequisites && coverage.foundation;
}
function appendMessage(role, text, count=0, error=false) {
  state.messages.push({role,text,count,error}); renderMessages(); save();
}
function renderMessages() {
  const messages = state.messages.length ? state.messages : [{role:'assistant',text:'Hi! Let’s make room for what matters to you.\n\nTell me when you’d like to take a course, how long you’d like to study, or which semester you want to keep free.',count:0}];
  $('#messages').innerHTML = messages.map(m => `<div class="message ${m.role === 'user' ? 'user' : 'assistant'} ${m.error ? 'error' : ''}">${escapeHTML(m.text)}${m.count ? `<br><span class="added-label">✓ ${m.count} constraint${m.count > 1 ? 's' : ''} added to your list</span>` : ''}</div>`).join('');
  if (state.chatting) $('#messages').insertAdjacentHTML('beforeend','<div class="message assistant" id="thinking">Translating your preference…</div>');
  $('#messages').scrollTop = $('#messages').scrollHeight;
}
async function sendPreference(event) {
  event.preventDefault();
  const message = $('#chat-input').value.trim();
  if (!message || state.chatting || state.busy) return;
  state.chatting = true; $('#send').disabled = true; $('#generate').disabled = true; $('#chat-input').value = '';
  appendMessage('user',message);
  const revision = state.revision;
  try {
    const result = await api('/api/preferences',{message,cards:state.cards,horizon:Number($('#horizon').value)});
    if (revision !== state.revision) throw new Error('Your constraints changed while the assistant was working. Please send the preference again against the updated list.');
    if (result.cards.length) {
      if (state.cards.length + result.cards.length > 80) throw new Error('The planner supports up to 80 cards. Remove a card before adding more.');
      const positions=cardPositions();
      state.cards=[...result.cards,...state.cards];
      if(new Set(result.cards.map(c=>c.strength)).size===1)state.filter=result.cards[0].strength;
      markChanged();renderCards({positions,newIds:result.cards.map(c=>c.id)});
      appendMessage('assistant',result.reply,result.cards.length);
      flyConstraints(result.cards);
      toast(`${result.cards.length} constraint card${result.cards.length > 1 ? 's' : ''} added`);
    } else appendMessage('assistant',result.reply,0);
  } catch (error) {appendMessage('assistant',error.message,0,true);}
  finally {state.chatting = false; $('#send').disabled = false; $('#generate').disabled = false; renderMessages(); $('#chat-input').focus();}
}
function showPlanStatus(message, kind='') {
  const el = $('#plan-status'); el.textContent = message; el.hidden = !message; el.className = `notice ${kind}`;
}
function setBusy(busy) {
  state.busy = busy;
  $('#generate').disabled = busy || state.chatting; $('#empty-generate')?.toggleAttribute('disabled',busy);
  $('#generate').innerHTML = busy ? '<span class="button-icon">◌</span> Finding your path…' : '<span class="button-icon">✳</span> Generate my plan <span>→</span>';
  $('#send').disabled = busy || state.chatting;
  $('#reset').disabled = busy; $('#add-constraint').disabled = busy;
  $('#export').disabled = !canExportPlan();
}
async function generatePlan() {
  if (state.busy || state.chatting || !state.config) return;
  const revision = state.revision;
  setBusy(true); showPlanStatus('Finding courses and verifying a complete weekly timetable for every semester. Conflicting combinations are fed back into the search.','loading');
  $('#study-plan').scrollIntoView({behavior:'smooth',block:'start'});
  try {
    const result = await api('/api/plans',{schema_version:1,cards:state.cards,horizon:Number($('#horizon').value),start_year:Number($('#start-year').value),math_qualified:$('#math-qualified').checked,allow_unpublished:$('#allow-unpublished').checked});
    if (revision !== state.revision) {showPlanStatus('Settings changed during generation. Generate again to use the updated constraints.'); return;}
    state.plan = null; state.timetable = null; state.timetableToken++;
    renderAcademicAudit();
    if (!['feasible','conditional'].includes(result.status)) {
      state.stale = false; $('#plan-content').innerHTML = '<div class="empty-plan"><h3>Let’s give your plan a little more room.</h3><p>Review conflicting requirements, relax a workload limit, or extend the search horizon.</p></div>';
      $('#plan-caption').textContent = 'No feasible course plan is available for these constraints.';
      $('#plan-warnings').hidden = true; $('[data-view="weekly"]').disabled = true;
      showPlanStatus(result.message,'error'); return;
    }
    state.plan = result; state.stale = false; state.view = 'degree';
    $('[data-view="weekly"]').disabled = false;
    $('#plan-caption').textContent = `${result.total_units} units · ${result.last_semester} semesters · ${result.elapsed_seconds}s search · ${result.optimal ? 'Optimum proven' : 'Feasible plan; optimality not proven'}`;
    showPlanStatus(result.unmet_preferences.length ? `Plan found. Preferences not fully met: ${result.unmet_preferences.map(p => p.title).join('; ')}.` : `Plan found. All active hard constraints passed.${result.weekly_verified?' Every active semester has a verified clash-free weekly timetable.':''}`);
    if(result.status==='conditional')showPlanStatus(`Conditional plan: published lessons are clash-free. Lesson times are unpublished for ${(result.unpublished_courses||[]).join(', ')}; complete weekly feasibility is not yet verified.`);
    const academicPassed=result.academic_audit?.status==='passed';
    if(!academicPassed){
      $('#plan-caption').textContent='Exploratory preview · academic checks have not passed';
      showPlanStatus('The selected cards have a solution, but the result is not an academically valid study plan. Restore foundation and prerequisite rules, then regenerate.','error');
    }
    renderAcademicAudit();
    $('#plan-warnings').hidden = false;
    $('#plan-warnings').innerHTML = `<details class="validation-notes"><summary>Plan assumptions & validation scope (${result.warnings.length})</summary><ul>${result.warnings.map(w => `<li>${escapeHTML(w)}</li>`).join('')}</ul></details>`;
    renderPlan(); toast(academicPassed?'Your study plan is ready':'Preview needs academic fixes before export');
  } catch (error) {showPlanStatus(error.message,'error');}
  finally {setBusy(false);}
}
function courseMarkup(course) {
  const color = course.code.startsWith('CS') ? 'cs' : /^(MA|ST)/.test(course.code) ? 'math' : '';
  const invalid=state.plan?.academic_audit?.prerequisite_violations?.some(v=>v.course===course.code);
  return `<div class="course ${color} ${invalid?'prereq-invalid':''}"><div><span class="code">${escapeHTML(course.code)}</span><span class="course-title">${escapeHTML(course.title)}</span>${invalid?'<span class="prereq-error">Prerequisites not completed first</span>':''}</div><span class="course-units">${course.units} units</span></div>`;
}
function renderPlan() {
  if (!state.plan) return;
  $$('[data-view]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.view === state.view)));
  if (state.view === 'weekly') {renderWeeklyShell();return;}
  const semesters = state.plan.semesters.slice(0,Math.max(8,state.plan.last_semester));
  let html = `<div class="plan-stats"><div><strong>${state.plan.total_units}</strong><span>planned units</span></div><div><strong>${semesters.reduce((n,s)=>n+s.courses.length,0)}</strong><span>courses</span></div><div><strong>${state.plan.last_semester}</strong><span>semesters</span></div></div>`;
  for (let i=0;i<semesters.length;i+=2) {
    const pair = semesters.slice(i,i+2);
    html += `<div class="year-heading">YEAR ${pair[0].year_of_study}<span>AY ${pair[0].academic_year.replace('-',' / ')}</span></div><div class="year-row">${pair.map(s => `<article class="semester"><div class="semester-header"><h3>Semester ${s.semester} <span>· overall ${s.number}</span></h3><span>${s.units} units</span></div><div class="course-list">${s.courses.length ? s.courses.map(courseMarkup).join('') : '<div class="semester-empty">No courses planned. Room for what’s next.</div>'}</div>${s.courses.length ? `<button class="timetable-button" data-timetable="${s.number}">View weekly timetable →</button>` : ''}</article>`).join('')}</div>`;
  }
  $('#plan-content').innerHTML = html;
}
function renderWeeklyShell(number) {
  const semesters = state.plan.semesters.filter(s => s.courses.length);
  $('#plan-content').innerHTML = `<div class="weekly-toolbar"><label>Semester<select id="weekly-semester">${semesters.map(s => `<option value="${s.number}" ${s.number === number ? 'selected' : ''}>Year ${s.year_of_study}, Sem ${s.semester} · ${s.units} units</option>`).join('')}</select></label><button class="secondary" id="load-timetable">Load reference timetable</button><a id="timetable-share" target="_blank" rel="noopener" hidden>Open this timetable in NUSMods ↗</a></div><p class="fine-print">Uses live AY2026/27 NUSMods lessons. Future years assume the same offering pattern. Enabled weekly requirements feed conflicts back into degree planning.</p><div id="weekly-status" class="notice" hidden></div><div id="weekly-content"><div class="empty-plan"><h3>See your week take shape.</h3><p>Load the reference timetable to find a clash-free combination of classes.</p></div></div>`;
}
async function loadTimetable() {
  if (state.stale) {toast('Generate an updated plan first');return;}
  const semester = state.plan.semesters.find(s => s.number === Number($('#weekly-semester').value));
  const token = ++state.timetableToken;
  const status = $('#weekly-status'); status.hidden = false; status.className='notice loading'; status.textContent='Loading live lessons and finding compatible classes…';
  $('#load-timetable').disabled = true; $('#timetable-share').hidden = true;
  try {
    const result = await api('/api/timetable',{courses:semester.courses.map(c => c.code),semester:semester.semester,academic_year:state.config.reference_year});
    if (token !== state.timetableToken || !$('#weekly-status')) return;
    state.timetable = result;
    const currentStatus = $('#weekly-status'); currentStatus.className = `notice ${['infeasible','timeout'].includes(result.status) ? 'error' : ''}`;
    currentStatus.textContent = [result.status === 'feasible' ? 'A clash-free lesson selection was found.' : 'A complete weekly timetable could not be built.', ...result.warnings].join(' ');
    if (result.share_url) {$('#timetable-share').href=result.share_url;$('#timetable-share').hidden=false;}
    renderTimetable(result);
  } catch (error) {if (token === state.timetableToken && $('#weekly-status')) {$('#weekly-status').textContent=error.message;$('#weekly-status').className='notice error';}}
  finally {if (token === state.timetableToken && $('#load-timetable')) $('#load-timetable').disabled=false;}
}
const timeMinutes = value => Number(value.slice(0,2))*60+Number(value.slice(2));
function renderTimetable(result) {
  if (!result.lessons.length) {$('#weekly-content').innerHTML='<div class="empty-plan"><p>No published lessons to display.</p></div>';return;}
  const lessons = result.lessons;
  const start = Math.min(8*60,...lessons.map(l => Math.floor(timeMinutes(l.startTime)/60)*60));
  const end = Math.max(18*60,...lessons.map(l => Math.ceil(timeMinutes(l.endTime)/60)*60));
  const colors = ['#eaf0fb','#edf3e5','#f7ecf8','#fbf0df','#e6f3f1','#f8e8e5','#efedfb'];
  const courses = [...new Set(lessons.map(l => l.course))];
  const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
  const html = `<div class="timetable-scroll"><div class="timetable"><div class="day-heading"></div>${days.map(day=>`<div class="day-heading">${day.slice(0,3)}</div>`).join('')}<div class="time-column" style="height:${end-start}px">${Array.from({length:(end-start)/60},(_,i)=>`<div class="time-label" style="top:${i*60}px">${String(start/60+i).padStart(2,'0')}:00</div>`).join('')}</div>${days.map(day=>`<div class="day-column" style="height:${end-start}px">${lessons.filter(l=>l.day===day).map(l=>{const title=`${l.course} · ${l.lessonType} ${l.classNo}\n${l.startTime}–${l.endTime} · ${l.venue}\nWeeks: ${JSON.stringify(l.weeks)}`;return `<div class="lesson" title="${escapeHTML(title)}" style="top:${timeMinutes(l.startTime)-start}px;height:${timeMinutes(l.endTime)-timeMinutes(l.startTime)}px;background:${colors[courses.indexOf(l.course)%colors.length]}"><b>${escapeHTML([l.course,...(l.sharedWith||[])].join(" + "))}</b>${escapeHTML(l.lessonType)} ${escapeHTML(l.classNo)}<small>${l.startTime.slice(0,2)}:${l.startTime.slice(2)}–${l.endTime.slice(0,2)}:${l.endTime.slice(2)} · ${escapeHTML(l.venue)}</small><small>${Array.isArray(l.weeks) ? `Weeks ${escapeHTML(l.weeks.join(', '))}` : 'Date-based weeks · hover for details'}</small></div>`;}).join('')}</div>`).join('')}</div></div>`;
  const exams = result.exams.map(e => `<p>${escapeHTML(e.course)} · ${escapeHTML(new Date(e.date).toLocaleString('en-SG',{timeZone:'Asia/Singapore',dateStyle:'medium',timeStyle:'short'}))} SGT · ${e.duration ?? '?'} min</p>`).join('');
  $('#weekly-content').innerHTML = html + `<div class="exam-list"><strong>Reference-year examinations</strong>${exams || '<p>No published examinations for these courses.</p>'}</div>`;
}
function showRuleFields(rule=null) {
  const type = $('#rule-type').value;
  const courseField = `<label>Course code<input id="field-course" list="catalogue-codes" placeholder="CS2102" value="${escapeHTML(rule?.course || '')}" required><datalist id="catalogue-codes">${state.config.catalogue.filter(c=>!c.placeholder && c.planner_eligible!==false).map(c=>`<option value="${escapeHTML(c.code)}">${escapeHTML(c.title)} ${(c.categories||[]).join(' ')}</option>`).join('')}</datalist></label>`;
  const semesterField = `<label>Overall semester<input id="field-semester" type="number" min="1" max="${$('#horizon').value}" value="${rule?.semester || 3}" required><small>1 = Y1S1, 3 = Y2S1, 8 = Y4S2</small></label>`;
  const unitField = `<label>Units<input id="field-units" type="number" min="${type==='min_total_units'?0:4}" max="${type==='min_total_units'?240:32}" value="${rule?.units ?? (type==='min_total_units'?160:20)}" required></label>`;
  const fields = {
    course_in_semester:courseField+semesterField, finish_by:semesterField, min_total_units:unitField, workload_target:unitField,
    require_courses:`<label>Course codes, separated by commas<input id="field-courses" placeholder="CS2102, CS3243" value="${escapeHTML((rule?.courses || []).join(', '))}" required></label>`,
    exclude_courses:`<label>Course codes, separated by commas<input id="field-courses" placeholder="CS3244" value="${escapeHTML((rule?.courses || []).join(', '))}" required></label>`,
    blocked_semesters:`<label>Overall semesters, separated by commas<input id="field-semesters" placeholder="5, 6" value="${escapeHTML((rule?.semesters || []).join(', '))}" required></label>`,
    focus_area:`<label>Focus area<select id="field-area">${state.config.focus_areas.map(area=>`<option ${area===rule?.area?'selected':''}>${escapeHTML(area)}</option>`).join('')}</select></label>`,
    semester_units:`<div class="field-row"><label>Minimum units<input id="field-min" type="number" min="0" max="40" value="${rule?.minimum ?? 16}" required></label><label>Maximum units<input id="field-max" type="number" min="0" max="40" value="${rule?.maximum ?? 24}" required></label></div><label>First semester maximum<input id="field-first-max" type="number" min="0" max="40" value="${rule?.first_semester_maximum ?? 20}" required></label><p>Limits apply to non-empty semesters. Empty semesters are permitted.</p>`,
  };
  $('#rule-fields').innerHTML = fields[type];
  const soft = ['course_in_semester','finish_by','workload_target'].includes(type);
  $('#rule-strength').disabled = !soft || type === 'workload_target';
  if (!soft) $('#rule-strength').value='hard';
  if (type==='workload_target') $('#rule-strength').value='soft';
  $('#rule-error').textContent='';
}
function openConstraintDialog(card=null) {
  if (state.busy) return;
  state.editing=card?.id || null;
  $('#constraint-dialog h2').textContent=card?'Edit constraint':'Add a constraint';
  $('#constraint-form .primary').textContent=card?'Save constraint':'Add to my constraints ＋';
  $('#rule-type').disabled=Boolean(card); $('#rule-type').value=card?.rules[0].type || 'course_in_semester';
  $('#rule-strength').value=card?.strength || 'hard';
  showRuleFields(card?.rules[0]); $('#constraint-dialog').showModal();
}
function submitConstraint(event) {
  event.preventDefault();
  const type=$('#rule-type').value;
  const rule={type}; let title,description;
  if (type==='course_in_semester') {rule.course=$('#field-course').value.trim().toUpperCase();rule.semester=Number($('#field-semester').value);title=`Take ${rule.course} in semester ${rule.semester}`;description=`Year ${Math.ceil(rule.semester/2)}, semester ${(rule.semester-1)%2+1}.`;}
  if (type==='min_total_units' || type==='workload_target') {rule.units=Number($('#field-units').value);title=type==='min_total_units'?`Complete at least ${rule.units} units`:`Aim for ${rule.units} units per semester`;description=type==='min_total_units'?'Minimum total credits across the planned courses.':'Prefer this workload in non-empty semesters.';}
  if (type==='finish_by') {rule.semester=Number($('#field-semester').value);title=`Finish within ${rule.semester} semesters`;description='Complete all selected courses by this overall semester.';}
  if (['require_courses','exclude_courses'].includes(type)) {rule.courses=[...new Set($('#field-courses').value.split(/[,\s]+/).map(c=>c.trim().toUpperCase()).filter(Boolean))];title=`${type==='require_courses'?'Include':'Exclude'} ${rule.courses.join(', ')}`;description=type==='require_courses'?'These courses must be part of the study plan.':'Do not select these courses in the plan.';}
  if (type==='blocked_semesters') {rule.semesters=[...new Set($('#field-semesters').value.split(/[,\s]+/).filter(Boolean).map(Number))];title=`Keep semester${rule.semesters.length>1?'s':''} ${rule.semesters.join(', ')} free`;description='No courses can be assigned to these semesters.';}
  if (type==='focus_area') {rule.area=$('#field-area').value;title=`Complete ${rule.area}`;description='Three primary courses, including one at level 4000 or above.';}
  if (type==='semester_units') {rule.minimum=Number($('#field-min').value);rule.maximum=Number($('#field-max').value);rule.first_semester_maximum=Number($('#field-first-max').value);title=`Keep semester workloads at ${rule.minimum}–${rule.maximum} units`;description=`Non-empty semesters only. First semester at most ${rule.first_semester_maximum} units.`;}
  const error = validateManualRule(rule);
  if (error) {$('#rule-error').textContent=error;return;}
  if (!state.editing && state.cards.length >= 80) {$('#rule-error').textContent='Maximum 80 cards. Remove a card first.';return;}
  const card={id:state.editing || 'user_'+crypto.randomUUID().replaceAll('-','').slice(0,12),title,description,strength:$('#rule-strength').value,source:'user',rules:[rule]};
  if (state.editing) state.cards=state.cards.map(c=>c.id===state.editing?card:c); else state.cards.unshift(card);
  state.filter=card.strength; markChanged();renderCards({newIds:[card.id]});$('#constraint-dialog').close();toast(state.editing?'Constraint updated':'Constraint added');
}
function validateManualRule(rule) {
  const known=new Set(state.config.catalogue.map(c=>c.code));
  for (const code of rule.courses || (rule.course?[rule.course]:[])) if (!known.has(code)) return `${code} is not in the project catalogue. CS1010S is not automatically substituted for CS1101S.`;
  if (rule.semesters?.some(s=>!Number.isInteger(s) || s<1 || s>Number($('#horizon').value))) return 'Each semester must be an integer within the selected horizon.';
  if (rule.semesters?.length===0 || rule.courses?.length===0) return 'Add at least one entry.';
  if (rule.type==='semester_units' && (rule.minimum>rule.maximum || rule.minimum>rule.first_semester_maximum)) return 'Minimum workload cannot exceed either maximum.';
  return null;
}
async function downloadPlan() {
  if (!canExportPlan())return;
  const revision=state.revision,plan=state.plan,button=$('#download-plan');button.disabled=true;
  try{
    const assignments=Object.fromEntries(plan.semesters.flatMap(s=>s.courses.map(c=>[c.code,s.number])));
    const payload=await api('/api/exports/nusmods',{assignments,horizon:plan.semesters.length,
      start_year:Number(plan.semesters[0].academic_year.slice(0,4)),math_qualified:plan.student_profile?.math_qualified ?? true});
    if(revision!==state.revision || plan!==state.plan || !canExportPlan())throw new Error('Plan changed during export. Generate an updated plan first.');
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='pathway-nusmods-planner.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Academic checks passed. Planner JSON downloaded.');
  }catch(error){
    if(error.academicAudit && plan===state.plan){state.plan.academic_audit=error.academicAudit;state.plan.exportable=false;renderAcademicAudit();renderPlan();$('#export').disabled=true;}
    toast(error.message);
  }finally{button.disabled=false;}
}
async function init() {
  $('#retry-init').disabled=true;
  try {
    state.config=await api('/api/config'); state.cards=structuredClone(state.config.defaults);
    try {
      const saved=JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (saved && Array.isArray(saved.cards) && saved.cards.every(c=>c.id && c.title && ['hard','soft'].includes(c.strength) && Array.isArray(c.rules) && c.rules.length)) {
        if(saved.cards.length===0 && saved.emptyDraftExplicit!==true){
          saved.cards=structuredClone(state.config.defaults);
          toast('Defaults restored: an old empty browser draft was found.');
        }
        state.intentionallyEmpty=saved.cards.length===0 && saved.emptyDraftExplicit===true;
        if((saved.catalogueVersion || 1)<CATALOGUE_VERSION){
          const defaults=new Map(state.config.defaults.map(c=>[c.id,c]));
          state.cards=saved.cards.map(c=>c.source==='default'&&defaults.has(c.id)?structuredClone(defaults.get(c.id)):c).filter(c=>!c.rules.some(r=>(r.courses||[]).some(code=>['ID1','ID2','CD','GEC','GEA','GESS','GEN'].includes(code))));
          const present=new Set(state.cards.map(c=>c.id));
          state.cards.push(...state.config.defaults.filter(c=>['weekly','gec','gea','gess','gen','idcd'].includes(c.id)&&!present.has(c.id)));
        }else state.cards=saved.cards;
        if((saved.draftVersion||1)<DRAFT_VERSION){
          const coverage=academicSolverCoverage();
          const restore=state.config.defaults.filter(c=>(c.id==='core'&&!coverage.foundation)||(c.id==='prereqs'&&!coverage.prerequisites));
          if(restore.length){
            const ids=new Set(restore.map(c=>c.id));
            state.cards=[...structuredClone(restore),...state.cards.filter(c=>!ids.has(c.id))];
            toast('This update restored missing foundation / prerequisite rules in your old draft. Generate a fresh plan.');
          }
        }
        state.messages=Array.isArray(saved.messages)?saved.messages:[];
        if ([8,10,12].includes(saved.horizon)) $('#horizon').value=String(saved.horizon);
        if ([2025,2026,2027].includes(saved.startYear)) $('#start-year').value=String(saved.startYear);
        $('#math-qualified').checked=saved.mathQualified!==false;
        $('#allow-unpublished').checked=saved.allowUnpublished===true;
      }
    } catch { /* A damaged browser draft must not prevent startup. */ }
    renderCards();renderMessages();save();
    $('#boot-error').hidden=true;
    $('#generate').disabled=false;$('#add-constraint').disabled=false;$('#reset').disabled=false;
    const health=await api('/api/health');
    $('#model-status').innerHTML=health.model_configured?`<span class="status-dot"></span> SoCLaaS · ${escapeHTML(health.model)} · server configured`:'<span class="status-dot off"></span> Chat needs backend model configuration · manual constraints available';
  } catch (error) {
    $('#boot-error').hidden=false;
    $('#boot-error-message').textContent=error instanceof TypeError ? 'Cannot reach the local backend. Start it with ./run.sh start, then retry the connection.' : 'Could not load the planner: '+error.message;
    $('#generate').disabled=true;$('#add-constraint').disabled=true;$('#reset').disabled=true;
    $('#model-status').textContent='Backend unavailable · retry the connection to continue';
  } finally {$('#retry-init').disabled=false;}
}
$('#retry-init').addEventListener('click',init);
$$('[data-filter]').forEach(button=>{
  button.addEventListener('click',()=>{state.filter=button.dataset.filter;renderCards();});
  button.addEventListener('keydown',event=>{if (['ArrowLeft','ArrowRight'].includes(event.key)) {event.preventDefault();state.filter=state.filter==='hard'?'soft':'hard';renderCards();$(`[data-filter="${state.filter}"]`).focus();}});
});
$('#constraint-list').addEventListener('click',async event=>{
  const remove=event.target.closest('[data-remove]'),edit=event.target.closest('[data-edit]');
  if (state.busy) return;
  if (remove) {
    const positions=cardPositions(),element=remove.closest('.constraint-card');
    state.cards=state.cards.filter(c=>c.id!==remove.dataset.remove);state.intentionallyEmpty=state.cards.length===0;markChanged();
    const animation=animateElement(element,[{opacity:1,transform:'scale(1)'},{opacity:0,transform:'scale(.65) translateY(10px)'}],{duration:240,easing:'ease-in'});
    if(animation)await animation.finished.catch(()=>{});
    renderCards({positions});toast('Constraint and its solver rules removed');
  }
  if (edit) openConstraintDialog(state.cards.find(c=>c.id===edit.dataset.edit));
});
$('#reset').addEventListener('click',()=>{state.cards=structuredClone(state.config.defaults);state.filter='hard';markChanged();renderCards();toast('Default constraints restored');});
$('#restore-academic').addEventListener('click',restoreAcademicCards);
$('#academic-audit').addEventListener('click',event=>{if(event.target.closest('#restore-plan-academic'))restoreAcademicCards();});
$('#add-constraint').addEventListener('click',()=>openConstraintDialog());
$('#rule-type').addEventListener('change',()=>showRuleFields());
$('#constraint-form').addEventListener('submit',submitConstraint);
$$('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('#chat-form').addEventListener('submit',sendPreference);
$('#chat-input').addEventListener('keydown',event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();$('#chat-form').requestSubmit();}});
$$('[data-example]').forEach(button=>button.addEventListener('click',()=>{$('#chat-input').value=button.dataset.example;$('#chat-input').focus();}));
$('#generate').addEventListener('click',generatePlan);$('#empty-generate').addEventListener('click',generatePlan);
$('#horizon').addEventListener('change',markChanged);$('#start-year').addEventListener('change',markChanged);
$('#math-qualified').addEventListener('change',markChanged);$('#allow-unpublished').addEventListener('change',markChanged);
$$('[data-view]').forEach(button=>button.addEventListener('click',()=>{if(!state.plan)return;state.view=button.dataset.view;state.timetableToken++;renderPlan();}));
$('#plan-content').addEventListener('click',event=>{
  const semester=event.target.closest('[data-timetable]');
  if(semester){state.view='weekly';$$('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));renderWeeklyShell(Number(semester.dataset.timetable));loadTimetable();}
  if(event.target.closest('#load-timetable'))loadTimetable();
});
$('#plan-content').addEventListener('change',event=>{if(event.target.id==='weekly-semester'){state.timetableToken++;$('#timetable-share').hidden=true;$('#weekly-content').innerHTML='';$('#weekly-status').hidden=true;$('#load-timetable').disabled=false;}});
$('#export').addEventListener('click',()=>{if(!canExportPlan())return;$('#export-dialog').showModal();});
$('#download-plan').addEventListener('click',downloadPlan);
const categoryLabels={all:'All courses',ID:'ID',CD:'CD',GEA:'GEA',GEC:'GEC',GESS:'GESS',GEN:'GEN'};
let catalogueFilter='all';
function renderCatalogue() {
  const query=$('#catalogue-search').value.trim().toLowerCase();
  const descriptions={ID:'interdisciplinary',CD:'cross disciplinary',GEA:'data literacy',GEC:'cultures connections',GESS:'singapore studies',GEN:'communities engagement'};
  const courses=state.config.catalogue.filter(c=>(catalogueFilter==='all'||(c.categories||[]).includes(catalogueFilter)) &&
    `${c.code} ${c.title} ${(c.categories||[]).map(g=>`${g} ${descriptions[g]||''}`).join(' ')}`.toLowerCase().includes(query));
  $('#catalogue-filters').innerHTML=Object.entries(categoryLabels).map(([key,label])=>`<button data-category="${key}" aria-pressed="${key===catalogueFilter}">${label} <small>${key==='all'?state.config.catalogue.length:state.config.catalogue.filter(c=>(c.categories||[]).includes(key)).length}</small></button>`).join('');
  $('#catalogue-result-count').textContent=`${courses.length} courses · Reference AY${state.config.reference_year} · Search by code, title or category`;
  $('#catalogue-results').innerHTML=courses.map(c=>`<article class="catalogue-result"><div><h3>${escapeHTML(c.code)} · ${escapeHTML(c.title)}</h3><p>${c.units} units · Offered in semester${c.semesters.length>1?'s':''} ${c.semesters.join(', ')}</p><div class="catalogue-tags">${(c.categories||[]).map(g=>`<span>${escapeHTML(g)}</span>`).join('')}</div>${c.eligibility_note?`<p class="catalogue-browse-only">${escapeHTML(c.eligibility_note)}</p>`:''}<p><a href="${escapeHTML(c.nusmods_url||`https://nusmods.com/courses/${c.code}`)}" target="_blank" rel="noopener">NUSMods ↗</a>${(c.source_urls||[]).slice(0,1).map(url=>`<a href="${escapeHTML(url)}" target="_blank" rel="noopener">Category source ↗</a>`).join('')}</p></div><button class="secondary" data-choose-course="${escapeHTML(c.code)}" ${c.planner_eligible===false?'disabled':''}>Add to plan ＋</button></article>`).join('')||'<p>No matching courses. Try another code or category.</p>';
}
$('#browse-courses').addEventListener('click',()=>{if(!state.config)return;renderCatalogue();$('#catalogue-dialog').showModal();$('#catalogue-search').focus();});
$('#catalogue-search').addEventListener('input',renderCatalogue);
$('#catalogue-filters').addEventListener('click',event=>{const button=event.target.closest('[data-category]');if(button){catalogueFilter=button.dataset.category;renderCatalogue();}});
$('#catalogue-results').addEventListener('click',event=>{
  const button=event.target.closest('[data-choose-course]');if(!button||state.busy)return;
  $('#catalogue-dialog').close();openConstraintDialog();$('#field-course').value=button.dataset.chooseCourse;
});
document.addEventListener('click',event=>{
  if(prefersReducedMotion()||!event.target.closest('button:not(:disabled)'))return;
  const button=event.target.closest('button'),rect=button.getBoundingClientRect(),ring=document.createElement('span');
  ring.className='action-feedback';ring.setAttribute('aria-hidden','true');ring.style.left=`${event.clientX||rect.left+rect.width/2}px`;ring.style.top=`${event.clientY||rect.top+rect.height/2}px`;document.body.append(ring);setTimeout(()=>ring.remove(),600);
});
init();
