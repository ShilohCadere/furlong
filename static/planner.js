/* Furlong's continuous workspace. All edits pass through the same durable queue. */
(async()=>{
'use strict';
const C=window.FurlongCore,tid=Number(document.body.dataset.tripId),app=document.getElementById('app'),editor=document.getElementById('editor');
let bundle=null,S,U,sid,view='plan',settingsTab='display',travelWhole=false,mapDay='',ideaSearch='',ideaType='',ideaCity='',ideaScope='trip',ideaFavorites=false,ideaList=true,taskBoard=true;
let rates={rates:{USD:1},asOf:null},queue=[],undo=[],syncing=false,syncError='',db,saveChain=Promise.resolve(),flushTimer,activeReturn=null,mapInstance=null,editorTimer,offlineReady=false;
const planDisclosures=new Map();
const colors=[['#8fc9b0','#124638'],['#99b9e7','#18345b'],['#bea0d9','#43265b'],['#91c6cf','#16424d'],['#ddc28a','#4c391d'],['#c99b7d','#493326']];
const cityColors={dublin:colors[0],galway:colors[1],doolin:colors[1],edinburgh:colors[2],inverness:colors[3],glasgow:colors[3],london:colors[4],glencoe:colors[3],portree:['#eca9bd','#51273e']};
const text=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const attr=text,vals=C.values,alive=C.alive,uid=C.uid,copy=C.clone;
const prefs=()=>U?.preferences?.display||{};
const fx=()=>S.meta.rateLock?.base===S.meta.currency?S.meta.rateLock.rates:rates.base===S.meta.currency?rates.rates:{[S.meta.currency]:1};
const money=(n,cur=S?.meta.currency||'USD')=>n===null||n===undefined?'Unknown':new Intl.NumberFormat(undefined,{style:'currency',currency:cur,maximumFractionDigits:Math.abs(n)<100?2:0}).format(n);
const today=()=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const localDate=(when,zone)=>{try{return new Intl.DateTimeFormat('en-CA',{timeZone:zone||undefined,year:'numeric',month:'2-digit',day:'2-digit'}).format(when);}catch(_){return today();}};
const shortDate=d=>d?new Date(d+'T12:00:00Z').toLocaleDateString(undefined,{month:'short',day:'numeric',timeZone:'UTC'}):'Dates open';
const dateSpan=(a,b)=>a?shortDate(a)+(b&&a!==b?' – '+shortDate(b):''):'Dates open';
const title=o=>C.title(o,U),activeScenario=()=>S.scenarios[sid],scenarios=()=>vals(S.scenarios).filter(alive);
const optButton=(label,action,data='',className='small')=>`<button type="button" class="${className}" data-action="${action}" ${data}>${label}</button>`;
const empty=(heading,body,button='')=>`<div class="empty"><h3>${text(heading)}</h3><p>${text(body)}</p>${button}</div>`;
function color(name,index=0){const key=String(name||'').toLowerCase();if(cityColors[key])return cityColors[key];let n=0;for(const ch of key)n=(n*31+ch.charCodeAt(0))>>>0;return colors[key?n%colors.length:index%colors.length];}
const colorAttr=(name,index)=>{const [c,b]=color(name,index);return `style="--city:${c};--city-bg:${b}"`;};
function toast(message){const el=document.getElementById('toast');el.textContent=message;el.style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.style.display='none',5000);}
function openDB(){return new Promise((resolve,reject)=>{const req=indexedDB.open('furlong-planner-v2',1);req.onupgradeneeded=()=>{req.result.createObjectStore('documents');};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
function storeGet(key){return new Promise((resolve,reject)=>{const tx=db.transaction('documents');const r=tx.objectStore('documents').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
function storePut(key,value){return new Promise((resolve,reject)=>{const tx=db.transaction('documents','readwrite');tx.objectStore('documents').put(value,key);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);});}
function persist(){if(!db||!bundle)return Promise.resolve();const snapshot=copy({...bundle,state:S,user:U,queue,undo:undo.slice(-20),rates,offlineReady});saveChain=saveChain.then(()=>storePut(bundle.userId+':'+tid,snapshot)).catch(()=>{syncError='Browser storage is full or unavailable. Keep this page open until changes sync.';updateSync();});return saveChain;}
function integrate(data){bundle=data;S=data.state;U=data.user;for(const op of queue)C.patch(op.scope==='user'?U:S,op);}
function addChanges(changes,label='Edit',saveUndo=true){const ops=[],inverses=[];for(const [collection,id,next,scope='trip'] of changes){const doc=scope==='user'?U:S,before=collection==='meta'?doc.meta:doc[collection][id],op=C.operations(scope,collection,id,before,next);if(!op)continue;ops.push(op);inverses.unshift([collection,id,before?copy(before):{...copy(next),archived:true},scope]);C.patch(doc,op);}
if(!ops.length)return;queue.push(...ops);if(saveUndo)undo.push({label,changes:inverses,opIds:ops.map(o=>o.opId)});syncError='';persist();updateSync();clearTimeout(flushTimer);flushTimer=setTimeout(flush,400);}
function editEntity(collection,id,patch,scope='trip',label='Edit'){const doc=scope==='user'?U:S,before=collection==='meta'?doc.meta:doc[collection][id];if(!before)throw Error('This item is no longer available.');addChanges([[collection,id,{...copy(before),...patch},scope]],label);}
function updateSync(){document.querySelectorAll('[data-sync]').forEach(el=>{el.textContent=syncError?'Needs review':!navigator.onLine?(queue.length?`Offline · ${queue.length} pending`:'Offline · saved locally'):syncing?'Saving…':queue.length?`${queue.length} pending`:'Saved';el.classList.toggle('pending',Boolean(queue.length||syncError||!navigator.onLine));});const undoButton=document.querySelector('[data-action="undo"]');if(undoButton)undoButton.disabled=!undo.length;}
async function requestAPI(path,options={}){const response=await fetch(path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),'X-CSRF-Token':bundle?.csrf||'',...options.headers}});if(response.redirected&&response.url.includes('/login'))throw Error('Sign in again to sync. Your offline changes are retained.');return response;}
async function flush(){if(syncing||!queue.length||!navigator.onLine||document.getElementById('conflict-dialog').open)return;syncing=true;updateSync();const sent=queue.slice(0,2000);try{const response=await requestAPI(`/api/planner/${tid}/sync`,{method:'POST',body:JSON.stringify({operations:sent})});if(response.status===409){const data=await response.json();showConflicts(data);return;}if(!response.ok){const body=await response.text();throw Error(body.replace(/<[^>]*>/g,' ').trim().slice(-250)||'Changes could not sync.');}const data=await response.json();const acknowledged=new Set(sent.map(o=>o.opId));queue=queue.filter(o=>!acknowledged.has(o.opId));integrate(data);await persist();}catch(error){syncError=error.message;if(navigator.onLine)toast(error.message);}finally{syncing=false;updateSync();if(queue.length&&!syncError&&!document.getElementById('conflict-dialog').open)setTimeout(flush,200);}}
function showConflicts(data){const dialog=document.getElementById('conflict-dialog');dialog.innerHTML=`<div class="editor-header"><div><span class="eyebrow">BOTH VERSIONS ARE SAFE</span><h2 id="conflict-title">Resolve overlapping edits</h2></div></div><div class="editor-body"><p class="muted">Unrelated changes combine automatically. Choose which value to keep for each field below.</p><form id="resolve-conflicts">${data.conflicts.map((c,i)=>`<div class="conflict"><strong>${text(c.field)}</strong><label><input type="radio" name="conflict-${i}" value="mine" checked> My change</label><pre>${text(typeof c.mine==='object'?JSON.stringify(c.mine,null,2):c.mine)}</pre><label><input type="radio" name="conflict-${i}" value="theirs"> Latest saved change</label><pre>${text(typeof c.theirs==='object'?JSON.stringify(c.theirs,null,2):c.theirs)}</pre></div>`).join('')}<button class="primary">Keep choices & sync</button></form></div>`;dialog.showModal();dialog.querySelector('form').onsubmit=e=>{e.preventDefault();data.conflicts.forEach((conflict,i)=>{const op=queue.find(o=>o.opId===conflict.opId);if(!op)return;const choice=new FormData(e.target).get('conflict-'+i);if(conflict.field==='record'){if(choice==='mine')op.create=true;else op.patch={};}else{op.base[conflict.field]=conflict.theirs;if(choice==='theirs')delete op.patch[conflict.field];}});queue=queue.filter(o=>Object.keys(o.patch).length);integrate(data);dialog.close();syncError='';persist();render();flush();};}
function undoLast(){const item=undo.pop();if(!item)return;const ids=new Set(item.opIds);if(!syncing&&item.opIds.every(id=>queue.some(op=>op.opId===id))){queue=queue.filter(op=>!ids.has(op.opId));for(const [col,id,prior,scope] of item.changes){const doc=scope==='user'?U:S;if(col==='meta')doc.meta=prior;else doc[col][id]=prior;}persist();}else addChanges(item.changes,'Undo '+item.label,false);render();toast('Undid '+item.label);}
function showEditor(heading,html,subtitle=''){clearTimeout(editorTimer);const pending=editor.pendingSave;editor.pendingSave=null;if(pending)pending();activeReturn=document.activeElement;editor.innerHTML=`<div class="editor-header"><div><span class="eyebrow">${text(subtitle||'YOUR WORKING JOURNEY')}</span><h2 id="editor-title">${text(heading)}</h2></div><button type="button" data-close-editor aria-label="Close editor">×</button></div><div class="editor-body">${html}</div>`;if(!editor.open)editor.showModal();editor.querySelector('[data-close-editor]').onclick=()=>editor.close();editor.querySelector('input,select,textarea,button')?.focus();}
editor.addEventListener('close',()=>{clearTimeout(editorTimer);if(editor.pendingSave){editor.pendingSave();editor.pendingSave=null;}if(activeReturn?.isConnected)activeReturn.focus();});
editor.addEventListener('click',e=>{if(e.target===editor)editor.close();});
function formValues(form){const result={};for(const input of form.querySelectorAll('[name]')){if(input.type==='checkbox')result[input.name]=input.checked;else if(input.type==='number')result[input.name]=input.value===''?null:Number(input.value);else result[input.name]=input.value;}return result;}
function field(label,name,value='',kind='text',extra=''){return `<label>${text(label)}${kind==='textarea'?`<textarea name="${attr(name)}" ${extra}>${text(value)}</textarea>`:`<input name="${attr(name)}" type="${kind}" value="${attr(value)}" ${kind==='number'?'step="any"':''} ${extra}>`}</label>`;}
function select(label,name,value,choices,extra=''){return `<label>${text(label)}<select name="${attr(name)}" ${extra}>${choices.map(([v,t])=>`<option value="${attr(v)}" ${String(v)===String(value)?'selected':''}>${text(t)}</option>`).join('')}</select></label>`;}
function directLink(item,ideaId=item.ideaId){
 const url=item.website||U.ideas[ideaId]?.website||'';
 try{if(['http:','https:'].includes(new URL(url).protocol))return url;}catch(_){}
 return '';
}
function linkActions(item,action,id,part=''){
 const url=directLink(item);
 return `<div class="add-row">${url?`<a href="${attr(url)}" target="_blank" rel="noopener noreferrer">Open direct link ↗</a>`:''}${optButton(url?'Edit link':'Add link',action,`data-id="${id}" ${part?`data-part="${part}"`:''}`)}</div>`;
}
function linkField(value=''){
 return field('Direct link','website',value,'url','maxlength="2048" pattern="https?://.+"');
}
function dayChoices(scenarioId){
 return vals(S.days).filter(d=>alive(d)&&d.scenarioId===scenarioId).sort((a,b)=>(dayDate(a)||'9999').localeCompare(dayDate(b)||'9999')||C.byPosition(a,b)).map(d=>[d.id,(dayDate(d)?shortDate(dayDate(d)):'Day '+(Number(d.position||0)+1))+' · '+(S.stops[d.stopId]?.name||'Unassigned')]);
}
function quoteAmountFields(q,prefix='',label='Quoted price (optional)'){
 return field(label,prefix+'amount',q.amount??'','number','min="0" max="1000000000"')+
  field('Currency',prefix+'currency',q.currency||S.meta.currency,'text','required minlength="3" maxlength="3" pattern="[A-Za-z]{3}"');
}
function quoteFields(q,prefix='',includeAmount=true){
 return `<div class="form-grid">${includeAmount?quoteAmountFields(q,prefix):''}${select('Pricing basis',prefix+'basis',q.basis||'total',[['total','Total for the group'],['person','Per person'],['room-night','Per room, per night'],['vehicle-day','Per vehicle, per day'],['unit','Custom unit']])}${field('People / rooms / vehicles / units',prefix+'quantity',q.quantity??1,'number','required min="0.01" max="1000000000"')}${field('Nights / days / repetitions',prefix+'units',q.units??1,'number','required min="0.01" max="1000000000"')}</div>`;
}
const templates=()=>vals(U.templates).filter(x=>!x.archived).map(x=>[x.id,x.name]);
function autosave(form,callback){let dirty=false;const save=()=>{if(!dirty)return;if(!form.reportValidity())return;dirty=false;callback(formValues(form));editor.querySelector('[data-editor-saved]')?.replaceChildren(document.createTextNode('Saved to working plan.'));};form.addEventListener('input',()=>{dirty=true;clearTimeout(editorTimer);editorTimer=setTimeout(save,600);});form.addEventListener('change',()=>{dirty=true;clearTimeout(editorTimer);save();});form.addEventListener('submit',e=>{e.preventDefault();dirty=true;save();});editor.pendingSave=save;}
function regionTime(st){return st?.timeZone||(['Dublin','Galway'].includes(st?.location)?'Europe/Dublin':['London','Edinburgh','Glasgow','Inverness','Glencoe'].includes(st?.location)?'Europe/London':Intl.DateTimeFormat().resolvedOptions().timeZone);}
function dayDate(d){if(d.date)return d.date;const st=S.stops[d.stopId];return st?.startDate?C.datePlus(st.startDate,Number(d.position||0)):null;}
function summary(o){const tpl=U.templates[o.type]||U.templates.idea;return (tpl.summaryFields||[]).map(k=>o.fields?.[k]).filter(v=>v!==null&&v!==undefined&&v!=='').map(text).join(' · ');}
function notesHTML(item){return C.itemNotes(item,U,S).map(n=>`<p class="option-note">${text(n)}</p>`).join('');}
function activityPrice(a){const o=S.options[a.optionId];if(!alive(o)||o.scenarioId!==a.scenarioId)return '';const c=C.cost(S,o,fx()),selected=S.groups[o.groupId]?.selectedId===o.id;return `<small class="activity-price">${c.unknown?'Quote needed':money(c.amount)} · ${selected?'Included in budget':'Quote only; not in budget'}${c.provisional?' · Recheck quote':''}</small>`;}
function optionPartsHTML(option){
 const parts=option.parts||[];
 const optionAttrs=`data-id="${attr(option.id)}"`;
 return `<div class="option-parts">
  ${parts.length?`<ol class="option-part-list" aria-label="Option parts">${parts.map(part=>{
   const mode=part.fields?.mode||U.templates[part.type]?.name||part.type;
   return `<li><button type="button" class="option-part-link" data-action="part" ${optionAttrs} data-part="${attr(part.id)}">
    <span>${text(part.name)}</span><small class="muted">${text(mode)}</small>
   </button></li>`;
  }).join('')}</ol>`:''}
  ${optButton('+ Add a part','add-part',optionAttrs,'small')}
 </div>`;
}
function optionCard(o,g){const c=C.cost(S,o,fx()),q=o.quote,b=C.booking(S,o);const name=title(o);return `<article class="option-card ${g.selectedId===o.id?'selected':''}" id="item-${o.id}"><div class="option-main"><div class="option-status"><span class="badge ${b?'booked':g.selectedId===o.id?'selected':''}">${text(C.status(S,o,g))}</span>${c.provisional?'<span class="badge provisional">* Recheck</span>':''}</div><h4>${text(name)}</h4><div class="option-details">${text(dateSpan(o.fields?.startDate,o.fields?.endDate))}</div><div class="option-secondary option-details">${summary(o)}</div></div><div class="option-price">${c.unknown?'Quote needed':money(c.amount)}${c.provisional?'*':''}<small>${q?.amount!=null?money(C.quoteTotal(q),q.currency)+' · '+text(q.basis==='total'?'total quote':'unit pricing'):'Group estimate'}${c.unknown&&c.amount?' · '+money(c.amount)+' known':''}</small></div><div class="option-actions">${g.selectedId===o.id?optButton('Selected','unselect',`data-id="${g.id}"`):optButton('Select','select',`data-id="${o.id}"`,'small choose')}${optButton('Edit','option',`data-id="${o.id}"`)}${['activity','restaurant'].includes(o.type)?optButton('Schedule','schedule-option',`data-id="${o.id}"`):''}${optButton('···','option-more',`data-id="${o.id}"`,'small quiet')}</div>${o.parts?.length||['transport','flight'].includes(o.type)?optionPartsHTML(o):''}${notesHTML(o)}</article>`;}
function groupCard(g){const opts=C.options(S,g.id),emptyJourney=!opts.length&&!g.stopId&&['transport','flight'].includes(g.type);return `<section class="decision-group" id="group-${g.id}"><div class="group-heading"><h3>${text(g.name)} <small>${opts.length} ${opts.length===1?'option':'options'}</small></h3>${optButton(g.type==='flight'?'Route & placement':'Group settings','group',`data-id="${g.id}"`,'small quiet')}</div>${g.notes?`<p class="option-note">${text(g.notes)}</p>`:''}<div class="option-list">${opts.length?opts.map(o=>optionCard(o,g)).join(''): `<div class="group-empty"><span>No options yet.${g.allowance!=null?' Allowance: '+money(g.allowance):' Keep researching here.'}</span><div class="option-actions">${optButton('+ Add option','add-option',`data-group="${g.id}"`,'small')}${emptyJourney?optButton('Remove empty group','archive-group',`data-id="${g.id}"`,'small quiet'):''}</div></div>`}</div><div class="add-row">${opts.length?optButton('+ Add option','add-option',`data-group="${g.id}"`):''}${optButton('Use saved idea','pick-idea',`data-group="${g.id}"`)}</div></section>`;}
function activityOrder(a,b){const minutes=x=>{if(/^\d\d:\d\d$/.test(x.time||''))return Number(x.time.slice(0,2))*60+Number(x.time.slice(3));const block=(prefs().timeBlocks||[]).find(t=>t.name===x.timeBlock);if(block?.start)return Number(block.start.slice(0,2))*60+Number(block.start.slice(3));return 2000;};return minutes(a)-minutes(b)||(a.position||0)-(b.position||0);}
function planDisclosure(key,initial=false){
 return `data-plan-disclosure="${attr(key)}" ${(planDisclosures.get(key)??initial)?'open':''}`;
}
function firstPlanDay(){
 const stopIds=new Set(C.stops(S,sid).map(stop=>stop.id));
 const days=vals(S.days).filter(day=>alive(day)&&day.scenarioId===sid&&stopIds.has(day.stopId))
  .sort((a,b)=>(dayDate(a)||'9999').localeCompare(dayDate(b)||'9999')||C.byPosition(a,b));
 const now=today();
 return days.find(day=>dayDate(day)&&dayDate(day)>=now)||days[0];
}
function dayCard(d,initial){
 const activities=vals(S.activities).filter(x=>alive(x)&&x.dayId===d.id).sort(activityOrder),date=dayDate(d);
 return `<details class="day" id="day-${attr(d.id)}" ${planDisclosure('day-'+d.id,initial)}>
 <summary class="plan-summary">
  <span class="plan-summary-title"><span class="plan-day-date">${text(date?shortDate(date):'Day '+(Number(d.position||0)+1))}</span>
  <strong>${text(d.title||'Open day')}</strong></span><span class="plan-summary-meta">${activities.length} ${activities.length===1?'activity':'activities'}</span>
 </summary>
 <div class="plan-day-content">${notesHTML(d)}
 ${activities.map(a=>`<div class="activity"><span class="time">${text(a.time||a.timeBlock||'Anytime')}</span><button data-action="activity" data-id="${a.id}">${text(a.name||U.ideas[a.ideaId]?.name)}${a.confirmed?'<small>Confirmed</small>':''}${activityPrice(a)}</button>${notesHTML(a)}</div>`).join('')}
 <div class="add-row">${optButton('+ Activity','add-activity',`data-day="${d.id}"`)}${optButton('Use saved item','day-idea',`data-day="${d.id}"`)}${optButton('Edit day','day',`data-id="${d.id}"`,'small quiet')}</div></div></details>`;
}
function stopCard(st,firstDay,initial){
 const groups=C.groups(S,sid,st.id);
 const days=vals(S.days).filter(d=>alive(d)&&d.stopId===st.id).sort(C.byPosition);
 const range=dateSpan(st.startDate,st.startDate?C.datePlus(st.startDate,Number(st.nights||0)):'');
 const nights=st.nights==null?'Nights open':`${st.nights} ${Number(st.nights)===1?'night':'nights'}`;
 return `<section class="stop" id="stop-${attr(st.id)}" ${colorAttr(st.location||st.name)} draggable="true" data-stop-id="${attr(st.id)}">
 <details ${planDisclosure('stop-'+st.id,initial)}>
  <summary class="plan-summary plan-stop-summary"><span class="plan-summary-title"><span class="plan-stop-name">${text(st.name)}</span><span class="plan-nights">${nights}</span></span><span class="plan-summary-meta">${text(range)}</span></summary>
  <div class="plan-stop-content"><div class="stop-actions plan-stop-actions">
  <button class="drag-handle" aria-label="Drag ${attr(st.name)} to reorder" title="Drag to reorder">⠿</button>
  ${optButton('Move to…','move-stop',`data-id="${st.id}"`)}${optButton('Edit stop','stop',`data-id="${st.id}"`)}${optButton('Copy','copy-stop',`data-id="${st.id}"`,'small quiet')}</div>
  ${st.notes?`<p class="option-note plan-stop-note">${text(st.notes)}</p>`:''}
  ${groups.map(groupCard).join('')}
  ${days.length?`<div class="group-heading"><h3>Days in ${text(st.name)}</h3>${optButton('+ Day','add-day',`data-stop="${st.id}"`)}</div><div class="day-grid">${days.map(day=>dayCard(day,day.id===firstDay?.id)).join('')}</div>`:''}
  <div class="add-row">${optButton('+ Decision group','add-group',`data-stop="${st.id}"`)}${!days.length?optButton('+ Plan a day','add-day',`data-stop="${st.id}"`):''}</div></div>
 </details></section>`;
}
function attentionHTML(){const issues=C.notices(S,U,sid,fx());return `<div class="attention-summary"><h3>Needs attention</h3><span class="count">${issues.length}</span></div><div class="notice-list">${issues.length?issues.map((n,i)=>`<article class="notice"><button data-action="notice" data-index="${i}"><strong>${text(n.name)} ↗</strong><p>${text(n.detail)}</p></button><button class="dismiss" data-action="dismiss" data-index="${i}">Mark intentional / dismiss</button></article>`).join(''):'<p class="notice-empty">No detected issues. Your open ideas can stay open.</p>'}</div>`;}
function budgetRail(){const b=C.budget(S,sid,fx());return `<section class="rail-card rail-budget"><h3>Working budget</h3><div class="metric-line"><span>Current estimate${b.provisional?'*':''}</span><strong>${money(b.amount)}</strong></div><div class="metric-line"><span>Recorded payments</span><strong>${money(b.paid)}</strong></div><div class="metric-line"><span>Food allowance</span><strong>${money(activeScenario()?.foodAllowance||0)}</strong></div><div class="metric-line total"><span>Room to roam</span><strong class="${b.remaining<0?'negative':''}">${money(b.remaining)}</strong></div>${b.unknown?`<p class="muted" style="margin-top:9px">${b.unknown} missing ${b.unknown===1?'price':'prices'} or conversions. Total incomplete.</p>`:''}${b.provisional?'<p class="muted" style="margin-top:9px">* Includes previous quotes to recheck.</p>':''}<div class="add-row">${optButton('Budget details','view', 'data-view="budget"')}</div></section>`;}
function relevantTasks(){return vals(S.tasks).filter(t=>alive(t)&&(!t.scenarioId||t.scenarioId===sid)&&t.status!=='Done').sort((a,b)=>(a.dueDate||'9999').localeCompare(b.dueDate||'9999'));}
function taskRail(){if(!prefs().tasksEnabled)return '';return `<section class="rail-card rail-tasks"><h3>Planning tasks</h3>${relevantTasks().slice(0,5).map(t=>`<div class="activity"><button data-action="task" data-id="${t.id}">${text(t.name)}<small>${text(t.dueDate||'No due date')}</small></button></div>`).join('')||'<p class="muted">Make space for the decisions you want to come back to.</p>'}<div class="add-row">${optButton('+ Task','add-task')}</div></section>`;}
function transfers(){return C.groups(S,sid).filter(g=>!g.stopId);}
function planHTML(){
 const stops=C.stops(S,sid),slots=C.journeySlots(S,sid),firstDay=firstPlanDay();
 const connected=new Set(transfers().map(group=>C.connectionStops(stops,group)?.[0].id).filter(Boolean));
 const journey=group=>{
  const options=C.options(S,group.id);
  const pair=C.connectionStops(stops,group);
  const from=pair?.[0]||stops.find(stop=>stop.id===group.fromStopId);
  const to=pair?.[1]||stops.find(stop=>stop.id===group.toStopId);
  const surface=(stop,fallback)=>stop?color(stop.location||stop.name)[1]:fallback;
  const selected=options.find(option=>option.id===group.selectedId);
  const representative=selected||options[0];
  const parts=representative?.parts||[];
  const modes=parts.map(part=>part.fields?.mode||U.templates[part.type]?.name||part.type);
  const context=parts.length?`${parts.length} ${parts.length===1?'leg':'legs'} · ${modes.join(' → ')}`:
   `${options.length} ${options.length===1?'option':'options'}`;
  const date=parts.find(part=>part.fields?.startDate)?.fields.startDate||representative?.fields?.startDate||group.startDate;
  return `<section class="transfer" id="journey-${attr(group.id)}" style="--from:${surface(from,'#152d40')};--to:${surface(to,'#302440')}">
   <details ${planDisclosure('journey-'+group.id,Boolean(parts.length))}>
    <summary class="plan-summary plan-journey-summary"><span class="plan-summary-title"><strong>${text(group.name)}</strong>${date?`<span class="plan-nights">${text(shortDate(date))}</span>`:''}</span><span class="plan-summary-meta">${text(context)}</span></summary>
    <div class="plan-journey-content">${groupCard(group)}</div>
   </details></section>`;
 };
 let body=slots.before.map(journey).join('');
 for(const [i,stop] of stops.entries()){
  body+=stopCard(stop,firstDay,firstDay?stop.id===firstDay.stopId:i===0);
  const next=stops[i+1];
  body+=slots.after[stop.id].map(journey).join('');
  if(next&&!connected.has(stop.id))body+=`<div class="add-row plan-connection-action">${optButton('+ Compare transport to '+text(next.name),'add-connection',`data-from="${stop.id}" data-to="${next.id}"`)}</div>`;
 }
 if(slots.shared.length)body+=`<div class="section-title"><div><h2>Journeys & shared transport</h2><p>Add travel dates or choose itinerary placement in group settings.</p></div></div>${slots.shared.map(journey).join('')}`;
 if(!stops.length)body=empty('Start anywhere','Add a stop, save a possibility, or leave the dates open.',optButton('+ Add a stop','add-stop','','primary'))+body;
 return `<section class="plan-workspace" aria-labelledby="plan-title">
  <div class="plan-heading"><h2 id="plan-title">Itinerary</h2>${stops.length?optButton('+ Add to plan','plan-activity','','small primary'):''}</div>
  <div class="plan-timeline">${body}</div>
  <div class="add-row">${optButton('+ Add stop','add-stop','','primary')}${optButton('+ Shared transport','add-group','data-type="transport"')}</div>
  <details class="plan-overview" ${planDisclosure('summary-'+sid)}><summary class="plan-summary">Planning summary</summary>
   <aside class="rail">${budgetRail()}<section class="rail-card">${attentionHTML()}</section>${taskRail()}</aside>
  </details>
 </section>`;
}
function ideasHTML(){
const linkedIdeas=new Set(vals(S.options).map(option=>option.ideaId));
for(const activity of vals(S.activities))if(activity.ideaId)linkedIdeas.add(activity.ideaId);
const all=vals(U.ideas).filter(idea=>alive(idea)&&(ideaScope==='all'||idea.originTripId===tid||linkedIdeas.has(idea.id)));
const stops=C.stops(S,sid),route=[...new Set(stops.map(st=>(st.location||st.name||'').trim()).filter(Boolean))];
const known=[...new Set([...route,'Dublin','Galway','Edinburgh','Inverness','Glasgow','Glencoe','London','Stonehenge'])];
const transferPattern=/\b(flight|airline|airport|train|rail|coach|bus|ferry|transfer|transport|car rental|car hire|rental car)\b/i;
const normalize=i=>{
 const raw=(i.location||'').trim(),label=[raw,i.name].join(' ');
 const type=(U.templates[i.type]?.name||i.type||'').toLowerCase();
 const words=raw.toLowerCase().split(/[^a-z]+/).filter(Boolean);
 const matches=known.filter(city=>words.join(' ').includes(city.toLowerCase()));
 const routePair=matches.length>1||/\bto\b|→|–| - /i.test(raw)&&matches.length>0;
 const isTransfer=transferPattern.test(type)||routePair||transferPattern.test(raw)||(/\bto\b|→/i.test(label)&&transferPattern.test(label));
 if(isTransfer)return 'Transfers';
 if(matches.length)return matches[0];
 if(/^ireland$|^scotland$|^england$|^uk$|^united kingdom$/i.test(raw))return 'Regional research';
 return raw||'Unassigned';
};
const order=[...route,'Transfers','Regional research','Unassigned'];
const keys=[...new Set(all.map(normalize))].sort((a,b)=>{const x=order.findIndex(k=>k.toLowerCase()===a.toLowerCase()),y=order.findIndex(k=>k.toLowerCase()===b.toLowerCase());return (x<0?999:x)-(y<0?999:y)||a.localeCompare(b);});
const filtered=all.filter(i=>(!ideaFavorites||i.favorite)&&(!ideaType||i.type===ideaType)&&(!ideaCity||normalize(i)===ideaCity)&&[i.name,i.location,i.notes,i.website].join(' ').toLowerCase().includes(ideaSearch.toLowerCase())).sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||''));
const unique=new Map();let duplicateCount=0;
const tidy=v=>String(v||'').normalize('NFKC').trim().toLowerCase().replace(/\s+/g,' ');
const quality=i=>(i.website?2:0)+(i.notes?1:0)+(i.image?1:0)+(i.favorite?1:0);
for(const idea of filtered){
 // Same city + type + property name identifies one research idea, regardless of imported URL or notes.
 const key=[tidy(normalize(idea)),tidy(idea.type),tidy(idea.name)].join('|');
 if(!unique.has(key)){unique.set(key,idea);continue;}
 duplicateCount++;
 if(quality(idea)>quality(unique.get(key)))unique.set(key,idea);
}
const ideas=[...unique.values()];
const grouped=new Map();for(const idea of ideas){const city=normalize(idea),type=U.templates[idea.type]?.name||idea.type||'Other';if(!grouped.has(city))grouped.set(city,new Map());const categories=grouped.get(city);if(!categories.has(type))categories.set(type,[]);categories.get(type).push(idea);}
const card=i=>`<article class="idea-card idea-compact" ${colorAttr(normalize(i)||i.type)}><div class="idea-body"><div><span class="eyebrow">${i.favorite?'♥ Favorite':''}</span><h3>${text(i.name)}</h3><p>${i.website?'Link saved':''}</p></div><div class="add-row">${optButton(i.favorite?'♥':'♡','favorite',`data-id="${i.id}"`,'small quiet')}${optButton('Edit','idea',`data-id="${i.id}"`)}${optButton('Use in a plan','use-idea',`data-id="${i.id}"`)}</div></div></article>`;
const typeOrder=['Flights','Flight','Transport','Transportation','Train','Rail','Coach','Hotels','Hotel','Accommodation','Activities','Activity','Excursions','Excursion','Restaurants','Restaurant'];
const rank=t=>{const n=typeOrder.findIndex(x=>x.toLowerCase()===t.toLowerCase());return n<0?999:n;};
const sections=keys.filter(city=>grouped.has(city)).map((city,index)=>{const categories=grouped.get(city),count=[...categories.values()].reduce((n,items)=>n+items.length,0);const blocks=[...categories.entries()].sort((a,b)=>rank(a[0])-rank(b[0])||a[0].localeCompare(b[0])).map(([type,items])=>`<section class="idea-category"><h4>${text(type)} <span>${items.length}</span></h4><div class="${ideaList?'idea-list':'idea-grid'}">${items.map(card).join('')}</div></section>`).join('');return `<details class="idea-city" ${ideaSearch||ideaCity||ideaType||ideaFavorites||index===0?'open':''} ${colorAttr(city)}><summary><strong>${text(city)}</strong><span>${count} saved · ${categories.size} categories</span></summary><div class="idea-city-content">${blocks}</div></details>`;}).join('');
return `<div class="section-title"><div><h2>${ideaScope==='all'?'All saved ideas':'Ideas for this trip'}</h2><p>${ideaScope==='all'?'Your reusable collection across trips. Use an idea in a plan to add it to this trip.':'Research saved here or used in this trip. Explore All saved ideas to reuse research from elsewhere.'}</p></div>${optButton('+ Save an idea','add-idea','','primary')}</div><div class="toolbar">${select('Idea collection','idea-scope',ideaScope,[['trip','This trip'],['all','All saved ideas']])}<input id="idea-search" aria-label="Search ideas" placeholder="Search ideas, places, notes" value="${attr(ideaSearch)}">${select('City / section','idea-city',ideaCity,[['','All sections'],...keys.map(c=>[c,c])])}${select('Type','idea-filter',ideaType,[['','All types'],...templates()])}${optButton(ideaFavorites?'♥ Favorites':'♡ Favorites','filter-favorites')}${optButton(ideaList?'Gallery':'List','idea-layout')}</div><p class="muted">${ideas.length} matching ideas${duplicateCount?' · '+duplicateCount+' exact duplicates hidden':''}</p>${sections||empty('No matching ideas','Try clearing the filters.')}`;
}
function tasksHTML(){const tasks=vals(S.tasks).filter(t=>alive(t)&&(!t.scenarioId||t.scenarioId===sid)),statuses=prefs().taskStatuses||['To do','In progress','Done'];return `<div class="section-title"><div><h2>Planning tasks</h2><p>Trip-wide decisions and tasks for ${text(activeScenario().name)}. Customize statuses and fields in Settings.</p></div><div class="header-actions">${optButton(taskBoard?'List view':'Board view','task-layout')}${optButton('+ Task','add-task','','primary')}</div></div>${taskBoard?`<div class="task-board">${statuses.map(status=>`<section class="task-column"><h3>${text(status)}</h3>${tasks.filter(t=>(t.status||statuses[0])===status).map(taskHTML).join('')||'<p class="muted">Nothing here yet.</p>'}</section>`).join('')}</div>`:`<div class="notice-list">${tasks.map(taskHTML).join('')}</div>`}`;}
function taskHTML(t){return `<article class="task-card"><button data-action="task" data-id="${t.id}"><strong>${text(t.name)}</strong></button><small>${t.scenarioId?text(S.scenarios[t.scenarioId]?.name):'Whole trip'}${t.dueDate?' · Due '+text(t.dueDate):''}</small>${t.stopId?optButton('Go to '+text(S.stops[t.stopId]?.name||'details'),'jump',`data-id="${t.stopId}"`,'small quiet'):''}</article>`;}
function compareHTML(){const baseline=C.stops(S,sid).map(s=>s.name).join(' → ');return `<div class="section-title"><div><h2>Choose your journey</h2><p>Independent alternatives, shared research. Compare what changes before committing.</p></div>${optButton('+ Alternative','new-scenario','','primary')}</div><div class="compare-grid">${scenarios().map((s,i)=>{const b=C.budget(S,s.id,fx()),st=C.stops(S,s.id),route=st.map(x=>x.name).join(' → '),dur=C.groups(S,s.id).map(g=>S.options[g.selectedId]).filter(alive).filter(o=>['transport','flight'].includes(o.type)).map(C.duration),issues=C.notices(S,U,s.id,fx()).length;return `<article class="compare-card" ${colorAttr('',i)}><span class="eyebrow">${s.id===S.meta.activeScenario?'ACTIVE TRAVEL PLAN':'WORKING ALTERNATIVE'}</span><h3>${text(s.name)}</h3><div class="metric-line"><span>Estimate${b.provisional?'*':''}</span><strong>${money(b.amount)}</strong></div><div class="metric-line"><span>Nights</span><strong>${st.reduce((n,x)=>n+Number(x.nights||0),0)}</strong></div><div class="metric-line"><span>Known travel time</span><strong>${dur.reduce((n,x)=>n+(x||0),0).toFixed(1)} h${dur.some(x=>x===null)?' + unknown':''}</strong></div><div class="metric-line"><span>Open issues</span><strong>${issues}</strong></div><div class="compare-route">${st.map(x=>`<div class="compare-stop" ${colorAttr(x.location||x.name)}>${text(x.name)} · ${x.nights??'?'} nights</div>`).join('')}</div>${route!==baseline?'<p class="compare-diff">Route differs from the currently viewed alternative.</p>':'<p class="muted">Same stop sequence as the viewed alternative.</p>'}${b.unknown?'<p class="muted">Some prices or conversions are missing.</p>':''}<div class="add-row">${optButton('Open plan','scenario',`data-id="${s.id}"`)}${optButton('Make active','activate-scenario',`data-id="${s.id}"`)}${optButton('Duplicate','duplicate-scenario',`data-id="${s.id}"`)}</div></article>`;}).join('')}</div>`;}
function bookingCard(b){const payments=vals(S.payments).filter(p=>alive(p)&&p.bookingId===b.id),paid=payments.reduce((n,p)=>n+(p.refund?-1:1)*Number(p.baseAmount||0),0),estimate=C.exchange(C.quoteTotal(b.quote),b.quote?.currency||S.meta.currency,S.meta.currency,fx());return `<article class="booking-card"><div class="row"><h3>${text(b.name)}</h3><span class="badge ${b.canceled?'':'booked'}">${b.canceled?'Canceled':'Booked'}</span></div><p class="muted">${text(dateSpan(b.fields?.startDate,b.fields?.endDate))}${b.reference?' · Reference '+text(b.reference):''}</p><div class="row"><span>Paid ${money(paid)}${estimate!==null?' · Estimated balance '+money(Math.max(0,estimate-paid)):''}</span>${b.balanceDue?`<span class="muted">Due ${text(b.balanceDue)}</span>`:''}</div>${b.cancellation?`<p class="muted">Cancellation: ${text(b.cancellation)}</p>`:''}<div class="file-list">${(b.attachments||[]).map(f=>`<a href="${attr(f.url)}" download>${text(f.name)} ↗</a>`).join('')}</div><div class="add-row">${optButton('Reservation details','booking',`data-id="${b.id}"`)}${optButton('+ Payment / refund','payment',`data-booking="${b.id}"`)}</div></article>`;}
let budgetTrial={sid:null,choices:{},extras:[],food:null};
function budgetHTML(){
 if(budgetTrial.sid!==sid)budgetTrial={sid,choices:{},extras:[],food:null};
 const sc=activeScenario(),base=C.budget(S,sid,fx()),seen=new Set(),missing=[];
 let total=budgetTrial.food===null?Number(sc.foodAllowance||0):budgetTrial.food;
 const budgetEntries=C.groups(S,sid).filter(g=>{const opts=C.options(S,g.id);return opts.length>0||g.allowance!=null||Boolean(g.selectedId&&S.options[g.selectedId]&&alive(S.options[g.selectedId]));}).map(g=>{
  const opts=C.options(S,g.id),override=Object.prototype.hasOwnProperty.call(budgetTrial.choices,g.id);
  const selected=override?budgetTrial.choices[g.id]:(g.selectedId||((g.allowance!=null)?'__allowance__':''));
  const o=opts.find(o=>o.id===selected);
  if(o){const c=C.cost(S,o,fx(),seen);total+=c.amount;if(c.unknown)missing.push(g.name);}
  else if(selected==='__allowance__')total+=Number(g.allowance||0);
  const choices=[['','No option selected'],...(g.allowance!=null?[['__allowance__','Use allowance · '+money(g.allowance)]]:[]),...opts.map(o=>[o.id,title(o)+' · '+(C.quoteTotal(o.quote)==null?'Quote needed':money(C.quoteTotal(o.quote),o.quote?.currency||S.meta.currency))])];
  return {group:g,html:`<div class="budget-choice"><label for="budget-choice-${attr(g.id)}">${text(g.name)}</label><select id="budget-choice-${attr(g.id)}" data-budget-choice="${attr(g.id)}">${choices.map(([id,label])=>`<option value="${attr(id)}" ${id===selected?'selected':''}>${text(label)}</option>`).join('')}</select></div>`};
 });
 const stops=C.stops(S,sid),stopName=id=>S.stops[id]?.name||S.stops[id]?.location||'',buckets=new Map();
 const typeName=t=>({hotel:'Accommodation',accommodation:'Accommodation',flight:'Flights',transport:'Transport',activity:'Activities',experience:'Activities',food:'Food',dining:'Food'}[String(t||'').toLowerCase()]||String(t||'Other').replace(/^./,c=>c.toUpperCase()));
 for(const entry of budgetEntries){const g=entry.group,route=g.fromStopId||g.toStopId,from=stopName(g.fromStopId),to=stopName(g.toStopId);let location=route?[from||'Departure',to||'Arrival'].join(' → '):stopName(g.stopId);if(!location){const match=stops.find(st=>g.name.toLowerCase().includes(st.name.toLowerCase()));location=match?.name||'Trip-wide';}const key=location,kind=typeName(g.type);if(!buckets.has(key))buckets.set(key,new Map());const types=buckets.get(key);if(!types.has(kind))types.set(kind,[]);types.get(kind).push(entry);}
 const cityOrder=stops.map(st=>st.name);const ordered=[...buckets.entries()].sort((a,b)=>{const rank=x=>{const i=cityOrder.indexOf(x);if(i>=0)return i;const first=x.split(' → ')[0],j=cityOrder.indexOf(first);return j>=0?j+.5:999;};return rank(a[0])-rank(b[0]);});
 const selectors=ordered.map(([location,types])=>`<section class="budget-city" ${colorAttr(location.split(' → ')[0])}><h3>${text(location)}</h3><div class="budget-types">${[...types.entries()].map(([kind,entries])=>`<div class="budget-type"><h4>${text(kind)}</h4><div class="budget-choice-list">${entries.map(e=>e.html).join('')}</div><div class="budget-category-actions">${optButton('+ Add option','add-option',`data-group="${attr(entries[0].group.id)}"`)}${optButton('Use saved idea','pick-idea',`data-group="${attr(entries[0].group.id)}"` )}</div></div>`).join('')}</div></section>`).join('');
 for(const e of vals(S.expenses).filter(x=>alive(x)&&x.scenarioId===sid&&!x.coveredByAllowance)){const c=C.cost(S,{id:e.id,expenseId:e.id,quote:{amount:e.amount,currency:e.currency||S.meta.currency,basis:'total'}},fx());total+=c.amount;if(c.unknown)missing.push(e.name);}
 total+=budgetTrial.extras.reduce((n,e)=>n+e.amount,0);
 const remaining=Number(sc.budget||0)-total;
 return `<div class="section-title"><div><h2>Budget</h2><p>Try different choices and costs. Experiments do not change your saved itinerary.</p></div></div>
 <div class="playground-summary"><div><small>PLANNING CEILING</small><strong>${money(sc.budget||0)}</strong></div><div><small>CURRENT PLAN</small><strong>${money(base.amount)}</strong></div><div><small>WORKING ESTIMATE</small><strong>${money(total)}</strong></div><div><small>REMAINING ROOM</small><strong class="${remaining<0?'negative':''}">${money(remaining)}</strong></div></div>
 <section class="playground-panel budget-food"><div class="playground-heading"><div><h2>Food allowance</h2><p>Included in your working estimate. You can adjust the allowance here.</p></div><label>Food budget (${text(S.meta.currency)})<input id="budget-food-input" type="number" min="0" step="0.01" value="${attr(budgetTrial.food===null?Number(sc.foodAllowance||0):budgetTrial.food)}"></label></div></section>
 <section class="playground-panel"><div class="playground-heading"><div><h2>Compare options</h2><p>Switch options to see how they affect the total.</p></div>${optButton('Reset experiment','budget-reset')}</div><div class="playground-options">${selectors||'<p>No options yet.</p>'}</div>${missing.length?`<p class="pg-warning">Incomplete estimate — missing prices: ${text(missing.join('; '))}</p>`:''}</section>
 <section class="playground-panel"><h2>Try additional costs or savings</h2><p>Positive amounts add costs; negative amounts are savings. These are temporary.</p><form id="budget-trial-form" class="playground-whatif"><label>What would change?<input name="name" required maxlength="160" placeholder="Extra castle tour"></label><label>Difference (${text(S.meta.currency)})<input name="amount" type="number" step="0.01" required placeholder="150 or -75"></label><button type="submit" class="primary">Add what-if</button></form><div class="playground-extras">${budgetTrial.extras.map((e,i)=>`<div class="pg-extra"><span>${text(e.name)}</span><strong>${money(e.amount)}</strong>${optButton('Edit','budget-edit-extra',`data-index="${i}"`)}${optButton('Remove','budget-remove-extra',`data-index="${i}"`)}</div>`).join('')}</div></section>
 <section class="playground-panel playground-baseline"><h2>About the estimate</h2><p>Includes food allowance and recorded additional expenses. Changing a choice replaces its cost. No purchases or saved expenses are changed.</p></section>`;
}
function wireBudget(){
 const food=document.getElementById('budget-food-input');if(food)food.onchange=()=>{const n=Number(food.value);if(Number.isFinite(n)&&n>=0){budgetTrial.food=n;render();}};
 const form=document.getElementById('budget-trial-form');
 if(form)form.onsubmit=e=>{e.preventDefault();const d=new FormData(form),amount=Number(d.get('amount')),name=String(d.get('name')||'').trim();if(!name||!Number.isFinite(amount))return;budgetTrial.extras.push({name,amount});render();};
 for(const el of document.querySelectorAll('[data-budget-choice]'))el.onchange=()=>{budgetTrial.choices[el.dataset.budgetChoice]=el.value;render();};
}
function reimbursementHTML(){const people={...S.travelers,...S.households},paid={};for(const p of vals(S.payments).filter(alive))paid[p.payerId]=(paid[p.payerId]||0)+(p.refund?-1:1)*Number(p.baseAmount||0);return `<h3>Who paid & reimbursements</h3><p class="muted" style="margin:10px 0">Cost shares are separate from who paid. Reimbursements do not increase the trip cost.</p><div class="table-wrap"><table><thead><tr><th>Traveler / household</th><th>Paid to providers</th><th>Allocated share</th></tr></thead><tbody>${vals(people).filter(alive).map(p=>{let share=0;for(const booking of vals(S.bookings).filter(x=>!x.canceled)){const amount=C.exchange(C.quoteTotal(booking.quote),booking.quote?.currency,S.meta.currency,fx());share+=(amount||0)*Number(booking.allocations?.[p.id]||0)/100;}for(const exp of vals(S.expenses).filter(x=>alive(x)&&x.scenarioId===sid))share+=(C.exchange(exp.amount,exp.currency,S.meta.currency,fx())||0)*Number(exp.allocations?.[p.id]||0)/100;return `<tr><td>${text(p.name)}</td><td>${money(paid[p.id]||0)}</td><td>${money(share)}</td></tr>`;}).join('')}</tbody></table></div>${optButton('+ Record reimbursement','reimbursement')}<div class="file-list">${vals(S.reimbursements).filter(alive).map(r=>`<p class="muted">${text(people[r.fromId]?.name||'Traveler')} → ${text(people[r.toId]?.name||'Traveler')} · ${money(r.amount,r.currency)} · ${text(r.date)}</p>`).join('')}</div>`;}
function travelHTML(){const ss=C.stops(S,S.meta.activeScenario||sid),nowDate=today(),days=vals(S.days).filter(d=>alive(d)&&d.scenarioId===sid).sort((a,b)=>(dayDate(a)||'9999').localeCompare(dayDate(b)||'9999')||C.byPosition(a,b));const current=days.filter(d=>dayDate(d)===localDate(new Date(),regionTime(S.stops[d.stopId]))),shown=travelWhole?days:current;const selected=C.groups(S,sid).map(g=>S.options[g.selectedId]).filter(alive);return `<div class="travel-hero"><div><span class="eyebrow">${text(activeScenario().name)}</span><h2>${travelWhole?'The whole journey':'Today · '+text(shortDate(nowDate))}</h2><p class="muted">Local times at each stop. Reservations are prominent; open decisions remain accessible.</p></div><div class="segmented">${optButton('Today','travel-today','',travelWhole?'':'active')}${optButton('Whole trip','travel-whole','',travelWhole?'active':'')}</div></div>${!shown.length?empty('No itinerary day scheduled for today','Your full itinerary and reservations are still available.',optButton('See the whole trip','travel-whole','','primary')):''}${shown.map(d=>{const st=S.stops[d.stopId],acts=vals(S.activities).filter(a=>alive(a)&&a.dayId===d.id).sort(activityOrder),items=selected.filter(o=>{const start=o.fields?.startDate,end=o.fields?.endDate;return start&&dayDate(d)>=start&&dayDate(d)<=(end||start);});return `<section class="stop" ${colorAttr(st?.location||st?.name)}><div class="stop-header"><div><span class="eyebrow">${text(st?.name||'Travel day')}</span><h2>${text(shortDate(dayDate(d)))} · ${text(d.title)}</h2></div></div>${notesHTML(d)}${items.map(o=>{const booked=C.booking(S,o);return `<article class="travel-item"><span class="badge ${booked?'booked':''}">${text(C.status(S,o,S.groups[o.groupId]))}</span><h3>${text(title(o))}</h3><p>${text(summary(o))}</p>${notesHTML(o)}${booked?.reference?`<p class="muted">Booking reference: ${text(booked.reference)}</p>`:''}${U.ideas[o.ideaId]?.location?`<p class="muted">${text(U.ideas[o.ideaId].location)}</p>`:''}<div class="add-row">${optButton('Details & backups','option',`data-id="${o.id}"`)}${booked?optButton('Tickets & reservation','booking',`data-id="${booked.id}"`):'<span class="badge provisional">Not booked</span>'}</div></article>`;}).join('')}${acts.map(a=>`<article class="travel-item"><span class="badge ${a.confirmed?'booked':''}">${a.confirmed?'Confirmed':'Planned'}</span><h3>${text(a.time||a.timeBlock||'Anytime')} · ${text(a.name)}</h3>${notesHTML(a)}${activityPrice(a)}${optButton('Details','activity',`data-id="${a.id}"`)}</article>`).join('')}${!items.length&&!acts.length?'<p class="travel-gap">Open day. Add plans or leave room to explore.</p>':''}</section>`;}).join('')}<div class="section-title"><h3>Reservations & tickets</h3></div>${vals(S.bookings).filter(b=>!b.canceled).map(bookingCard).join('')||'<p class="muted">No confirmed reservations recorded.</p>'}`;}
function mapHTML(){const ss=C.stops(S,sid),days=vals(S.days).filter(d=>alive(d)&&d.scenarioId===sid).sort((a,b)=>(dayDate(a)||'').localeCompare(dayDate(b)||''));return `<div class="section-title"><div><h2>Map your journey</h2><p>Follow the overall route or focus on one day. Connections show the journey sequence, not turn-by-turn directions.</p></div></div><div class="toolbar">${select('Map focus','map-day',mapDay,[['','Whole journey'],...days.map(d=>[d.id,(dayDate(d)?shortDate(dayDate(d)):'Day '+(Number(d.position)+1))+' · '+(S.stops[d.stopId]?.name||d.title)])])}<label class="label-row"><input id="map-backups" type="checkbox" ${prefs().mapBackups?'checked':''}> Backups</label><label class="label-row"><input id="map-unscheduled" type="checkbox" ${prefs().mapUnscheduled?'checked':''}> Unscheduled ideas</label></div><div class="map-layout"><div><div id="journey-map" class="map-canvas" aria-label="Journey map"></div><p id="map-tile-status" class="muted" role="status" hidden>Map tiles could not load. You can still use the route, pins, and stop list.</p><p class="map-legend">© OpenStreetMap contributors · Map tiles require a connection and are not included in offline downloads.</p></div><div class="map-points">${ss.map(st=>`<button class="map-point" ${colorAttr(st.location||st.name)} data-action="jump" data-id="${st.id}"><strong>${text(st.name)}</strong><small>${text(dateSpan(st.startDate,C.datePlus(st.startDate,Number(st.nights||0))))}${st.lat==null?' · Add coordinates in stop details':''}</small></button>`).join('')}</div></div>`;}
async function drawMap(){if(view!=='map')return;const el=document.getElementById('journey-map');if(!el)return;try{if(!window.L){await loadCSS('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css');await loadScript('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js');}if(!el.isConnected)return;const L=window.L;mapInstance=L.map(el).setView([54,-4],5);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,referrerPolicy:'origin',attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'})
 .on('tileerror',()=>{const status=document.getElementById('map-tile-status');if(el.isConnected&&status)status.hidden=false;})
 .addTo(mapInstance);let ss=C.stops(S,sid);if(mapDay)ss=ss.filter(st=>st.id===S.days[mapDay]?.stopId);const coords=[];for(const st of ss)if(st.lat!=null&&st.lng!=null){const point=[Number(st.lat),Number(st.lng)];coords.push(point);const popup=document.createElement('div');popup.innerHTML=`<strong>${text(st.name)}</strong><br>${text(dateSpan(st.startDate,C.datePlus(st.startDate,Number(st.nights||0))))}<br>`;const b=document.createElement('button');b.textContent='Open stop';b.onclick=()=>jump(st.id);popup.append(b);L.circleMarker(point,{radius:9,color:color(st.location||st.name)[0],fillColor:color(st.location||st.name)[1],fillOpacity:1,weight:3}).addTo(mapInstance).bindPopup(popup);}
const selectedIds=new Set(C.groups(S,sid).map(g=>g.selectedId));for(const o of vals(S.options).filter(o=>alive(o)&&o.scenarioId===sid&&(selectedIds.has(o.id)||prefs().mapBackups))){const g=S.groups[o.groupId];if(mapDay&&g.stopId!==S.days[mapDay]?.stopId)continue;const idea=U.ideas[o.ideaId];if(idea?.lat==null||idea?.lng==null)continue;const popup=document.createElement('div');popup.innerHTML=`<strong>${text(title(o))}</strong><br>${text(C.status(S,o,g))}`;const b=document.createElement('button');b.textContent='Open details';b.onclick=()=>openOption(o.id);popup.append(b);L.circleMarker([Number(idea.lat),Number(idea.lng)],{radius:5,color:selectedIds.has(o.id)?'#d3b781':'#a6b4c8',fillOpacity:.8}).addTo(mapInstance).bindPopup(popup);}
for(const activity of vals(S.activities).filter(a=>alive(a)&&a.scenarioId===sid&&a.dayId&&(!mapDay||a.dayId===mapDay))){const idea=U.ideas[activity.ideaId];if(idea?.lat==null||idea?.lng==null)continue;const popup=document.createElement('div');popup.textContent=(activity.time||activity.timeBlock||'Anytime')+' · '+(activity.name||idea.name);const button=document.createElement('button');button.textContent='Open activity';button.onclick=()=>openActivity(activity.id);popup.append(button);L.circleMarker([Number(idea.lat),Number(idea.lng)],{radius:6,color:'#a0c9b7',fillOpacity:.8}).addTo(mapInstance).bindPopup(popup);}
if(prefs().mapUnscheduled)for(const idea of vals(U.ideas).filter(i=>alive(i)&&i.lat!=null&&i.lng!=null&&!vals(S.options).some(o=>alive(o)&&o.scenarioId===sid&&o.ideaId===i.id))){const popup=document.createElement('div');popup.textContent=idea.name;L.circleMarker([Number(idea.lat),Number(idea.lng)],{radius:4,color:'#bccbdf',dashArray:'3 3',fillOpacity:.3}).addTo(mapInstance).bindPopup(popup);}
if(coords.length>1){L.polyline(coords,{color:'#b9a482',weight:2,dashArray:'6 6'}).addTo(mapInstance);mapInstance.fitBounds(coords,{padding:[35,35]});}else if(coords.length)mapInstance.setView(coords[0],12);
}catch(_){el.innerHTML='<div class="empty"><h3>Map unavailable</h3><p>Your itinerary is still available. Connect to load map tiles, or use the stop list alongside this view.</p></div>';}}
function loadScript(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.head.append(s);});}
function loadCSS(href){return new Promise((resolve,reject)=>{if(document.querySelector(`link[href="${href}"]`))return resolve();const l=document.createElement('link');l.rel='stylesheet';l.href=href;l.onload=resolve;l.onerror=reject;document.head.append(l);});}
function settingsHTML(){const tabs=[['display','Display'],['trip','Trip & alternatives'],['templates','Types & fields'],['time','Time blocks'],['tasks','Planning tasks'],['travelers','Travelers & households'],['currency','Currencies'],['offline','Offline & backups']];let html='';const p=prefs();
if(settingsTab==='display')html=`<h3>Make the workspace yours</h3><p>Useful defaults stay here. Everyday editing stays with your plan.</p><form id="display-settings" class="field-list">${select('Default detail','density',p.density||'compact',[['compact','Compact'],['detailed','Detailed']])}<label class="check"><input name="showNotes" type="checkbox" ${p.showNotes!==false?'checked':''}> Show notes in Detailed view</label><label class="check"><input name="mapBackups" type="checkbox" ${p.mapBackups?'checked':''}> Show backup options on the map by default</label><label class="check"><input name="mapUnscheduled" type="checkbox" ${p.mapUnscheduled?'checked':''}> Show unscheduled ideas on the map by default</label><button class="primary">Save display defaults</button></form>`;
if(settingsTab==='trip')html=`<h3>Your trip</h3><form id="trip-name-form">${field('Trip name','name',S.meta.name,'text','required maxlength="120"')}<div class="add-row"><button class="primary">Save name</button></div></form><h3>Itinerary alternatives</h3><p>Each alternative has its own stops, dates, selections and budget. Actual bookings remain shared records.</p>${scenarios().map(s=>`<article class="booking-card"><div class="row"><h4>${text(s.name)}</h4>${s.id===S.meta.activeScenario?'<span class="badge booked">Active travel plan</span>':''}</div><p class="muted">${text(s.startDate||'Dates open')} · ${money(s.budget)} budget</p><div class="add-row">${optButton('Edit dates & details','scenario-settings',`data-id="${s.id}"`)}${s.id===S.meta.activeScenario?'':optButton('Archive','archive-scenario',`data-id="${s.id}"`,'danger')}${optButton('Duplicate','duplicate-scenario',`data-id="${s.id}"`)}${optButton('Make active','activate-scenario',`data-id="${s.id}"`)}</div></article>`).join('')}<div class="add-row">${optButton('+ New alternative','new-scenario','','primary')}</div>`;
if(settingsTab==='templates')html=`<h3>Predictable fields, freely customizable</h3><p>These templates apply to new items. Removing a field from a template never erases existing item values.</p>${vals(U.templates).filter(alive).map(t=>`<article class="booking-card"><div class="row"><h4>${text(t.name)}</h4>${optButton('Edit template','template',`data-id="${t.id}"`)}</div><p class="muted">${(t.fields||[]).map(f=>text(f.label)).join(' · ')||'Name and common details only'}</p><p class="muted">Summary: ${(t.summaryFields||[]).map(text).join(' · ')||'No additional fields'}</p></article>`).join('')}<div class="add-row">${optButton('+ Custom type','new-template','','primary')}</div>`;
if(settingsTab==='time')html=`<h3>Flexible time blocks</h3><p>One block per line: name | approximate start time. Leave the time blank for Anytime. Exact reservations retain their own local times and time zones.</p><form id="time-blocks-form">${field('Blocks','blocks',(p.timeBlocks||[]).map(b=>b.name+' | '+b.start).join('\n'),'textarea')}<div class="add-row"><button class="primary">Save time blocks</button></div></form>`;
if(settingsTab==='tasks')html=`<h3>Optional planning tasks</h3><form id="task-settings" class="field-list"><label class="check"><input name="tasksEnabled" type="checkbox" ${p.tasksEnabled!==false?'checked':''}> Show Planning Tasks and its attention-panel section</label>${field('Statuses, one per line','statuses',(p.taskStatuses||['To do','In progress','Done']).join('\n'),'textarea')}${field('Custom task fields, one label per line','taskFields',(p.taskFields||[]).map(f=>f.label).join('\n'),'textarea')}<button class="primary">Save task settings</button></form><p style="margin-top:16px">Existing tasks keep their values when you change these defaults.</p>`;
if(settingsTab==='travelers')html=`<h3>People on the trip</h3><p>These are travelers and cost-allocation groups. Existing account access rules are unchanged.</p>${vals(S.travelers).filter(alive).map(t=>`<article class="booking-card"><div class="row"><strong>${text(t.name)}</strong>${optButton('Edit','traveler',`data-id="${t.id}"`)}</div><p class="muted">${text(S.households[t.householdId]?.name||'No household assigned')}</p></article>`).join('')}<div class="add-row">${optButton('+ Traveler','add-traveler','','primary')}</div><h3>Households</h3>${vals(S.households).filter(alive).map(h=>`<article class="booking-card"><div class="row"><strong>${text(h.name)}</strong>${optButton('Edit','household',`data-id="${h.id}"`)}</div></article>`).join('')}<div class="add-row">${optButton('+ Household','add-household')}</div><hr><label class="check"><input id="reimbursement-enabled" type="checkbox" ${p.trackReimbursements?'checked':''}> Track reimbursements separately from cost shares</label>`;
if(settingsTab==='currency'){const lock=S.meta.rateLock;html=`<h3>Original prices, one working currency</h3><p>Original quotes stay in their quoted currency. Estimates refresh automatically with daily reference rates. Actual payment charges stay fixed.</p><form id="currency-form" class="field-list">${select('Trip budget currency','currency',S.meta.currency,['USD','GBP','EUR','CAD','AUD','NZD','JPY','CHF','SEK','NOK','DKK'].map(c=>[c,c]))}<button class="primary">Use this currency</button></form><h3>${lock?'Planning rate locked':'Automatic rate updates'}</h3><p>${text(lock?.asOf||rates.asOf||'No rate date available')}${rates.notice?' · '+text(rates.notice):''}</p><div class="add-row">${optButton(lock?'Unlock rates':'Lock current rates','rate-lock','','primary')}${optButton('Refresh rates','refresh-rates')}</div><div class="table-wrap"><table><thead><tr><th>Original currency</th><th>1 unit in ${text(S.meta.currency)}</th></tr></thead><tbody>${Object.entries(fx()).map(([c,n])=>`<tr><td>${text(c)}</td><td>${Number(n).toFixed(5)}</td></tr>`).join('')}</tbody></table></div><h3>Set a manual planning rate</h3><form id="manual-rate" class="form-grid">${field('Original currency','currency','GBP','text','required minlength="3" maxlength="3"')}${field('1 unit equals this many '+S.meta.currency,'rate','','number','required min="0.000001"')}<button class="primary full">Save & lock planning rate</button></form><p style="margin-top:15px">Reference data: <a href="https://frankfurter.dev/" target="_blank" rel="noopener noreferrer">Frankfurter</a>. Card fees and actual bank rates can differ.</p>`;}
if(settingsTab==='offline')html=`<h3>Take your trip with you</h3><p>Download the workspace, plans, ideas and attached reservation files for this browser. Offline edits and expenses queue locally and sync when connected. Map tiles stay online.</p><div class="add-row">${optButton('Download / update offline copy','download-offline','','primary')}${optButton('Export trip backup','export-backup')}${optButton('Print current view','print')}</div><p style="margin-top:13px">${offlineReady?'Last offline download: '+text(offlineReady):'No complete offline download recorded in this browser.'}</p><p>Your changes are also saved locally as you work. A backup export includes this trip and your idea collection; keep it private.</p><h3>Pending changes</h3><p>${queue.length} queued operations. ${text(syncError||'Updates save automatically.')}</p>${optButton('Retry synchronization','sync-now')}`;
return `<div class="section-title"><div><h2>Settings</h2><p>Customize the tools without crowding the trip.</p></div></div><div class="settings-layout"><nav class="settings-nav" aria-label="Settings sections">${tabs.map(([id,name])=>optButton(text(name),'settings-section',`data-section="${id}"`,id===settingsTab?'active':'')).join('')}</nav><section class="settings-panel">${html}</section></div>`;}
function render(){if(!S||!U)return;const scroll=window.scrollY;
 for(const disclosure of app.querySelectorAll('[data-plan-disclosure]'))planDisclosures.set(disclosure.dataset.planDisclosure,disclosure.open);
 if(mapInstance){mapInstance.remove();mapInstance=null;}const ss=C.stops(S,sid);document.title=S.meta.name+' · Furlong';const nav=[['plan','✧','Plan'],['ideas','◇','Ideas'],['map','⌖','Map'],['compare','⇄','Compare'],['travel','◷','Travel'],...(prefs().tasksEnabled!==false?[['tasks','☑','Tasks']]:[]),['budget','◈','Budget'],['settings','⚙','Settings']];const body=view==='plan'?planHTML():view==='ideas'?ideasHTML():view==='tasks'?tasksHTML():view==='compare'?compareHTML():view==='budget'?budgetHTML():view==='travel'?travelHTML():view==='map'?mapHTML():settingsHTML();app.innerHTML=`<div class="shell ${view==='plan'?'plan-view':''} density-${prefs().density||'compact'} ${prefs().showNotes===false?'hide-notes':''}"><aside class="sidebar"><a class="brand" href="/"><img src="/static/furlong-bear.svg" alt=""><span class="wordmark">furlong<span>.</span></span></a><nav class="nav-stack" aria-label="Trip navigation">${nav.map(([id,icon,name])=>`<button data-action="view" data-view="${id}" class="${view===id?'active':''}" ${view===id?'aria-current="page"':''}><span aria-hidden="true">${icon}</span>${name}</button>`).join('')}</nav><div class="mobile-account"><a class="button small" href="/">My journeys</a>${optButton('Sign out','logout','','small quiet')}</div>${view==='plan'?`<nav class="stop-nav" aria-label="Jump to a stop"><span class="eyebrow">YOUR STOPS</span>${ss.map((s,i)=>`<a href="#stop-${s.id}" data-action="jump" data-id="${s.id}" ${colorAttr(s.location||s.name,i)}>${text(s.name)}<span>↓</span></a>`).join('')}</nav>`:''}<div class="sidebar-footer"><a href="/">← My journeys</a><p style="margin-top:10px">Make room for the journey.</p>${optButton('Sign out','logout','','small quiet')}</div></aside><main class="main" id="workspace" tabindex="-1"><header class="topbar"><div class="title-group"><div><p class="eyebrow">${view==='travel'?'OUT IN THE WORLD':'A JOURNEY IN THE MAKING'}</p><h1>${text(S.meta.name)}</h1></div></div><div class="header-actions"><span class="sync" data-sync>Saved</span>${optButton('Undo','undo','','small quiet')}${optButton('+ Add idea','add-idea','','primary small')}${optButton('⚙ Settings','view','data-view="settings"','small')}</div></header>${!navigator.onLine?'<p class="offline-banner">Offline. Your downloaded plans remain available; edits and expenses will sync when you reconnect.</p>':''}<div class="modebar"><div class="tabs" aria-label="Itinerary alternatives">${scenarios().map((s,i)=>`<button style="--city:${colors[i%colors.length][0]}" class="${s.id===sid?'active':''}" data-action="scenario" data-id="${s.id}">${text(s.name)}${s.id===S.meta.activeScenario?' ·':''}</button>`).join('')}</div>${view==='plan'?`<div class="segmented" role="group" aria-label="Workspace detail">${optButton('Compact','density','data-value="compact"',prefs().density!=='detailed'?'active':'')}${optButton('Detailed','density','data-value="detailed"',prefs().density==='detailed'?'active':'')}</div>`:''}</div>${body}</main></div>`;updateSync();wireView();if(view==='budget')wireBudget();window.scrollTo({top:scroll,behavior:'instant'});if(view==='map')drawMap();}
function jump(id){view='plan';render();requestAnimationFrame(()=>{const target=document.getElementById('stop-'+id)||document.getElementById('group-'+id)||document.getElementById('day-'+id)||document.getElementById('item-'+id);if(!target){if(id==='bookings'){view='budget';render();}return;}
 const direct=target.querySelector(':scope > details[data-plan-disclosure]');
 if(direct)direct.open=true;
 for(let node=target;node&&node!==app;node=node.parentElement){
  if(node.matches('details[data-plan-disclosure]'))node.open=true;
 }
 target.classList.add('flash-target');target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});setTimeout(()=>target.classList.remove('flash-target'),3000);});}
function setView(next){view=next;if(view==='travel')sid=S.meta.activeScenario||sid;render();window.scrollTo({top:0,behavior:'instant'});}
function contextGroup(gid){const g=S.groups[gid],st=S.stops[g?.stopId];return {g,st,fields:{startDate:g?.startDate||st?.startDate||'',endDate:g?.endDate||(st?.startDate?C.datePlus(st.startDate,Number(st.nights||0)):''),guests:vals(S.travelers).filter(alive).length||null}};}
function newIdeaOption(idea,g,fields={}){return {id:uid(),scenarioId:g.scenarioId,groupId:g.id,ideaId:idea.id,type:idea.type,label:'',fields:{...fields},quote:{amount:null,currency:S.meta.currency,basis:'total',quantity:1,units:1,startDate:fields.startDate||'',endDate:fields.endDate||'',conditions:C.conditions(fields),checkedAt:null},quoteHistory:[],stage:'idea',parts:[],bookingId:null,confirmed:false,position:C.options(S,g.id).length,archived:false};}
function openAddIdea(groupId=null,existingIdeaId=null){
 const group=groupId&&S.groups[groupId],existing=existingIdeaId&&U.ideas[existingIdeaId];
 const ctx=group?contextGroup(group.id):null;
 showEditor(existing?'Use '+existing.name:group?'Add an option':'Save an idea',`<form id="new-idea">
 <p class="muted">${group?'Adding to '+text(group.name)+' · '+text(S.scenarios[group.scenarioId]?.name):'Save to your general collection. A name is enough.'}</p>
 ${field(existing?'Name for this plan':'Name','name',existing?.name||'','text','required maxlength="160"')}
 ${select('Type','type',existing?.type||group?.type||'idea',templates())}
 ${linkField(existing?.website)}
 <div class="add-row">${optButton('Try filling details from link','fill-link')}</div>
 <p id="link-preview-note" class="muted"></p>
 <div id="new-option-details"></div>
 ${!existing?field('Location','location',ctx?.st?.location||''):''}
 ${field('Notes','notes',existing?.notes||'','textarea')}
 <button class="primary">${group?'Save option':'Save idea'}</button></form>`,'ROOM FOR POSSIBILITIES');
 const form=editor.querySelector('#new-idea');
 const drafts={};
 let renderedType=null;
 const showOptionFields=()=>{
  const container=form.querySelector('#new-option-details');
  if(renderedType)drafts[renderedType]=formValues(container);
  if(!group)return;
  const type=form.elements.type.value,draft=drafts[type]||{},flight=type==='flight';
  renderedType=type;
  const fields={...ctx.fields,travelers:ctx.fields.guests,...Object.fromEntries(
   Object.entries(draft).filter(([key])=>key.startsWith('field_')).map(([key,value])=>[key.slice(6),value]))};
  const descriptors=(U.templates[type]||U.templates.idea)?.fields||[];
  const days=['activity','restaurant'].includes(type)?dayChoices(group.scenarioId):[];
  container.innerHTML=`${descriptors.length?`<h3>${text(U.templates[type]?.name||'Option')} details</h3>
   <div class="form-grid">${descriptors.map(f=>field(f.label,'field_'+f.key,fields[f.key]??'',f.kind)).join('')}</div>`:''}
   ${days.length?select('Add to itinerary day (optional)','dayId',draft.dayId||'',[['','Leave unscheduled'],...days]):''}
   <details ${flight||draft.quote_amount!=null?'open':''}><summary>Price quote</summary>
   ${quoteFields({amount:draft.quote_amount,currency:draft.quote_currency,basis:draft.quote_basis,
    quantity:draft.quote_quantity??(flight?fields.travelers:1),units:draft.quote_units},'quote_')}</details>`;
 };
 form.elements.type.onchange=showOptionFields;
 showOptionFields();
 form.onsubmit=e=>{
  e.preventDefault();
  if(!form.reportValidity())return;
  const data=formValues(form);
  const idea=existing||{id:uid(),name:data.name,type:data.type,website:data.website,
   location:data.location,notes:data.notes,originTripId:tid,createdAt:new Date().toISOString(),favorite:false,archived:false};
  const changes=[];
  if(!existing)changes.push(['ideas',idea.id,idea,'user']);
  if(group){
   const fields={...ctx.fields};
   for(const [key,value] of Object.entries(data))if(key.startsWith('field_'))fields[key.slice(6)]=value;
   const day=S.days[data.dayId];
   if(day)fields.startDate=dayDate(day)||'';
   if(existing&&data.notes!==existing.notes)fields.notes=data.notes;
   const option=newIdeaOption(idea,group,fields);
   option.type=data.type;
   if(existing&&data.name!==idea.name)option.label=data.name;
   if(existing&&data.website!==(idea.website||''))option.website=data.website;
   if(data.quote_amount!==null){
    option.quote={...option.quote,amount:data.quote_amount,currency:data.quote_currency.toUpperCase(),
     basis:data.quote_basis,quantity:data.quote_quantity,units:data.quote_units,checkedAt:new Date().toISOString()};
   }
   changes.push(['options',option.id,option]);
   if(day)changes.push(C.scheduleActivityChange(S,option,day,option.label||idea.name,fields));
  }
  addChanges(changes,group?'Save option':'Save idea');
  editor.pendingSave=null;editor.close();render();
  toast(group?'Option saved.':'Idea saved to your collection.');
 };
 editor.querySelector('[data-action="fill-link"]').onclick=async()=>{const url=form.elements.website.value,note=editor.querySelector('#link-preview-note');if(!url){note.textContent='Paste a link first, or keep entering details manually.';return;}note.textContent='Reading available page details…';try{const response=await requestAPI(`/api/planner/${tid}/link-preview`,{method:'POST',body:JSON.stringify({url})});const data=await response.json();for(const [k,v] of Object.entries(data.suggestions||{}))if(form.elements[k]&&!form.elements[k].value)form.elements[k].value=v;note.textContent=data.notice;}catch(_){note.textContent='Details could not be read. Manual entry is available.';}};}
function openIdea(id){const idea=U.ideas[id];showEditor(idea.name,`<form id="idea-details"><p class="muted">Core details are shared wherever this idea is used. Dates, quotes and choices stay independent in each plan.</p>${field('Name','name',idea.name,'text','required maxlength="160"')}${select('Type','type',idea.type,templates())}${field('Location / address','location',idea.location||'')}${field('Website','website',idea.website||'','url')}${field('Notes','notes',idea.notes||'','textarea')}${placeSearchHTML(idea.location||idea.name)}<div class="form-grid">${field('Latitude','lat',idea.lat??'','number','min="-90" max="90"')}${field('Longitude','lng',idea.lng??'','number','min="-180" max="180"')}</div><span class="save-status" data-editor-saved>Edits save automatically.</span></form><h3 style="margin:20px 0 10px">Image</h3>${idea.image?`<img src="${attr(idea.image.url)}" alt="${attr(idea.name)}" style="width:100%;max-height:180px;object-fit:cover;border-radius:8px">`:''}<label>Upload image<input id="idea-image" type="file" accept="image/png,image/jpeg,image/webp"></label><div class="editor-actions">${optButton('Use in a plan','use-idea',`data-id="${id}"`,'primary')}${optButton('Archive idea','archive-idea',`data-id="${id}"`,'danger')}</div>`,'SHARED IDEA');autosave(editor.querySelector('form'),data=>{editEntity('ideas',id,data,'user','Edit shared idea');render();});editor.querySelector('#idea-image').onchange=async e=>{const f=e.target.files[0];if(!f)return;const uploaded=await upload(f);if(uploaded){editEntity('ideas',id,{image:uploaded},'user','Add idea image');openIdea(id);}};wirePlaceSearch(editor.querySelector('#idea-details'));wireEditorActions();}
function openOption(id,partId=null){const option=S.options[id];if(!option)return;const item=partId?option.parts.find(p=>p.id===partId):option;if(!item)return;const group=S.groups[option.groupId],template=U.templates[item.type]||U.templates.idea,fields=item.fields||{};
const descriptors=[...(template.fields||[])];for(const key of Object.keys(fields))if(!descriptors.some(f=>f.key===key)&&!['notes'].includes(key))descriptors.push({key,label:item.customLabels?.[key]||key,kind:'text'});
const q=item.quote||{amount:null,currency:S.meta.currency,basis:'total',quantity:1,units:1},quoteHTML=`<form id="quote-form"><h3>Quote</h3><p class="muted">The previous quote remains a provisional reference if dates or conditions change.</p><div class="form-grid">${field('Quoted unit price or total','amount',q.amount??'','number')}${field('Currency','currency',q.currency||S.meta.currency,'text','required minlength="3" maxlength="3"')}${select('Pricing basis','basis',q.basis||'total',[['total','Total for this option'],['person','Per person'],['room-night','Per room, per night'],['vehicle-day','Per vehicle, per day'],['unit','Custom unit']])}${field('People / rooms / vehicles / units','quantity',q.quantity??1,'number')}${field('Nights / days / repetitions','units',q.units??1,'number')}</div><div class="quote-preview" id="quote-preview"></div><button class="primary">Save quote / mark checked</button></form>`;
const partsHTML=partId?`<div class="add-row">${optButton('Back to whole option','option',`data-id="${id}"`)}</div>`:
 `<section class="editor-parts" aria-label="Option parts">
  ${item.parts?.length?`<h3>Parts of this option</h3>${item.parts.map(p=>`<article class="part">
   <div class="part-heading"><strong>${text(p.name)}</strong>${optButton('Edit part','part',`data-id="${id}" data-part="${p.id}"`)}</div>
   <p class="muted">${text(C.status(S,p))} · ${C.cost(S,p,fx()).unknown?'Quote needed':money(C.cost(S,p,fx()).amount)}</p>
  </article>`).join('')}`:''}
  <div class="add-row">${optButton('+ Add a part','add-part',`data-id="${id}"`)}</div>
 </section>`;
showEditor(partId?item.name:title(option),`${partsHTML}${linkActions(partId?{...item,website:item.website||directLink(option)}:item,'option-link',id,partId||'')}<form id="option-details"><span class="badge ${C.booking(S,item)?'booked':''}">${text(C.status(S,item,group))}</span>${field(partId?'Part name':'Name for this occurrence (optional)','label',partId?item.name:option.label||'')}${select('Type','type',item.type,templates())}<div class="form-grid">${descriptors.map(f=>field(f.label,'field_'+f.key,fields[f.key]??'',f.kind)).join('')}</div>${field('Planning notes','notes',fields.notes||'','textarea')}${U.ideas[option.ideaId]?.notes?`<div class="shared-notes"><strong>Saved idea notes</strong><p>${text(U.ideas[option.ideaId].notes)}</p></div>`:''}<span class="save-status" data-editor-saved>Edits save automatically.</span></form><div class="add-row">${optButton('+ Custom field for this item','custom-item-field',`data-id="${id}" ${partId?`data-part="${partId}"`:''}`)}</div>${item.parts?.length?'':quoteHTML}<details><summary>Quote history (${(item.quoteHistory||[]).length})</summary>${(item.quoteHistory||[]).map(q=>`<div class="history">${money(C.quoteTotal(q),q.currency)} · ${text(q.startDate||'Dates open')} · ${text(q.checkedAt||'Check date unknown')}</div>`).join('')||'<p class="muted">Previous quotes will stay here when replaced.</p>'}</details><h3 style="margin:20px 0 10px">Reservations & confirmations</h3>${C.booking(S,item)?bookingCard(C.booking(S,item)):`<div class="add-row">${optButton('Record booking','record-booking',`data-id="${id}" ${partId?`data-part="${partId}"`:''}`,'primary')}${optButton(item.confirmed?'Mark unconfirmed':'Confirm without booking','confirm-option',`data-id="${id}" ${partId?`data-part="${partId}"`:''}`)}</div>`}<h3 style="margin:20px 0 10px">Attachments</h3>${filesHTML(item.attachments||[])}<label>Attach ticket, confirmation or notes<input type="file" id="option-file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.ics,.docx"></label><div class="editor-actions">${!partId?optButton('Remove from this plan','remove-option',`data-id="${id}"`,'danger'):''}${!partId?optButton('Edit shared idea','idea',`data-id="${option.ideaId}"`):''}</div>`,'INDEPENDENT PLANNING DETAILS');
const saveItem=patch=>{if(partId){const parts=copy(S.options[id].parts),index=parts.findIndex(p=>p.id===partId);parts[index]={...parts[index],...patch};editEntity('options',id,{parts},'trip','Edit option part');}else editEntity('options',id,patch,'trip','Edit option');};
autosave(editor.querySelector('#option-details'),data=>{const currentItem=partId?S.options[id].parts.find(p=>p.id===partId):S.options[id],newFields={...currentItem.fields};for(const [k,v] of Object.entries(data))if(k.startsWith('field_'))newFields[k.slice(6)]=v;newFields.notes=data.notes;saveItem({...(partId?{name:data.label||item.name}:{label:data.label}),type:data.type,fields:newFields});render();});
const quoteForm=editor.querySelector('#quote-form');if(quoteForm){const preview=()=>{const data=formValues(quoteForm),value=C.quoteTotal(data);editor.querySelector('#quote-preview').innerHTML=`${text(data.basis==='total'?'Direct total':'Unit price × quantity × repetitions')}<strong>${value===null?'Quote needed':money(value,(data.currency||S.meta.currency).toUpperCase())}</strong><span class="muted">Save explicitly to replace the current quote.</span>`;};quoteForm.oninput=()=>{try{preview();}catch(_){editor.querySelector('#quote-preview').textContent='Enter a valid three-letter currency.';}};preview();quoteForm.onsubmit=e=>{e.preventDefault();if(!e.target.reportValidity())return;const data=formValues(e.target),current=partId?S.options[id].parts.find(p=>p.id===partId):S.options[id];if(!/^[A-Za-z]{3}$/.test(data.currency)){toast('Use a three-letter currency code.');return;}const next={...data,currency:data.currency.toUpperCase(),startDate:current.fields?.startDate||'',endDate:current.fields?.endDate||'',conditions:C.conditions(current.fields),checkedAt:new Date().toISOString()};saveItem({quote:next,quoteHistory:[...(current.quoteHistory||[]),...(current.quote? [copy(current.quote)]:[])]});toast('Quote saved.');render();openOption(id,partId);};}
editor.querySelector('#option-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;const uploaded=await upload(f);if(uploaded){saveItem({attachments:[...(item.attachments||[]),uploaded]});openOption(id,partId);}};wireEditorActions();}
function filesHTML(files){return `<div class="file-list">${files.map(f=>`<a href="${attr(f.url)}" download>${text(f.name)} ↗</a>`).join('')||'<p class="muted">No files attached.</p>'}</div>`;}
async function upload(file){if(!navigator.onLine){toast('Connect to upload a new attachment. Downloaded attachments remain available offline.');return null;}try{const data=new FormData();data.append('file',file);const r=await requestAPI(`/api/planner/${tid}/files`,{method:'POST',body:data});if(!r.ok)throw Error('Upload failed. Use a supported file up to 10 MB.');return await r.json();}catch(e){toast(e.message);return null;}}
function openGroup(id=null,stopId=null,type='hotel',from=null,to=null){const old=id&&S.groups[id],st=S.stops[old?.stopId||stopId];const record=old||{id:uid(),scenarioId:sid,stopId:stopId||null,name:from?S.stops[from].name+' → '+S.stops[to].name:type==='hotel'?'Accommodation':'New decision',type,selectedId:null,allowance:null,notes:'',position:C.groups(S,sid).length,fromStopId:from,toStopId:to,startDate:st?.startDate||null,endDate:st?.startDate?C.datePlus(st.startDate,Number(st.nights||0)):null,archived:false};showEditor(old?'Edit decision group':'Add a decision group',`<form id="group-form"><p class="muted">The group stays even if you remove all its options. Different option types can compete here.</p>${field('Label','name',record.name,'text','required maxlength="160"')}${select('Suggested type for new options','type',record.type,templates())}${select('Stop / scope','stopId',record.stopId||'',[['','Between stops / shared transport'],...C.stops(S,sid).map(s=>[s.id,s.name])])}<div class="form-grid">${field('Start date (optional)','startDate',record.startDate||'','date')}${field('End date (optional)','endDate',record.endDate||'','date')}</div>${select('Itinerary placement','placement',record.stopId?'auto':record.itineraryPlacement==='before'?'before':record.itineraryPlacement==='after'?'after:'+record.anchorStopId:'auto',[['auto','Automatic: route links, then travel dates'],['before','Before first stop (outbound journey)'],...C.stops(S,sid).map(st=>['after:'+st.id,'After '+st.name])])}${field('Allowance before an option is selected ('+S.meta.currency+')','allowance',record.allowance??'','number')}${field('Notes','notes',record.notes||'','textarea')}<button class="primary">${old?'Save group':'Create empty group'}</button></form>${old?`<div class="editor-actions">${optButton('Remove group from plan','archive-group',`data-id="${id}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target),{placement,...data}=d,manual=placement!=='auto';addChanges([['groups',record.id,{...record,...data,stopId:manual?null:d.stopId||null,itineraryPlacement:placement==='before'?'before':placement.startsWith('after:')?'after':'auto',anchorStopId:placement.startsWith('after:')?placement.slice(6):null,startDate:d.startDate||null,endDate:d.endDate||null}]],'Edit decision group');editor.pendingSave=null;editor.close();render();};wireEditorActions();}
function placeSearchHTML(query=''){
 return `<div class="place-search">
 <label>Search for a city or town<input data-place-query value="${attr(query)}" maxlength="100" placeholder="Dublin"></label>
 <button type="button" class="small" data-find-place>Find map location</button>
 <p data-place-status class="muted" role="status"></p>
 <label hidden data-place-result-label>Matching place<select data-place-results></select></label>
 <p class="muted">Location search by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a>, using GeoNames data.</p>
 </div>`;
}
function wirePlaceSearch(form){
 const input=form.querySelector('[data-place-query]'),button=form.querySelector('[data-find-place]');
 const status=form.querySelector('[data-place-status]'),select=form.querySelector('[data-place-results]');
 let search=0;
 input.oninput=()=>{search++;select.replaceChildren();select.parentElement.hidden=true;status.textContent='';};
 button.onclick=async()=>{
  const query=input.value.trim(),request=++search;
  if(query.length<2){status.textContent='Enter a city or town name first.';return;}
  select.replaceChildren();select.parentElement.hidden=true;status.textContent='Finding matching places…';
  try{
   const response=await requestAPI('/api/places?name='+encodeURIComponent(query));
   if(!response.ok)throw Error();
   const data=await response.json();
   if(request!==search||!form.isConnected)return;
   select.add(new Option('Choose the matching place',''));
   for(const [index,place] of data.results.entries())select.add(new Option(place.label,String(index)));
   select.parentElement.hidden=!data.results.length;
   status.textContent=data.results.length?'Choose a result to fill the coordinates.':'No match found. Try a nearby city or town.';
   select.onchange=()=>{
    if(select.value==='')return;
    const place=data.results[Number(select.value)];
    form.elements.lat.value=place.lat;form.elements.lng.value=place.lng;
    if(form.elements.timeZone)form.elements.timeZone.value=place.timeZone;
    status.textContent='Map coordinates filled for '+place.label+'.';
    form.elements.lat.dispatchEvent(new Event('change',{bubbles:true}));
   };
  }catch(_){if(request===search&&form.isConnected)status.textContent='Place search is unavailable. You can save now and add a map location later.';}
 };
}
function openStop(id=null){const old=id&&S.stops[id],previous=C.stops(S,sid).at(-1),st=old||{id:uid(),scenarioId:sid,name:'',location:'',position:C.stops(S,sid).length,startDate:previous?.startDate?C.datePlus(previous.startDate,Number(previous.nights||0)):activeScenario().startDate||null,nights:1,notes:'',lat:null,lng:null,archived:false};showEditor(old?'Edit '+st.name:'Add a stop',`<form id="stop-form"><p class="muted">A stop can be a city, region or any label that helps you plan.</p>${field('Stop name','name',st.name,'text','required maxlength="100"')}${field('Location / region','location',st.location||'')}<div class="form-grid">${field('Start date (optional)','startDate',st.startDate||'','date')}${field('Nights','nights',st.nights??1,'number','max="365"')}</div>${placeSearchHTML(st.location||st.name)}<div class="form-grid">${field('Latitude (optional)','lat',st.lat??'','number','min="-90" max="90"')}${field('Longitude (optional)','lng',st.lng??'','number','min="-180" max="180"')}</div>${field('IANA time zone (optional)','timeZone',st.timeZone||'','text','placeholder="Europe/London"')}${field('Notes','notes',st.notes||'','textarea')}<button class="primary">${old?'Save stop':'Create stop'}</button></form>${old?`<div class="editor-actions">${optButton('Remove stop from plan','archive-stop',`data-id="${id}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const data=formValues(e.target),changes=[['stops',st.id,{...st,...data,nights:data.nights??1,startDate:data.startDate||null}]];if(!old){const gid=uid();changes.push(['groups',gid,{id:gid,scenarioId:sid,stopId:st.id,name:'Accommodation',type:'hotel',selectedId:null,allowance:null,position:0,notes:'',archived:false}]);}else{const delta=st.startDate&&data.startDate?C.dayNumber(data.startDate)-C.dayNumber(st.startDate):0;if(delta)changes.push(...shiftStopDetails(st,delta));}addChanges(changes,'Edit stop');editor.pendingSave=null;editor.close();render();};wirePlaceSearch(editor.querySelector('#stop-form'));wireEditorActions();}
function shiftStopDetails(st,delta){const changes=[],gids=new Set(C.groups(S,st.scenarioId,st.id).map(g=>g.id));for(const d of vals(S.days).filter(d=>alive(d)&&d.stopId===st.id))changes.push(['days',d.id,{...d,date:C.datePlus(d.date,delta)||null}]);for(const o of vals(S.options).filter(o=>alive(o)&&gids.has(o.groupId))){const next=copy(o);for(const p of next.parts?.length?next.parts:[next])if(!C.booking(S,p))for(const k of ['startDate','endDate'])if(p.fields[k])p.fields[k]=C.datePlus(p.fields[k],delta);changes.push(['options',o.id,next]);}return changes;}
function openDay(id=null,stopId=null){const old=id&&S.days[id],st=S.stops[old?.stopId||stopId],days=vals(S.days).filter(x=>alive(x)&&x.stopId===st?.id),d=old||{id:uid(),scenarioId:sid,stopId:st?.id||null,position:days.length,date:st?.startDate?C.datePlus(st.startDate,days.length):null,title:'',notes:'',archived:false};showEditor(old?'Edit day':'Plan a day',`<form id="day-form">${field('Title','title',d.title||'')}${select('Stop','stopId',d.stopId||'',[['','Unassigned'],...C.stops(S,sid).map(s=>[s.id,s.name])])}<div class="form-grid">${field('Relative day (starting at 1)','relativeDay',Number(d.position||0)+1,'number','required min="1" max="365"')}${field('Exact date (optional)','date',d.date||'','date')}</div>${field('Notes','notes',d.notes||'','textarea')}<button class="primary">Save day</button></form>${old?`<div class="editor-actions">${optButton('Remove day; keep its ideas','archive-day',`data-id="${id}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const data=formValues(e.target);addChanges([['days',d.id,{...d,title:data.title,notes:data.notes,stopId:data.stopId||null,position:Number(data.relativeDay)-1,date:data.date||null}]],'Edit day');editor.pendingSave=null;editor.close();render();};wireEditorActions();}
function openDayIdea(dayId){
 const day=S.days[dayId],options=vals(S.options).filter(o=>alive(o)&&o.scenarioId===day.scenarioId&&['activity','restaurant','idea'].includes(o.type));
 const used=new Set(options.map(o=>o.ideaId));
 const ideas=vals(U.ideas).filter(i=>alive(i)&&!used.has(i.id)&&['activity','restaurant','idea'].includes(i.type));
 const entries=[...options.map(o=>['option:'+o.id,title(o)+' · '+S.groups[o.groupId]?.name]),
  ...ideas.map(i=>['idea:'+i.id,i.name+(i.location?' · '+i.location:'')])];
 if(!entries.length){toast('There are no saved activities to use yet.');return;}
 simpleForm('Use a saved item',select('Item','item','',[['','Choose an item'],...entries],'required'),data=>{
  const [kind,id]=data.item.split(':');
  if(kind==='option'){openScheduleOption(id,dayId);return;}
  const existing=vals(S.activities).find(a=>alive(a)&&a.scenarioId===day.scenarioId&&a.ideaId===id);
  openActivity(existing?.id,dayId,id);
 });
}
function openScheduleOption(id,dayId=null){
 const option=S.options[id];
 if(!alive(option))return;
 const days=dayChoices(option.scenarioId);
 if(!days.length){toast('Add an itinerary day first.');return;}
 const existing=C.scheduledActivity(S,option),fields=option.fields||{};
 const time=existing?.time??fields.startTime??fields.departureTime??'';
 const blocks=(prefs().timeBlocks||[]).map(b=>[b.name,b.name]),block=existing?.timeBlock??fields.timeBlock??'';
 if(block&&!blocks.some(([name])=>name===block))blocks.push([block,block]);
 simpleForm('Schedule '+title(option),select('Day','dayId',dayId||existing?.dayId||days.find(([id])=>dayDate(S.days[id])===fields.startDate)?.[0]||'',
  [['','Choose a day'],...days],'required')+field('Exact local time (optional)','time',/^\d\d:\d\d$/.test(time)?time:'','time')
  +select('Time block','timeBlock',block,[['','Anytime'],...blocks]),data=>{
   addChanges([C.scheduleActivityChange(S,option,S.days[data.dayId],title(option),{...fields,startTime:data.time,timeBlock:data.timeBlock})],'Schedule item');
   editor.close();render();
  });
}
function openActivity(id=null,dayId=null,savedIdeaId=null){
 const old=id&&S.activities[id],idea=U.ideas[savedIdeaId];
 const a=old||{id:uid(),scenarioId:sid,dayId,ideaId:idea?.id,position:vals(S.activities).filter(x=>x.dayId===dayId).length,
  name:idea?.name||'',time:'',timeBlock:'Anytime',duration:null,notes:'',confirmed:false,archived:false};
 const linked=S.options[a.optionId],option=alive(linked)&&linked.scenarioId===a.scenarioId?linked:null,q=option?.quote||{amount:null,currency:S.meta.currency,basis:'total',quantity:1,units:1};
 const locked=option&&(C.booking(S,option)||option.parts?.length),moving=old&&dayId&&dayId!==a.dayId;
 const newQuote=`<div class="form-grid">${quoteAmountFields(q,'quote_','Estimated cost (optional)')}</div><details><summary>Pricing details</summary>${quoteFields(q,'quote_',false)}
 <label class="check"><input type="checkbox" name="include" checked> Include this activity quote in the budget</label></details>`;
 const quoteForm=locked?`<p class="muted">This activity uses a reservation or multipart option. Open its details to edit the relevant price.</p>`:
 `<form id="activity-quote"><h3>Price quote</h3>${quoteFields(q)}
 ${!option?'<label class="check"><input type="checkbox" name="include" checked> Include this activity quote in the budget</label>':`<p class="muted">${S.groups[option.groupId]?.selectedId===option.id?'Included in budget.':'Quote only; select the linked option to include it in the budget.'}</p>`}
 <p class="quote-preview" id="activity-quote-preview"></p><button class="primary">Save price quote</button></form>`;
 showEditor(old?'Edit activity':'Add activity',`${old&&!moving?linkActions(option||a,'activity-link',id):''}<form id="activity-form">${field('Name','name',a.name,'text','required maxlength="160"')}${select('Day','dayId',dayId||a.dayId||'',[['','Unscheduled'],...dayChoices(a.scenarioId)])}<div class="form-grid">${field('Exact local time (optional)','time',/^\d\d:\d\d$/.test(a.time||'')?a.time:'','time')}${select('Loose time block','timeBlock',a.timeBlock||'Anytime',[['','No block'],...(prefs().timeBlocks||[]).map(b=>[b.name,b.name])])}${field('Duration in hours (optional)','duration',a.duration??'','number')}</div>${old?'':newQuote}${field('Notes','notes',a.notes||'','textarea')}${C.itemNotes(a,U,S).filter(note=>note!==a.notes).map(note=>`<div class="shared-notes"><strong>Linked notes</strong><p>${text(note)}</p></div>`).join('')}<label class="label-row"><input name="confirmed" type="checkbox" ${a.confirmed?'checked':''}> Confirmed</label><span class="save-status">${moving?'Save to move this activity.':old?'Changes save when you finish a field.':'Save to add this activity to your plan.'}</span>${!old?`${linkField(idea?.website)}<button class="primary">Save activity</button>`:''}</form>${old&&!moving?quoteForm:''}${option?`<div class="add-row">${optButton('Linked option, quote history & booking','option',`data-id="${option.id}"`)}</div>`:''}${old?`<div class="editor-actions">${optButton('Unschedule; keep idea','unschedule-activity',`data-id="${id}"`,'danger')}</div>`:''}`);
 const details=editor.querySelector('#activity-form');
 const activityChanges=data=>{
  const {website,quote_amount,quote_currency,quote_basis,quote_quantity,quote_units,include,...details}=data;
  const changes=[],current=S.activities[a.id]||a;let ideaId=current.ideaId;
  const activity={...current,...details};
  if(!ideaId){ideaId=uid();changes.push(['ideas',ideaId,{id:ideaId,name:data.name,type:'activity',originTripId:tid,location:S.stops[S.days[data.dayId]?.stopId]?.location||'',notes:data.notes,website:website??current.website??'',favorite:false,createdAt:new Date().toISOString(),archived:false},'user']);}
  activity.ideaId=ideaId;activity.dayId=data.dayId||null;
  if(!old&&idea&&website!==(idea.website||''))activity.website=website;
  changes.push(['activities',a.id,activity]);
  const linked=S.options[current.optionId],group=S.groups[linked?.groupId];
  if(alive(linked)&&group?.activityId===a.id&&!C.booking(S,linked)){
   const day=S.days[data.dayId],date=day?dayDate(day):linked.fields?.startDate||'';
   changes.push(['options',linked.id,{...linked,label:data.name,fields:{...linked.fields,startDate:date||'',startTime:data.time||'',notes:data.notes}}]);
   if(day&&group.stopId!==day.stopId)changes.push(['groups',group.id,{...group,stopId:day.stopId||null}]);
  }
  return changes;
 };
 const readQuote=(data,prefix='')=>({amount:data[prefix+'amount'],currency:data[prefix+'currency'].toUpperCase(),
  basis:data[prefix+'basis'],quantity:data[prefix+'quantity'],units:data[prefix+'units']});
 const save=data=>{addChanges(activityChanges(data),'Edit activity');render();};
 if(old&&!moving)autosave(details,save);
 else {
  if(old)details.insertAdjacentHTML('beforeend','<button class="primary">Save activity</button>');
  details.onsubmit=e=>{
   e.preventDefault();
   const data=formValues(details),changes=activityChanges(data);
   try{
    if(!old&&data.quote_amount!==null){
     const index=changes.findIndex(([collection])=>collection==='activities');
     const activity=changes[index][2];
     changes.splice(index,1,...C.activityQuoteChanges(S,activity,readQuote(data,'quote_'),data.include));
    }
    addChanges(changes,old?'Move activity':'Add activity');editor.close();render();
   }catch(error){toast(error.message);}
  };
 }
 const form=editor.querySelector('#activity-quote');
 if(form){
  const preview=()=>{const data=formValues(form),total=C.quoteTotal(data),out=editor.querySelector('#activity-quote-preview');try{out.textContent=total===null?'No price saved. A price in notes does not count toward the budget.':'Quote total: '+money(total,(data.currency||S.meta.currency).toUpperCase());}catch(_){out.textContent='Enter a three-letter currency code.';}};
  form.oninput=preview;preview();
  form.onsubmit=e=>{e.preventDefault();if(!details.reportValidity()||!form.reportValidity())return;try{
   const data=formValues(form),quote=readQuote(data);
   // Validate before creating anything; invalid quotes cannot leave partial activities.
   const draft={...S.activities[a.id],...formValues(details)};
   C.activityQuoteChanges(S,draft,quote,Boolean(data.include));
   editor.pendingSave?.();
   const current=S.activities[a.id],changes=current.ideaId?[]:activityChanges(formValues(details));
   const activity=changes.find(([collection])=>collection==='activities')?.[2]||current;
   addChanges([...changes,...C.activityQuoteChanges(S,activity,quote,Boolean(data.include))],'Save activity quote');
   editor.pendingSave=null;openActivity(a.id);render();toast('Price quote saved.');
  }catch(error){toast(error.message);}};
 }
 wireEditorActions();
}
function allocationsForm(allocations={}){const participants=[...vals(S.households).filter(alive),...vals(S.travelers).filter(alive)];return `<details><summary>Optional cost shares</summary><p class="muted">Allocate by household or traveler. Use percentages totaling 100, or leave all blank.</p><div class="form-grid">${participants.map(p=>field(p.name+' (%)','share_'+p.id,allocations[p.id]??'','number','max="100"')).join('')}</div>${!participants.length?'<p class="muted">Add travelers or households in Settings first.</p>':''}</details>`;}
function allocationsFrom(data){const shares=Object.fromEntries(Object.entries(data).filter(([k,v])=>k.startsWith('share_')&&v!==null&&v>0).map(([k,v])=>[k.slice(6),v]));const total=Object.values(shares).reduce((n,x)=>n+Number(x),0);if(total&&Math.abs(total-100)>.01)throw Error('Cost-share percentages must total 100.');return shares;}
function openBooking(id=null,optionId=null,partId=null){const option=optionId&&S.options[optionId],part=partId&&option.parts.find(p=>p.id===partId),item=part||option,old=id&&S.bookings[id],record=old||{id:uid(),optionId,partId,name:part?.name||(option?title(option):''),fields:copy(item?.fields||{}),quote:copy(item?.quote||{amount:null,currency:S.meta.currency,basis:'total',quantity:1,units:1}),reference:'',balanceDue:null,cancellation:'',attachments:copy(item?.attachments||[]),allocations:{},canceled:false};showEditor(old?'Reservation details':'Record an actual booking',`<form id="booking-form"><p class="muted">This records a reservation you made elsewhere. It does not place, change or cancel a booking with a provider.</p>${field('Reservation name','name',record.name,'text','required maxlength="160"')}${field('Confirmation / booking reference','reference',record.reference||'')}<div class="form-grid">${field('Reserved start date','startDate',record.fields.startDate||'','date')}${field('Reserved end date','endDate',record.fields.endDate||'','date')}${field('Actual booked total','amount',C.quoteTotal(record.quote)??'','number')}${field('Original currency','currency',record.quote.currency||S.meta.currency,'text','required minlength="3" maxlength="3"')}${field('Remaining balance due date','balanceDue',record.balanceDue||'','date')}</div>${field('Cancellation deadline & terms','cancellation',record.cancellation||'','textarea')}${allocationsForm(record.allocations)}<button class="primary">${old?'Save reservation':'Record booking'}</button></form><h3 style="margin:22px 0 10px">Tickets & confirmations</h3>${filesHTML(record.attachments)}${old?'<label>Attach file<input type="file" id="booking-file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.ics,.docx"></label>':''}${old?`<div class="editor-actions">${optButton('+ Payment / refund','payment',`data-booking="${id}"`)}${optButton(record.canceled?'Mark reservation active':'Mark canceled in Furlong','cancel-booking',`data-id="${id}"`,'danger')}</div>`:''}`,'REAL RESERVATION · SHARED ACROSS ALTERNATIVES');editor.querySelector('form').onsubmit=e=>{e.preventDefault();try{const d=formValues(e.target);if(!/^[A-Za-z]{3}$/.test(d.currency))throw Error('Use a three-letter currency.');const next={...record,name:d.name,reference:d.reference,balanceDue:d.balanceDue||null,cancellation:d.cancellation,fields:{...record.fields,startDate:d.startDate||'',endDate:d.endDate||''},quote:{...record.quote,amount:d.amount,basis:'total',currency:d.currency.toUpperCase(),quantity:1,units:1},allocations:allocationsFrom(d)},changes=[['bookings',record.id,next]];if(option){if(partId){const parts=copy(option.parts);parts.find(p=>p.id===partId).bookingId=record.id;changes.push(['options',option.id,{...option,parts}]);}else changes.push(['options',option.id,{...option,bookingId:record.id}]);const g=S.groups[option.groupId];changes.push(['groups',g.id,{...g,selectedId:option.id}]);}addChanges(changes,'Record reservation');editor.pendingSave=null;editor.close();render();}catch(e){toast(e.message);}};if(old)editor.querySelector('#booking-file').onchange=async e=>{if(!e.target.files[0])return;const uploaded=await upload(e.target.files[0]);if(uploaded){editEntity('bookings',id,{attachments:[...record.attachments,uploaded]},'trip','Attach confirmation');openBooking(id);}};wireEditorActions();}
function openPayment(bookingId=null,expenseId=null){const booking=S.bookings[bookingId],expense=S.expenses[expenseId],people=[...vals(S.households).filter(alive),...vals(S.travelers).filter(alive)];showEditor('Record payment or refund',`<form id="payment-form"><p class="muted">Booking status, cost shares and who paid are independent. Record the actual charge in your trip currency.</p>${select('Reservation / expense','target',bookingId?'b:'+bookingId:expenseId?'e:'+expenseId:'',[['','Choose…'],...vals(S.bookings).map(b=>['b:'+b.id,b.name]),...vals(S.expenses).filter(alive).map(e=>['e:'+e.id,e.name])],'required')}${select('Type','kind','payment',[['payment','Payment to provider'],['refund','Refund from provider']])}<div class="form-grid">${field('Amount in original currency','amount','','number','required')}${field('Original currency','currency',booking?.quote?.currency||expense?.currency||S.meta.currency,'text','required minlength="3" maxlength="3"')}${field('Actual amount charged / refunded ('+S.meta.currency+')','baseAmount','','number','required')}${field('Payment date','date',today(),'date','required')}</div>${select('Who paid / received refund','payerId','',[['','Unassigned'],...people.map(p=>[p.id,p.name])])}<button class="primary">Record payment</button></form>`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target),[kind,target]=d.target.split(':'),id=uid();const original=kind==='b'?S.bookings[target]?.quote?.currency:S.expenses[target]?.currency;if(original&&d.currency.toUpperCase()!==original){toast('Use the reservation or expense currency ('+original+'). Record the actual charge separately.');return;}addChanges([['payments',id,{id,bookingId:kind==='b'?target:null,expenseId:kind==='e'?target:null,amount:d.amount,currency:d.currency.toUpperCase(),baseAmount:d.baseAmount,baseCurrency:S.meta.currency,date:d.date,payerId:d.payerId||null,refund:d.kind==='refund',archived:false}]],'Record payment');editor.pendingSave=null;editor.close();render();};}
function openExpense(id=null){const old=id&&S.expenses[id],record=old||{id:uid(),scenarioId:sid,name:'',amount:null,currency:S.meta.currency,category:'other',coveredByAllowance:false,allocations:{},archived:false};showEditor(old?'Edit expense':'Record expense',`<form id="expense-form">${field('Description','name',record.name,'text','required maxlength="160"')}<div class="form-grid">${field('Amount','amount',record.amount??'','number','required')}${field('Currency','currency',record.currency,'text','required minlength="3" maxlength="3"')}${field('Category','category',record.category||'other')}</div><label class="label-row"><input type="checkbox" name="coveredByAllowance" ${record.coveredByAllowance?'checked':''}> Already covered by an existing allowance</label>${allocationsForm(record.allocations)}<button class="primary">Save expense</button></form>${old?`<div class="editor-actions">${optButton('+ Record payment','payment',`data-expense="${id}"`)}${optButton('Remove expense','archive-expense',`data-id="${id}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();try{const d=formValues(e.target);addChanges([['expenses',record.id,{...record,name:d.name,amount:d.amount,currency:d.currency.toUpperCase(),category:d.category,coveredByAllowance:d.coveredByAllowance,allocations:allocationsFrom(d)}]],'Record expense');editor.pendingSave=null;editor.close();render();}catch(e){toast(e.message);}};wireEditorActions();}
function openReimbursement(){const people=[...vals(S.households).filter(alive),...vals(S.travelers).filter(alive)].map(p=>[p.id,p.name]);showEditor('Record reimbursement',`<form id="reimbursement-form">${select('From','fromId','',people,'required')}${select('To','toId','',people,'required')}<div class="form-grid">${field('Amount','amount','','number','required')}${field('Currency','currency',S.meta.currency,'text','required minlength="3" maxlength="3"')}${field('Date','date',today(),'date','required')}</div><p class="muted">This transfer is tracked separately and does not add to the trip cost.</p><button class="primary">Record reimbursement</button></form>`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target);if(d.fromId===d.toId){toast('Choose different people or households.');return;}const id=uid();addChanges([['reimbursements',id,{id,...d,currency:d.currency.toUpperCase(),archived:false}]],'Record reimbursement');editor.close();render();};}
function openTask(id=null){const old=id&&S.tasks[id],record=old||{id:uid(),name:'',scenarioId:sid,stopId:null,optionId:null,status:(prefs().taskStatuses||[])[0]||'To do',dueDate:null,notes:'',custom:{},archived:false};showEditor(old?'Edit task':'Add planning task',`<form id="task-form">${field('Task','name',record.name,'text','required maxlength="160"')}${select('Scope','scenarioId',record.scenarioId||'',[['','Whole trip'],...scenarios().map(s=>[s.id,s.name])])}${select('Linked stop (optional)','stopId',record.stopId||'',[['','None'],...vals(S.stops).filter(alive).map(s=>[s.id,s.name+' · '+S.scenarios[s.scenarioId].name])])}<div class="form-grid">${select('Status','status',record.status,(prefs().taskStatuses||['To do','In progress','Done']).map(s=>[s,s]))}${field('Due date (optional)','dueDate',record.dueDate||'','date')}</div>${field('Notes','notes',record.notes||'','textarea')}${(prefs().taskFields||[]).map(f=>field(f.label,'custom_'+f.key,record.custom?.[f.key]||'')).join('')}<button class="primary">Save task</button></form>${old?`<div class="editor-actions">${optButton('Remove task','archive-task',`data-id="${id}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target),custom={...record.custom};for(const [k,v] of Object.entries(d))if(k.startsWith('custom_'))custom[k.slice(7)]=v;addChanges([['tasks',record.id,{...record,name:d.name,scenarioId:d.scenarioId||null,stopId:d.stopId||null,status:d.status,dueDate:d.dueDate||null,notes:d.notes,custom}]],'Edit task');editor.close();render();};wireEditorActions();}
function openPerson(collection,id=null){const old=id&&S[collection][id],record=old||{id:uid(),name:'',notes:'',householdId:null,archived:false};showEditor((old?'Edit ':'Add ')+(collection==='households'?'household':'traveler'),`<form id="person-form">${field('Name','name',record.name,'text','required maxlength="100"')}${collection==='travelers'?select('Household (optional)','householdId',record.householdId||'',[['','None'],...vals(S.households).filter(alive).map(h=>[h.id,h.name])]):''}${field('Notes','notes',record.notes||'','textarea')}<button class="primary">Save</button></form>${old?`<div class="editor-actions">${optButton('Archive','archive-person',`data-id="${id}" data-collection="${collection}"`,'danger')}</div>`:''}`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target);addChanges([[collection,record.id,{...record,...d,householdId:d.householdId||null}]],'Edit '+collection);editor.close();render();};wireEditorActions();}
function openTemplate(id=null){const old=id&&U.templates[id],record=old||{id:'custom'+uid().slice(0,8),name:'',fields:[],summaryFields:[]};showEditor(old?'Customize '+record.name:'Create an item type',`<form id="template-form">${field('Type name','name',record.name,'text','required maxlength="80"')}<p class="muted">Default fields are optional. Check the fields you want to see in item summaries.</p><div id="template-fields">${record.fields.map((f,i)=>`<div class="part"><div class="form-grid">${field('Field label','label_'+i,f.label,'text','required')}${select('Input type','kind_'+i,f.kind,['text','textarea','number','date','time','url'].map(x=>[x,x]))}</div><label class="label-row"><input name="summary_${i}" type="checkbox" ${record.summaryFields.includes(f.key)?'checked':''}> Show in summaries</label><label class="label-row"><input name="remove_${i}" type="checkbox"> Remove from future defaults</label></div>`).join('')}</div><h3>New field (optional)</h3><div class="form-grid">${field('Label','newLabel','')}${select('Input type','newKind','text',['text','textarea','number','date','time','url'].map(x=>[x,x]))}</div><button class="primary">Save template</button></form>`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const d=formValues(e.target),fields=record.fields.filter((f,i)=>!d['remove_'+i]).map(f=>{const i=record.fields.indexOf(f);return {...f,label:d['label_'+i],kind:d['kind_'+i]};}),summaryFields=record.fields.filter((f,i)=>!d['remove_'+i]&&d['summary_'+i]).map(f=>f.key);if(d.newLabel){const key='custom'+uid().slice(0,10);fields.push({key,label:d.newLabel,kind:d.newKind});}addChanges([['templates',record.id,{...record,name:d.name,fields,summaryFields},'user']],'Customize type template');editor.close();render();};}
function openScenario(id=sid,isNew=false){const record=isNew?{id:uid(),name:'',startDate:null,budget:20000,foodAllowance:0,archived:false}:S.scenarios[id];showEditor(isNew?'New itinerary alternative':'Edit '+record.name,`<form id="scenario-form">${field('Name','name',record.name,'text','required maxlength="100"')}${field('Trip start date (optional)','startDate',record.startDate||'','date')}<div class="form-grid">${field('Budget ceiling ('+S.meta.currency+')','budget',record.budget,'number','required')}${field('Food allowance ('+S.meta.currency+')','foodAllowance',record.foodAllowance||0,'number')}</div>${!isNew?'<label class="check"><input type="checkbox" name="shiftAll"> Also shift every flexible stop, day and option to match the new start date</label>':''}<div id="shift-preview" class="quote-preview">Changing the start date will not move existing itinerary days or reservations.</div><button class="primary">${isNew?'Create alternative':'Save alternative'}</button></form>${!isNew?`<div class="editor-actions">${optButton('Archive alternative','archive-scenario',`data-id="${id}"`,'danger')}</div>`:''}`);const form=editor.querySelector('form');const updatePreview=()=>{const d=form.elements.startDate.value,shift=form.elements.shiftAll?.checked,preview=shift&&!isNew?C.previewScenarioShift(S,id,d||null):null,box=editor.querySelector('#shift-preview');if(!preview||!preview.delta){box.textContent=shift?'No date shift is needed.':'Only the scenario start date changes. Existing dates stay as entered.';return;}const counts={};for(const entry of preview.details)counts[entry.kind]=(counts[entry.kind]||0)+1;box.replaceChildren();const heading=document.createElement('strong');heading.textContent=(preview.delta>0?'+':'')+preview.delta+' days · '+preview.details.length+' dated records move';box.append(heading);const summary=document.createElement('p');summary.textContent=Object.entries(counts).map(([kind,n])=>n+' '+kind).join(', ')||'No flexible dates to move';box.append(summary);const list=document.createElement('details');const label=document.createElement('summary');label.textContent='Review exact date changes';list.append(label);for(const item of preview.details){const p=document.createElement('p');p.textContent=item.label+': '+item.dates.map(d=>d.before+' → '+d.after).join(', ');list.append(p);}box.append(list);if(preview.held.length){const held=document.createElement('p');held.textContent=preview.held.length+' booked or confirmed option(s) retain their dates.';box.append(held);}for(const warning of preview.warnings){const p=document.createElement('p');p.textContent=warning;box.append(p);}};form.elements.startDate.onchange=updatePreview;if(form.elements.shiftAll)form.elements.shiftAll.onchange=updatePreview;form.onsubmit=e=>{e.preventDefault();const d=formValues(e.target),shift=Boolean(form.elements.shiftAll?.checked);const preview=shift&&!isNew?C.previewScenarioShift(S,id,d.startDate||null):null;if(preview?.delta&&!window.confirm('Apply '+preview.details.length+' date changes ('+(preview.delta>0?'+':'')+preview.delta+' days)? '+preview.held.length+' booked/confirmed option(s) will retain their dates.'))return;let changes=isNew?[['scenarios',record.id,{...record,...d,startDate:d.startDate||null}]]:shift?preview.changes:[['scenarios',id,{...record,startDate:d.startDate||null}]];changes[0][2]={...changes[0][2],name:d.name,budget:d.budget,foodAllowance:d.foodAllowance||0};delete changes[0][2].shiftAll;addChanges(changes,'Edit itinerary alternative');sid=record.id;editor.close();render();};wireEditorActions();}
function duplicateScenario(id){const source=S.scenarios[id],newId=uid(),changes=[['scenarios',newId,{...copy(source),id:newId,name:source.name+' copy',legacyId:null}]],map=new Map();for(const col of ['stops','groups','options','days','activities','tasks','expenses'])for(const entity of vals(S[col]).filter(x=>x.scenarioId===id)){const nid=uid();map.set(entity.id,nid);changes.push([col,nid,{...copy(entity),id:nid,scenarioId:newId}]);}for(const [col,nid,entity] of changes.slice(1))for(const key of ['stopId','fromStopId','toStopId','anchorStopId','groupId','selectedId','dayId','optionId','activityId'])if(map.has(entity[key]))entity[key]=map.get(entity[key]);addChanges(changes,'Duplicate alternative');sid=newId;render();toast('Alternative copied. Planning details are independent; actual bookings remain shared.');}
function openCopyOption(id){
 const o=S.options[id],targets=C.copyOptionDestinations(S,id),sourceGroup=S.groups[o?.groupId],sourceStop=S.stops[sourceGroup?.stopId];
 if(!targets.length){showEditor('Copy option','<p>No other current itinerary is available. Create an alternative in Trip settings, then copy this option.</p>');return;}
 showEditor('Copy '+title(o),`<form id="copy-option-form">
 ${select('Destination itinerary','scenarioId','',[['','Choose an itinerary'],...targets.map(t=>[t.scenario.id,t.scenario.name+(t.scenario.id===S.meta.activeScenario?' · Active plan':'')+(t.scenario.startDate?' · '+shortDate(t.scenario.startDate):'')])],'required')}
 <div id="copy-location"></div><div id="copy-group"></div>
 <p class="muted">The copy keeps its dates, quote, notes and links. Review them for the destination itinerary. Planning edits are independent; actual reservation references remain shared.</p>
 <p id="copy-preview" class="quote-preview" role="status" aria-live="polite">Choose where this option belongs.</p>
 <button class="primary" disabled>Copy option</button></form>`);
 const form=editor.querySelector('form'),locationBox=editor.querySelector('#copy-location'),groupBox=editor.querySelector('#copy-group'),preview=editor.querySelector('#copy-preview'),submit=form.querySelector('button');
 const target=()=>targets.find(t=>t.scenario.id===form.elements.scenarioId.value);
 const location=()=>target()?.locations.find(l=>l.id===form.elements.stopId?.value);
 const updatePreview=()=>{
  const t=target(),loc=location(),g=loc?.groups.find(g=>g.id===form.elements.groupId?.value),name=g?.name||form.elements.newGroupName?.value.trim();
  submit.disabled=!t||!loc||!name;
  preview.textContent=t&&loc&&name?`${t.scenario.name} → ${loc.name} → ${name}. Copied dates: ${dateSpan(o.fields?.startDate,o.fields?.endDate)||'Dates open'}.`:'Choose where this option belongs.';
 };
 const updateNewGroup=()=>{
  const creating=form.elements.groupId?.value==='';
  const label=groupBox.querySelector('[data-new-group]');label.hidden=!creating;
  form.elements.newGroupName.disabled=!creating;form.elements.newGroupName.required=creating;updatePreview();
 };
 const updateGroups=()=>{
  const loc=location();if(!loc){groupBox.innerHTML='';updatePreview();return;}
  const defaultName=sourceGroup?.name||'Copied options';
  groupBox.innerHTML=select('Destination group','groupId',loc.preferredGroupId,[...loc.groups.map(g=>[g.id,g.name+(g.type===o.type?' · Matching type':' · '+(U.templates[g.type]?.name||g.type))]),['','Create a new group…']])+
   `<div data-new-group>${field('New group name','newGroupName',defaultName,'text','maxlength="100"')}</div>`;
  form.elements.groupId.onchange=updateNewGroup;form.elements.newGroupName.oninput=updatePreview;updateNewGroup();
 };
 form.elements.scenarioId.onchange=()=>{
  const t=target();if(!t){locationBox.innerHTML='';groupBox.innerHTML='';updatePreview();return;}
  const match=sourceStop?t.locations.find(l=>l.stop&&(l.stop.location||l.name).toLowerCase()===(sourceStop.location||sourceStop.name).toLowerCase()):t.locations.find(l=>!l.stop);
  locationBox.innerHTML=select('City / destination','stopId',match?.id??t.locations[0].id,t.locations.map(l=>[l.id,l.name+(l.stop?.startDate?' · '+dateSpan(l.stop.startDate,C.datePlus(l.stop.startDate,Number(l.stop.nights||0))):'')]));
  form.elements.stopId.onchange=updateGroups;updateGroups();
 };
 form.onsubmit=e=>{
  e.preventDefault();if(!form.reportValidity())return;
  try{const d=formValues(form);addChanges(C.copyOptionChanges(S,id,d.scenarioId,d.stopId,d.groupId,d.newGroupName||''),'Copy option');editor.close();render();toast('Option copied to '+S.scenarios[d.scenarioId].name+'.');}
  catch(error){toast(error.message);}
 };
}
function openCopyStop(id){const st=S.stops[id];showEditor('Copy '+st.name,`<form id="copy-stop">${select('Destination alternative','scenarioId','',scenarios().filter(s=>s.id!==st.scenarioId).map(s=>[s.id,s.name]),'required')}<p class="muted">Copies days, activities, groups and options. Planning details become independent; real booking references stay shared.</p><button class="primary">Copy stop</button></form>`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();const target=formValues(e.target).scenarioId;if(!target){toast('Create another alternative first.');return;}const nid=uid(),changes=[['stops',nid,{...copy(st),id:nid,scenarioId:target,position:C.stops(S,target).length}]],map=new Map([[id,nid]]),gs=C.groups(S,st.scenarioId,id);for(const g of gs){const gid=uid();map.set(g.id,gid);changes.push(['groups',gid,{...copy(g),id:gid,scenarioId:target,stopId:nid}]);for(const o of C.options(S,g.id)){const oid=uid();map.set(o.id,oid);changes.push(['options',oid,{...copy(o),id:oid,scenarioId:target,groupId:gid}]);}}for(const d of vals(S.days).filter(x=>alive(x)&&x.stopId===id)){const did=uid();changes.push(['days',did,{...copy(d),id:did,scenarioId:target,stopId:nid}]);for(const a of vals(S.activities).filter(x=>alive(x)&&x.dayId===d.id)){const aid=uid();map.set(a.id,aid);changes.push(['activities',aid,{...copy(a),id:aid,scenarioId:target,dayId:did,optionId:map.get(a.optionId)||null}]);}}for(const [col,id,item] of changes)if(col==='groups'){if(map.has(item.selectedId))item.selectedId=map.get(item.selectedId);if(item.activityId)item.activityId=map.get(item.activityId)||null;}addChanges(changes,'Copy stop');editor.close();render();toast('Stop copied.');};}
function moveStop(id,newPosition){const ss=C.stops(S,sid),from=ss.findIndex(s=>s.id===id);if(from<0)return;const moved=ss.splice(from,1)[0];ss.splice(Math.max(0,Math.min(Number(newPosition),ss.length)),0,moved);const changes=[];let cursor=activeScenario().startDate||ss.find(s=>s.startDate)?.startDate||null;for(let i=0;i<ss.length;i++){const st=ss[i],newStart=cursor;if(st.startDate&&newStart){const delta=C.dayNumber(newStart)-C.dayNumber(st.startDate);if(delta)changes.push(...shiftStopDetails(st,delta));}changes.push(['stops',st.id,{...st,position:i,startDate:newStart}]);if(cursor)cursor=C.datePlus(cursor,Number(st.nights||0));}for(const g of transfers()){if(g.fromStopId||g.toStopId){const fromIndex=ss.findIndex(s=>s.id===g.fromStopId),toIndex=ss.findIndex(s=>s.id===g.toStopId);if(toIndex!==fromIndex+1)changes.push(['groups',g.id,{...g,needsRouteReview:true}]);}}addChanges(changes,'Move whole stop');render();toast('Whole stop moved. Review affected journeys and provisional quotes.');}
function openMoveStop(id){const ss=C.stops(S,sid);showEditor('Move '+S.stops[id].name,`<form id="move-stop">${select('Position in the journey','position',ss.findIndex(s=>s.id===id),ss.map((s,i)=>[i,(i+1)+' · '+s.name]))}<p class="muted">Its days and flexible plans move with it. Booked dates stay fixed. Existing transport routes are preserved for review.</p><button class="primary">Move stop</button></form>`);editor.querySelector('form').onsubmit=e=>{e.preventDefault();moveStop(id,formValues(e.target).position);editor.close();};}
function pickIdea(groupId,ideaId=null){
 if(!ideaId){
  const ideas=vals(U.ideas).filter(alive);
  if(!ideas.length){toast('Save an idea first, or use Add option to enter it here.');return;}
  simpleForm('Choose a saved idea',select('Idea','ideaId','',[['','Choose an idea'],...ideas.map(i=>[i.id,i.name+' · '+(i.location||i.type)])],'required'),
   data=>openAddIdea(groupId,data.ideaId));
  return;
 }
 showEditor('Use this idea',`<form id="assign-idea">${select('Itinerary alternative','scenarioId',sid,scenarios().map(s=>[s.id,s.name]))}
 <div id="assign-groups"></div><button class="primary">Continue to option details</button></form>`);
 const form=editor.querySelector('#assign-idea');
 const showGroups=()=>{
  const groups=C.groups(S,form.elements.scenarioId.value).filter(g=>!g.stopId||alive(S.stops[g.stopId]));
  form.querySelector('#assign-groups').innerHTML=select('Decision group','groupId',groupId||'',
   [['','Choose a group'],...groups.map(g=>[g.id,(S.stops[g.stopId]?.name||'Trip-wide')+' · '+g.name])],'required');
 };
 form.elements.scenarioId.onchange=showGroups;
 showGroups();
 form.onsubmit=e=>{e.preventDefault();openAddIdea(form.elements.groupId.value,ideaId);};
}
let showUnused=false;
function unusedHTML(){const removed=vals(S.options).filter(o=>o.archived);return `<div class="section-title"><div><h2>Unused planning ideas</h2><p>Removed options keep their dates, quotes and notes. Restore them into any current decision group.</p></div>${optButton('General collection','unused-toggle')}</div><div class="idea-list">${removed.map(o=>`<article class="booking-card"><h3>${text(title(o))}</h3><p class="muted">${text(S.scenarios[o.scenarioId]?.name)} · ${text(dateSpan(o.fields?.startDate,o.fields?.endDate))} · ${C.quoteTotal(o.quote)===null?'Quote needed':money(C.quoteTotal(o.quote),o.quote.currency)}</p><div class="add-row">${optButton('Restore / move to group','restore-option',`data-id="${o.id}"`)}</div></article>`).join('')||empty('No removed options','Options you remove from plans will remain here, with their research intact.')}</div>`;}
function wireEditorActions(){for(const button of editor.querySelectorAll('[data-action]'))button.onclick=e=>{e.preventDefault();dispatch(button).catch(err=>toast(err.message));};}
function simpleForm(heading,html,save){showEditor(heading,`<form id="simple-form">${html}<button class="primary">Save</button></form>`);editor.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await save(formValues(e.target));}catch(err){toast(err.message);}};}
async function dispatch(el){const a=el.dataset.action,id=el.dataset.id,part=el.dataset.part;
if(a==='budget-reset'){budgetTrial={sid,choices:{},extras:[],food:null};render();return;}
if(a==='budget-remove-extra'){budgetTrial.extras.splice(Number(el.dataset.index),1);render();return;}
if(a==='budget-edit-extra'){const i=Number(el.dataset.index),item=budgetTrial.extras[i];if(!item)return;simpleForm('Edit what-if',field('Description','name',item.name,'text','required')+field('Difference','amount',item.amount,'number','required'),d=>{budgetTrial.extras[i]={name:d.name,amount:Number(d.amount)};editor.close();render();});return;}
if(a==='view'){if(el.dataset.view==='ideas')showUnused=false;setView(el.dataset.view);return;}
if(a==='scenario'){sid=id;try{localStorage.setItem('furlong.lastScenario.'+tid,id);}catch(_){}render();return;}
if(a==='jump'){jump(id);return;}
if(a==='density'){editEntity('preferences','display',{density:el.dataset.value},'user','Change view density');render();return;}
if(a==='undo'){undoLast();return;}
if(a==='option'||a==='part'){openOption(id,part);return;}
if(a==='add-idea'){openAddIdea();return;}
if(a==='add-option'){openAddIdea(el.dataset.group);return;}
if(a==='idea'){openIdea(id);return;}
if(a==='use-idea'){pickIdea(null,id);return;}
if(a==='pick-idea'){pickIdea(el.dataset.group);return;}
if(a==='favorite'){editEntity('ideas',id,{favorite:!U.ideas[id].favorite},'user','Favorite idea');render();return;}
if(a==='filter-favorites'){ideaFavorites=!ideaFavorites;render();return;}
if(a==='idea-layout'){ideaList=!ideaList;render();return;}
if(a==='unused-toggle'){showUnused=!showUnused;render();return;}
if(a==='select'){const o=S.options[id];editEntity('groups',o.groupId,{selectedId:id},'trip','Select option');render();return;}
if(a==='unselect'){editEntity('groups',id,{selectedId:null},'trip','Clear selection');render();return;}
if(a==='group'){openGroup(id);return;}
if(a==='add-group'){openGroup(null,el.dataset.stop||null,el.dataset.type||'idea');return;}
if(a==='add-connection'){openGroup(null,null,'transport',el.dataset.from,el.dataset.to);return;}
if(a==='stop'){openStop(id);return;}
if(a==='add-stop'){openStop();return;}
if(a==='move-stop'){openMoveStop(id);return;}
if(a==='copy-stop'){openCopyStop(id);return;}
if(a==='add-day'){openDay(null,el.dataset.stop);return;}
if(a==='day'){openDay(id);return;}
if(a==='day-idea'){openDayIdea(el.dataset.day);return;}
if(a==='plan-activity'){
 const day=firstPlanDay();
 if(day)openActivity(null,day.id);
 else openDay(null,C.stops(S,sid)[0]?.id);
 return;
}
if(a==='add-activity'){openActivity(null,el.dataset.day);return;}
if(a==='activity'){openActivity(id);return;}
if(a==='task'){openTask(id);return;}
if(a==='add-task'){openTask();return;}
if(a==='task-layout'){taskBoard=!taskBoard;render();return;}
if(a==='record-booking'){openBooking(null,id,part);return;}
if(a==='booking'){openBooking(id);return;}
if(a==='payment'){openPayment(el.dataset.booking,el.dataset.expense);return;}
if(a==='expense'){openExpense(id);return;}
if(a==='add-expense'){openExpense();return;}
if(a==='reimbursement'){openReimbursement();return;}
if(a==='traveler'||a==='add-traveler'){openPerson('travelers',id);return;}
if(a==='household'||a==='add-household'){openPerson('households',id);return;}
if(a==='template'||a==='new-template'){openTemplate(id);return;}
if(a==='settings-section'){view='settings';settingsTab=el.dataset.section;render();window.scrollTo({top:0,behavior:'instant'});return;}
if(a==='scenario-settings'){openScenario(id||sid);return;}
if(a==='new-scenario'){openScenario(null,true);return;}
if(a==='duplicate-scenario'){duplicateScenario(id);return;}
if(a==='activate-scenario'){editEntity('meta','trip',{activeScenario:id},'trip','Choose active travel plan');toast('Active travel plan changed. Other alternatives are preserved.');render();return;}
if(a==='travel-today'||a==='travel-whole'){travelWhole=a==='travel-whole';render();return;}
if(a==='dismiss'){const n=C.notices(S,U,sid,fx())[Number(el.dataset.index)],did=uid();if(n){addChanges([['dismissals',did,{id:did,signature:n.id,reason:'Intentional / dismissed',createdAt:new Date().toISOString()}]],'Dismiss notice');render();}return;}
if(a==='notice'){const n=C.notices(S,U,sid,fx())[Number(el.dataset.index)];if(n)jump(n.target);return;}
if(a==='confirm-option'){const o=S.options[id];if(part){const parts=copy(o.parts),p=parts.find(x=>x.id===part);p.confirmed=!p.confirmed;editEntity('options',id,{parts},'trip','Confirm option part');}else editEntity('options',id,{confirmed:!o.confirmed},'trip','Confirm option');openOption(id,part);render();return;}
if(a==='add-part'){
 const fields=field('Part name','name','','text','required')+select('Type','type','transport',templates());
 simpleForm('Add a part',fields,data=>{
  const option=S.options[id];
  if(!alive(option))throw Error('This option is no longer available.');
  const {fields}=contextGroup(option.groupId);
  const part={
   id:uid(),name:data.name,type:data.type,fields,
   quote:{amount:null,currency:S.meta.currency,basis:'total',quantity:1,units:1,
    startDate:fields.startDate,endDate:fields.endDate,conditions:{}},
   quoteHistory:[],bookingId:null,confirmed:false
  };
  editEntity('options',id,{parts:[...(option.parts||[]),part]},'trip','Add option part');
  render();
  openOption(id,part.id);
 });
 return;
}
if(a==='custom-item-field'){simpleForm('Add a field to this item',field('Field label','label','','text','required')+field('Value','value',''),d=>{const o=S.options[id],key='custom'+uid().slice(0,8);if(part){const parts=copy(o.parts),p=parts.find(x=>x.id===part);p.fields[key]=d.value;p.customLabels={...p.customLabels,[key]:d.label};editEntity('options',id,{parts},'trip','Add custom field');}else editEntity('options',id,{fields:{...o.fields,[key]:d.value},customLabels:{...o.customLabels,[key]:d.label}},'trip','Add custom field');openOption(id,part);render();});return;}
if(a==='option-more'){const o=S.options[id],g=S.groups[o.groupId];showEditor(title(o),`<div class="field-list">${optButton('Edit details & quote','option',`data-id="${id}"`)}${optButton('Schedule on an itinerary day','schedule-option',`data-id="${id}"`)}${optButton('Copy into another alternative','copy-option',`data-id="${id}"`)}${optButton(o.stage==='shortlisted'?'Return to idea':'Shortlist','shortlist',`data-id="${id}"`)}${optButton('Remove from this plan','remove-option',`data-id="${id}"`,'danger')}</div><p class="muted" style="margin-top:20px">Removing preserves this occurrence and its quote in Unused planning ideas.</p>`);wireEditorActions();return;}
if(a==='schedule-option'){openScheduleOption(id);return;}
if(a==='option-link'||a==='activity-link'){
 const activity=a==='activity-link'?S.activities[id]:null;
 const linked=S.options[activity?.optionId];
 const option=activity?(alive(linked)&&linked.scenarioId===activity.scenarioId?linked:null):S.options[id];
 const item=part?option.parts.find(p=>p.id===part):option||activity;
 if(!item)return;
 const fallback=part?directLink(option):directLink({},item.ideaId);
 const shared=U.ideas[item.ideaId];
 simpleForm('Edit direct link',linkField(item.website||fallback)+(option&&fallback?'<p class="muted">Leave blank to use the inherited link.</p>':''),data=>{
  const website=option&&data.website===fallback?'':data.website;
  if(option&&part){
   const parts=copy(S.options[option.id].parts);
   parts.find(p=>p.id===part).website=website;
   editEntity('options',id,{parts},'trip','Edit part link');
  }else if(option)editEntity('options',option.id,{website},'trip','Edit option link');
  else if(shared&&!item.website)editEntity('ideas',shared.id,{website:data.website},'user','Edit activity link');
  else editEntity('activities',id,{website:data.website},'trip','Edit activity link');
  if(activity)openActivity(id);else openOption(id,part);
  render();
 });
 return;
}
if(a==='copy-option'){openCopyOption(id);return;}
if(a==='shortlist'){const o=S.options[id];editEntity('options',id,{stage:o.stage==='shortlisted'?'idea':'shortlisted'},'trip','Change shortlist');editor.close();render();return;}
if(a==='remove-option'){const o=S.options[id],g=S.groups[o.groupId],changes=[['options',id,{...o,archived:true}]];if(g.selectedId===id)changes.push(['groups',g.id,{...g,selectedId:null}]);addChanges(changes,'Remove option from plan');editor.pendingSave=null;editor.close();render();toast(C.booking(S,o)?'Removed from plan. The real reservation is still recorded.':'Preserved in Unused planning ideas.');return;}
if(a==='restore-option'){const o=S.options[id];simpleForm('Restore '+title(o),select('Decision group','groupId',o.groupId,vals(S.groups).filter(alive).map(g=>[g.id,S.scenarios[g.scenarioId].name+' · '+(S.stops[g.stopId]?.name||'Transport')+' · '+g.name]),'required'),d=>{const g=S.groups[d.groupId];if(!g)throw Error('Choose a current group.');editEntity('options',id,{groupId:g.id,scenarioId:g.scenarioId,archived:false},'trip','Restore option');editor.close();render();});return;}
if(a==='archive-group'){const g=S.groups[id],changes=[['groups',id,{...g,archived:true,selectedId:null}]];for(const o of C.options(S,id))changes.push(['options',o.id,{...o,archived:true}]);addChanges(changes,'Remove decision group');if(editor.open)editor.close();render();return;}
if(a==='archive-stop'){const st=S.stops[id],gs=C.groups(S,st.scenarioId,id),changes=[['stops',id,{...st,archived:true}]];for(const g of gs){changes.push(['groups',g.id,{...g,archived:true,selectedId:null}]);for(const o of C.options(S,g.id))changes.push(['options',o.id,{...o,archived:true}]);}for(const d of vals(S.days).filter(d=>d.stopId===id)){changes.push(['days',d.id,{...d,archived:true}]);for(const a of vals(S.activities).filter(a=>a.dayId===d.id))changes.push(['activities',a.id,{...a,dayId:null}]);}addChanges(changes,'Remove stop from plan');editor.close();render();return;}
if(a==='archive-day'){const d=S.days[id],changes=[['days',id,{...d,archived:true}]];for(const act of vals(S.activities).filter(a=>a.dayId===id))changes.push(['activities',act.id,{...act,dayId:null}]);addChanges(changes,'Remove day');editor.close();render();return;}
if(a==='unschedule-activity'){editEntity('activities',id,{dayId:null},'trip','Unschedule activity');editor.close();render();return;}
if(a==='archive-idea'){editEntity('ideas',id,{archived:true},'user','Archive idea');editor.close();render();return;}
if(a==='archive-task'||a==='archive-expense'||a==='archive-person'){const collection=a==='archive-task'?'tasks':a==='archive-expense'?'expenses':el.dataset.collection;editEntity(collection,id,{archived:true},'trip','Archive item');editor.close();render();return;}
if(a==='archive-scenario'){if(id===S.meta.activeScenario){toast('Choose another active travel plan before archiving this one.');return;}editEntity('scenarios',id,{archived:true},'trip','Archive alternative');if(sid===id)sid=S.meta.activeScenario;editor.close();render();return;}
if(a==='cancel-booking'){editEntity('bookings',id,{canceled:!S.bookings[id].canceled},'trip','Update recorded cancellation');openBooking(id);render();toast('Updated in Furlong only. Contact the provider to change the actual reservation.');return;}
if(a==='rate-lock'){editEntity('meta','trip',{rateLock:S.meta.rateLock?null:{base:S.meta.currency,rates:copy(fx()),asOf:rates.asOf||today()}},'trip','Set planning exchange rates');render();return;}
if(a==='refresh-rates'){await loadRates(true);render();return;}
if(a==='download-offline'){await downloadOffline();return;}
if(a==='export-backup'){await persist();const data={exportedAt:new Date().toISOString(),state:S,user:U,pendingOperations:queue};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='furlong-trip-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);return;}
if(a==='print'){window.print();return;}
if(a==='sync-now'){syncError='';await flush();return;}
if(a==='logout'){if(queue.length){await flush();if(queue.length){toast('Sync or export pending changes before signing out.');return;}}const csrf=bundle.csrf;if(db){const tx=db.transaction('documents','readwrite');tx.objectStore('documents').delete('currentUser');tx.objectStore('documents').delete(bundle.userId+':'+tid);}for(const name of await caches.keys())if(name.startsWith('furlong-offline-v2-'))await caches.delete(name);const form=document.createElement('form');form.method='POST';form.action='/logout';const input=document.createElement('input');input.type='hidden';input.name='_csrf_token';input.value=csrf;form.append(input);document.body.append(form);form.submit();return;}
}
app.addEventListener('click',event=>{const el=event.target.closest('[data-action]');if(el){event.preventDefault();dispatch(el).catch(e=>toast(e.message));}});
function wireView(){
const form=(id,fn)=>{const el=document.getElementById(id);if(el)el.onsubmit=e=>{e.preventDefault();Promise.resolve(fn(formValues(el))).catch(err=>toast(err.message));};};
form('display-settings',d=>{editEntity('preferences','display',d,'user','Save display preferences');render();});
form('trip-name-form',d=>{editEntity('meta','trip',{name:d.name},'trip','Rename trip');render();});
form('time-blocks-form',d=>{const blocks=d.blocks.split('\n').map(s=>s.trim()).filter(Boolean).map(s=>{const [name,start='']=s.split('|').map(x=>x.trim());if(start&&!/^([01]\d|2[0-3]):[0-5]\d$/.test(start))throw Error('Use time values such as 06:00, or leave them blank.');return {name,start};});editEntity('preferences','display',{timeBlocks:blocks},'user','Customize time blocks');toast('Time blocks saved.');});
form('task-settings',d=>{const statuses=[...new Set(d.statuses.split('\n').map(s=>s.trim()).filter(Boolean))];if(!statuses.includes('Done'))statuses.push('Done');const old=prefs().taskFields||[],taskFields=d.taskFields.split('\n').map(s=>s.trim()).filter(Boolean).map(label=>old.find(f=>f.label===label)||{key:'custom'+uid().slice(0,8),label});editEntity('preferences','display',{tasksEnabled:d.tasksEnabled,taskStatuses:statuses,taskFields},'user','Customize planning tasks');render();});
form('currency-form',async d=>{editEntity('meta','trip',{currency:d.currency,rateLock:null},'trip','Change trip currency');await loadRates();render();});
form('manual-rate',d=>{if(!/^[A-Za-z]{3}$/.test(d.currency)||!(d.rate>0))throw Error('Enter a three-letter currency and a positive rate.');editEntity('meta','trip',{rateLock:{base:S.meta.currency,rates:{...fx(),[d.currency.toUpperCase()]:d.rate},asOf:today()}},'trip','Set manual planning rate');render();});
const search=document.getElementById('idea-search');if(search)search.oninput=()=>{ideaSearch=search.value;clearTimeout(search.timer);search.timer=setTimeout(()=>{const position=search.selectionStart;render();const next=document.getElementById('idea-search');next.focus();next.setSelectionRange(position,position);},180);};
const ideaScopeFilter=document.querySelector('[name="idea-scope"]');if(ideaScopeFilter)ideaScopeFilter.onchange=()=>{ideaScope=ideaScopeFilter.value;ideaCity='';render();};
const cityFilter=document.querySelector('[name="idea-city"]');if(cityFilter)cityFilter.onchange=()=>{ideaCity=cityFilter.value;render();};
const filter=document.querySelector('[name="idea-filter"]');if(filter)filter.onchange=()=>{ideaType=filter.value;render();};
const mapSelect=document.querySelector('[name="map-day"]');if(mapSelect)mapSelect.onchange=()=>{mapDay=mapSelect.value;render();};
for(const [id,key] of [['map-backups','mapBackups'],['map-unscheduled','mapUnscheduled'],['reimbursement-enabled','trackReimbursements']]){const el=document.getElementById(id);if(el)el.onchange=()=>{editEntity('preferences','display',{[key]:el.checked},'user','Change display preference');render();};}
let dragged=null;for(const stop of document.querySelectorAll('[data-stop-id]')){stop.addEventListener('dragstart',e=>{if(e.target.closest('button,input,textarea,select')&&!e.target.closest('.drag-handle')){e.preventDefault();return;}dragged=stop.dataset.stopId;stop.classList.add('dragging');e.dataTransfer.setData('text/plain',dragged);});stop.addEventListener('dragend',()=>stop.classList.remove('dragging'));stop.addEventListener('dragover',e=>{if(dragged)e.preventDefault();});stop.addEventListener('drop',e=>{e.preventDefault();if(dragged&&dragged!==stop.dataset.stopId){const index=C.stops(S,sid).findIndex(s=>s.id===stop.dataset.stopId);moveStop(dragged,index);}dragged=null;});}
}
async function loadRates(refresh=false){if(!navigator.onLine)return;try{const r=await requestAPI(`/api/planner/${tid}/rates?base=${S.meta.currency}${refresh?'&refresh=1':''}`);if(!r.ok)throw Error();rates=await r.json();rates.checkedOn=today();persist();}catch(_){if(!rates.base||rates.base!==S.meta.currency)rates={base:S.meta.currency,rates:{[S.meta.currency]:1},asOf:null};if(refresh)toast('Rates could not refresh. The last available values are retained.');}}
async function downloadOffline(){if(!('serviceWorker'in navigator)||!('caches'in window)){toast('Offline downloads are unavailable in this browser. Export a trip backup instead.');return;}if(!navigator.onLine){toast('Connect to download or update the offline copy.');return;}try{await flush();if(queue.length)throw Error('Resolve pending edits before updating the offline copy.');const registration=await navigator.serviceWorker.register('/planner-sw.js');await navigator.serviceWorker.ready;const worker=registration.active||registration.waiting||registration.installing,files=[...new Map([...vals(U.ideas).flatMap(i=>i.image?[i.image]:[]),...vals(S.bookings).flatMap(b=>b.attachments||[]),...vals(S.options).flatMap(o=>[...(o.attachments||[]),...(o.parts||[]).flatMap(p=>p.attachments||[])])].map(f=>[f.id,f])).values()];const urls=[location.pathname,'/static/planner.css?v=7',...Array.from(document.querySelectorAll('script[src*="/static/planner"]'),script=>script.src),'/static/furlong-bear.svg',...files.map(f=>f.url)];await new Promise((resolve,reject)=>{const channel=new MessageChannel();const timeout=setTimeout(()=>reject(Error('Offline download timed out. Try again while connected.')),45000);channel.port1.onmessage=e=>{clearTimeout(timeout);e.data.ok?resolve():reject(Error(e.data.error||'Some files could not download.'));};worker.postMessage({type:'DOWNLOAD',userId:bundle.userId,tripId:tid,urls},[channel.port2]);});offlineReady=new Date().toLocaleString();await persist();toast('Trip and attached reservation files downloaded for offline use.');render();}catch(e){toast(e.message);}}
async function bootstrap(){try{try{db=await openDB();}catch(_){db=null;}
let cached=null,currentUser=db&&await storeGet('currentUser');if(db&&currentUser)cached=await storeGet(currentUser+':'+tid);
let data;try{const response=await fetch(`/api/planner/${tid}`,{headers:{'Accept':'application/json'},cache:'no-store'});if(!response.ok||response.redirected){const error=Error('Sign in to open this trip.');error.accessDenied=true;throw error;}data=await response.json();if(!data.state){const error=Error('Sign in to open this trip.');error.accessDenied=true;throw error;}if(db){await storePut('currentUser',data.userId);cached=await storeGet(data.userId+':'+tid);}queue=cached?.queue||[];undo=cached?.undo||[];rates=cached?.rates||rates;offlineReady=cached?.offlineReady||false;integrate(data);}catch(error){if(error.accessDenied||!cached)throw error;bundle=cached;S=cached.state;U=cached.user;queue=cached.queue||[];undo=cached.undo||[];rates=cached.rates||rates;offlineReady=cached.offlineReady||false;syncError=navigator.onLine?'Connection unavailable. Working from the last local copy.':'';}
sid=S.meta.activeScenario||scenarios()[0]?.id;const params=new URLSearchParams(location.search),legacy=params.get('scenario');if(legacy){const match=scenarios().find(s=>String(s.legacyId)===legacy||s.id===legacy);if(match)sid=match.id;}else{try{const last=localStorage.getItem('furlong.lastScenario.'+tid);if(last&&S.scenarios[last]&&!S.scenarios[last].archived)sid=last;}catch(_){}}
view=['plan','ideas','map','compare','travel','tasks','budget','settings'].includes(params.get('view'))?params.get('view'):'plan';render();await persist();flush();loadRates().then(()=>{if(!editor.open)render();});
window.addEventListener('online',async()=>{syncError='';try{const r=await fetch(`/api/planner/${tid}`,{cache:'no-store'});if(r.ok&&!r.redirected){const fresh=await r.json();if(fresh.userId!==bundle.userId){toast('A different account is signed in. Reload to continue.');return;}integrate(fresh);persist();}}catch(_){}flush();loadRates();render();});window.addEventListener('offline',()=>{persist();render();});window.addEventListener('beforeunload',e=>{if(queue.length&&syncError){e.preventDefault();e.returnValue='';}});setInterval(()=>{if(rates.checkedOn!==today())loadRates();},60000);
}catch(error){app.innerHTML=`<div class="boot"><span class="wordmark">furlong.</span><h2 style="margin-top:20px">Your journey is safe</h2><p>${text(error.message||'The workspace could not open.')}</p><p><a class="button primary" href="/login">Sign in</a> <a class="button" href="/">My journeys</a></p></div>`;}}
// Keep removed planning records discoverable from the idea collection.
const regularIdeas=ideasHTML;ideasHTML=function(){return showUnused?unusedHTML():regularIdeas().replace('<div class="toolbar">','<div class="toolbar">'+optButton('Unused planning items','unused-toggle'));};
await bootstrap();
})();
