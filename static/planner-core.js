/* Pure planning calculations shared by UI actions and regression tests. */
((root,factory)=>{const core=factory();if(typeof module==='object'&&module.exports)module.exports=core;else root.FurlongCore=core;})(typeof globalThis!=='undefined'?globalThis:this,()=>{
'use strict';
const values=o=>Object.values(o||{}),clone=o=>JSON.parse(JSON.stringify(o)),alive=o=>o&&!o.archived;
const uid=()=>typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID().replaceAll('-',''):Date.now().toString(36)+Math.random().toString(36).slice(2);
const dayNumber=d=>d?Math.round(Date.parse(d+'T12:00:00Z')/86400000):null;
const datePlus=(d,n)=>d?new Date(Date.parse(d+'T12:00:00Z')+n*86400000).toISOString().slice(0,10):'';
const byPosition=(a,b)=>(a.position||0)-(b.position||0)||String(a.id).localeCompare(String(b.id));
const stops=(s,sid)=>values(s.stops).filter(x=>alive(x)&&x.scenarioId===sid).sort(byPosition);
const groups=(s,sid,stopId)=>values(s.groups).filter(x=>alive(x)&&x.scenarioId===sid&&(stopId===undefined||x.stopId===stopId)).sort(byPosition);
const options=(s,gid)=>values(s.options).filter(x=>alive(x)&&x.groupId===gid).sort(byPosition);
// A live child is not a destination when its itinerary or stop was archived.
function copyOptionDestinations(s,optionId){
 const source=s.options[optionId];
 if(!alive(source))return [];
 return values(s.scenarios).filter(x=>alive(x)&&x.id!==source.scenarioId)
  .sort((a,b)=>Number(b.id===s.meta.activeScenario)-Number(a.id===s.meta.activeScenario)||a.name.localeCompare(b.name))
  .map(scenario=>({scenario,locations:[...stops(s,scenario.id).map(stop=>({id:stop.id,name:stop.name,stop})),
   {id:'',name:'Transport & trip-wide groups',stop:null}].map(location=>({...location,
    groups:groups(s,scenario.id,location.id||null).sort((a,b)=>Number(b.type===source.type)-Number(a.type===source.type)||byPosition(a,b))}))}));
}
function copyOptionChanges(s,optionId,scenarioId,stopId,groupId,newGroupName='',makeId=uid){
 const source=s.options[optionId],target=copyOptionDestinations(s,optionId).find(x=>x.scenario.id===scenarioId),
  location=target?.locations.find(x=>x.id===(stopId||''));
 if(!location)throw Error('Choose a current itinerary and destination.');
 let group=location.groups.find(g=>g.id===groupId);const changes=[];
 if(groupId){if(!group)throw Error('This destination group is no longer available.');}
 else {
  const name=newGroupName.trim();if(!name||name.length>100)throw Error('Enter a group name up to 100 characters.');
  const id=makeId();group={id,scenarioId,stopId:stopId||null,name,type:source.type,selectedId:null,allowance:null,
   position:location.groups.reduce((n,g)=>Math.max(n,Number(g.position||0)+1),0),notes:'',archived:false};
  changes.push(['groups',id,group]);
 }
 const id=makeId();changes.push(['options',id,{...clone(source),id,scenarioId,groupId:group.id,
  position:options(s,group.id).reduce((n,o)=>Math.max(n,Number(o.position||0)+1),0),archived:false}]);
 return changes;
}
// Each shared journey appears exactly once. Explicit placement wins; dates
// place outside-trip flights without changing the stop sequence or its dates.
function journeySlots(s,sid){
 const ss=stops(s,sid),result={before:[],after:Object.fromEntries(ss.map(st=>[st.id,[]])),shared:[]};
 for(const g of groups(s,sid).filter(g=>!g.stopId)){
  let anchor=null,before=false;
  if(g.itineraryPlacement==='before')before=true;
  else if(g.itineraryPlacement==='after')anchor=ss.find(st=>st.id===g.anchorStopId)?.id;
  else {
   anchor=ss.find(st=>st.id===g.fromStopId)?.id;
   if(!anchor&&g.toStopId){const i=ss.findIndex(st=>st.id===g.toStopId);if(i===0)before=true;else if(i>0)anchor=ss[i-1].id;}
   if(!anchor&&!before){
    const selected=s.options[g.selectedId],opts=selected&&alive(selected)?[selected]:options(s,g.id);
    const dates=opts.flatMap(o=>(o.parts?.length?o.parts:[o]).map(p=>p.fields?.startDate)).filter(Boolean).sort();
    const date=dates[0]||g.startDate;
    if(date&&ss.length&&ss.every(st=>st.startDate)){
     if(date<=ss[0].startDate)before=true;
     else {const i=ss.findIndex(st=>st.startDate>=date);anchor=(i<0?ss.at(-1):ss[i-1]).id;}
    }
   }
  }
  if(before)result.before.push(g);else if(anchor)result.after[anchor].push(g);else result.shared.push(g);
 }
 return result;
}
function itemNotes(item,user,s){
 const shared=user?.ideas?.[item?.ideaId]?.notes||'',planning=item?.fields?.notes??item?.notes??'',linked=item?.optionId&&s?.options?.[item.optionId];
 const linkedNotes=alive(linked)&&linked.scenarioId===item.scenarioId?linked.fields?.notes:'';
 return [...new Set([shared,linkedNotes,planning].filter(n=>String(n).trim()))];
}
function scheduledActivity(s,option){
 const activities=values(s.activities).filter(a=>alive(a)&&a.scenarioId===option.scenarioId);
 return activities.find(a=>a.optionId===option.id)||activities.find(a=>option.ideaId&&a.ideaId===option.ideaId);
}
function scheduleActivityChange(s,option,day,name,fields,makeId=uid){
 if(!alive(day)||day.scenarioId!==option.scenarioId)throw Error('Choose a day in this itinerary.');
 const existing=scheduledActivity(s,option),id=existing?.id||makeId();
 const position=existing?.dayId===day.id?existing.position:
  values(s.activities).filter(a=>alive(a)&&a.dayId===day.id).reduce((n,a)=>Math.max(n,Number(a.position||0)+1),0);
 return ['activities',id,{...existing,id,scenarioId:option.scenarioId,dayId:day.id,ideaId:option.ideaId,optionId:option.id,
  name:existing?.optionId===option.id?existing.name:name,time:fields.startTime||'',timeBlock:fields.timeBlock||'',
  duration:existing?.duration??fields.duration??null,notes:existing?.notes||'',confirmed:existing?.confirmed??!!option.confirmed,
  position,archived:false}];
}
// An explicit quote creates a normal selected option, never a second expense.
// Linked alternatives keep their group, history, booking and selection intact.
function activityQuoteChanges(s,a,quote,include,makeId=uid){
 const linked=s.options[a.optionId],existing=alive(linked)?linked:null;
 if(existing&&existing.scenarioId!==a.scenarioId)throw Error('Activity quotes stay within their itinerary alternative.');
 if(existing?.parts?.length)throw Error('Edit the individual option parts to change this quote.');
 if(existing&&booking(s,existing))throw Error('Edit the reservation to change its booked price.');
 if(quote.amount!==null&&(!Number.isFinite(quote.amount)||quote.amount<0))throw Error('Enter a nonnegative price.');
 if(!/^[A-Z]{3}$/.test(quote.currency))throw Error('Use a three-letter currency code.');
 for(const k of ['quantity','units'])if(!Number.isFinite(quote[k])||quote[k]<=0)throw Error('Enter a quantity greater than zero.');
 const day=s.days[a.dayId],date=day?.date||(s.stops[day?.stopId]?.startDate?datePlus(s.stops[day.stopId].startDate,Number(day.position||0)):'');
 const fields=existing?.fields||{startDate:date||'',startTime:a.time||'',timeBlock:a.timeBlock||'',duration:a.duration??null,notes:a.notes||''};
 const gid=existing?.groupId||makeId(),oid=existing?.id||makeId();
 const next={...existing,id:oid,groupId:gid,scenarioId:a.scenarioId,ideaId:existing?.ideaId||a.ideaId,type:existing?.type||'activity',label:existing?.label||a.name,fields,
  ...(existing?.website||a.website?{website:existing?.website||a.website}:{}),
  quote:{...quote,startDate:fields.startDate||'',endDate:fields.endDate||'',conditions:conditions(fields),checkedAt:new Date().toISOString()},
  quoteHistory:[...(existing?.quoteHistory||[]),...(existing?.quote?[clone(existing.quote)]:[])],archived:false};
 const changes=[];
 if(!existing)changes.push(['groups',gid,{id:gid,scenarioId:a.scenarioId,stopId:day?.stopId||null,name:a.name,type:'activity',selectedId:include?oid:null,allowance:null,position:groups(s,a.scenarioId,day?.stopId||null).length,activityId:a.id,archived:false}]);
 changes.push(['options',oid,next],['activities',a.id,{...a,optionId:oid}]);
 return changes;
}
const title=(o,user)=>o.label||user.ideas[o.ideaId]?.name||o.name||'Untitled idea';
const booking=(s,o)=>o.bookingId&&s.bookings[o.bookingId]&&!s.bookings[o.bookingId].canceled?s.bookings[o.bookingId]:null;
const status=(s,o,g)=>{if(o.parts?.length){const n=o.parts.filter(p=>booking(s,p)||p.confirmed).length;if(n===o.parts.length)return 'Booked / confirmed';if(n)return 'Partially booked';}if(booking(s,o))return 'Booked';if(o.confirmed)return 'Confirmed';if(g?.selectedId===o.id)return 'Selected';return o.stage==='shortlisted'?'Shortlisted':'Idea';};
const conditions=f=>Object.fromEntries(['rooms','guests','travelers','vehicles','roomType','baggage'].filter(k=>f?.[k]!==undefined&&f[k]!=='').map(k=>[k,f[k]]));
function needsRecheck(o){const q=o.quote;if(!q||q.amount===null||q.amount===undefined)return false;return (q.startDate||'')!==(o.fields?.startDate||'')||(q.endDate||'')!==(o.fields?.endDate||'')||Object.entries(q.conditions||{}).some(([k,v])=>JSON.stringify(v)!==JSON.stringify(o.fields?.[k]));}
const quoteTotal=q=>q?.amount===null||q?.amount===undefined?null:Number(q.amount)*(q.basis==='total'?1:Number(q.quantity??1)*Number(q.units??1));
const exchange=(amount,currency,base,rates)=>currency===base?Number(amount):rates?.[currency]?Number(amount)*Number(rates[currency]):null;
function cost(s,o,fx,seen=new Set()){
if(o.parts?.length){const list=o.parts.map(p=>cost(s,p,fx,seen));return {amount:list.reduce((n,c)=>n+c.amount,0),unknown:list.some(c=>c.unknown),provisional:list.some(c=>c.provisional),paid:list.reduce((n,c)=>n+c.paid,0)};}
const reservation=booking(s,o),q=reservation?.quote||o.quote,original=quoteTotal(q),base=s.meta.currency;
if(reservation&&seen.has(reservation.id))return {amount:0,paid:0,unknown:false,provisional:false};
if(reservation)seen.add(reservation.id);
let paid=0,paidOriginal=0,missingPaymentRate=false;
for(const p of values(s.payments).filter(p=>alive(p)&&(reservation?p.bookingId===reservation.id:o.expenseId?p.expenseId===o.expenseId:p.optionId===o.id))){const sign=p.refund?-1:1,n=exchange(p.baseAmount||0,p.baseCurrency||base,base,fx);if(n===null)missingPaymentRate=true;else paid+=sign*n;if(p.currency===q?.currency)paidOriginal+=sign*Number(p.amount||0);}
const remaining=original===null?null:Math.max(0,original-paidOriginal),converted=remaining===null?null:exchange(remaining,q.currency||base,base,fx);
return {amount:paid+(converted??0),unknown:original===null||converted===null||missingPaymentRate,provisional:!reservation&&needsRecheck(o),paid};}
function budget(s,sid,fx){let amount=0,unknown=0,provisional=0,paid=0;const seen=new Set();for(const g of groups(s,sid)){const o=s.options[g.selectedId];if(o&&alive(o)){const c=cost(s,o,fx,seen);amount+=c.amount;unknown+=Number(c.unknown);provisional+=Number(c.provisional);paid+=c.paid;}else if(g.allowance!==null&&g.allowance!==undefined)amount+=Number(g.allowance);}
const scenario=s.scenarios[sid];amount+=Number(scenario?.foodAllowance||0);
for(const exp of values(s.expenses).filter(x=>alive(x)&&x.scenarioId===sid)){const c=cost(s,{id:exp.id,expenseId:exp.id,quote:{amount:exp.amount,currency:exp.currency||s.meta.currency,basis:'total'}},fx);paid+=c.paid;if(!exp.coveredByAllowance){amount+=c.amount;unknown+=Number(c.unknown);}}
return {amount,unknown,provisional,paid,remaining:Number(scenario?.budget||0)-amount};}
function zonedStamp(date,time,zone){if(!date||!time||!zone)return null;try{const target=Date.parse(date+'T'+time+':00Z');const formatter=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});let stamp=target;for(let i=0;i<3;i++){const parts=Object.fromEntries(formatter.formatToParts(new Date(stamp)).map(x=>[x.type,x.value]));const local=Date.parse(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}Z`);stamp+=target-local;}return stamp;}catch(_){return null;}}
function duration(o){if(o.parts?.length)return o.parts.reduce((n,p)=>n+(duration(p)||0),0);const f=o.fields||{};if(Number(f.duration)>0)return Number(f.duration);const a=zonedStamp(f.startDate,f.departureTime,f.originZone),b=zonedStamp(f.endDate||f.startDate,f.arrivalTime,f.destinationZone);return a!==null&&b!==null&&b>=a?(b-a)/3600000:null;}
function notices(s,user,sid,fx){const list=[],add=(kind,target,name,detail)=>{const signature=[kind,target,name,detail].join('|');if(!values(s.dismissals).some(d=>d.signature===signature))list.push({id:signature,kind,target,name,detail});};
const gs=groups(s,sid),ss=stops(s,sid),selected=gs.map(g=>s.options[g.selectedId]).filter(alive),lodging=[];
for(const g of gs){if(g.needsRouteReview)add('route',g.id,g.name,'The stop order changed. Review this researched connection.');const o=s.options[g.selectedId];if(!o){add('decision',g.stopId||g.id,g.name,'No option selected'+(g.allowance!=null?'; allowance is included in the estimate.':'.'));continue;}const c=cost(s,o,fx),n=title(o,user);if(c.unknown)add('quote',g.stopId||g.id,n,'A price or currency conversion is missing. The total is incomplete.');if(c.provisional)add('quote',g.stopId||g.id,n,'Previous quote retained provisionally. Recheck dates and conditions when ready.');
const parts=o.parts?.length?o.parts:[o];for(const p of parts){const b=booking(s,p);if(b&&['startDate','endDate'].some(k=>(b.fields?.[k]||'')!==(p.fields?.[k]||'')))add('booking',g.stopId||g.id,n,'The working dates differ from the actual reservation.');}
if(['hotel','castle'].includes(o.type)&&o.fields?.startDate&&o.fields?.endDate)lodging.push({o,g});
if(['transport','flight'].includes(g.type)&&g.startDate&&o.fields?.startDate&&g.startDate!==o.fields.startDate)add('route',g.id,n,'This researched journey needs review for the current connection.');}
lodging.sort((a,b)=>(a.o.fields.startDate||'').localeCompare(b.o.fields.startDate||''));for(let i=1;i<lodging.length;i++){const a=lodging[i-1],b=lodging[i];if(a.o.fields.endDate!==b.o.fields.startDate)add('stay',b.g.stopId||b.g.id,'Stay date conflict',`${title(a.o,user)} ends ${a.o.fields.endDate}; ${title(b.o,user)} starts ${b.o.fields.startDate}.`);}
for(const st of ss){const actual=selected.filter(o=>s.groups[o.groupId]?.stopId===st.id&&['hotel','castle'].includes(o.type));if(st.startDate&&st.nights&&actual.length){const end=datePlus(st.startDate,Number(st.nights));const first=actual.map(o=>o.fields.startDate).filter(Boolean).sort()[0],last=actual.map(o=>o.fields.endDate).filter(Boolean).sort().at(-1);if(first&&last&&(first>st.startDate||last<end))add('stay',st.id,st.name+' · Uncovered night','Selected lodging does not cover the whole stop.');}}
for(const b of values(s.bookings).filter(x=>!x.canceled)){const used=selected.some(o=>o.bookingId===b.id||o.parts?.some(p=>p.bookingId===b.id));if(!used)add('booking','bookings',b.name,'A real reservation is not used by this alternative.');if(b.balanceDue&&b.balanceDue<=datePlus(new Date().toISOString().slice(0,10),7))add('payment','bookings',b.name,'Payment due '+b.balanceDue+'.');}
const acts=values(s.activities).filter(x=>alive(x)&&x.scenarioId===sid&&x.time&&/^\d\d:\d\d$/.test(x.time));for(let i=0;i<acts.length;i++)for(let j=i+1;j<acts.length;j++){const a=acts[i],b=acts[j];if(a.dayId!==b.dayId)continue;const mins=t=>Number(t.slice(0,2))*60+Number(t.slice(3));if(Math.abs(mins(a.time)-mins(b.time))<Number(a.duration||1)*60)add('schedule',s.days[b.dayId]?.stopId||b.dayId,'Overlapping activities',a.name+' and '+b.name+' may overlap.');}
return list;}
function diff(before,after,path='',result={}){for(const key of new Set([...Object.keys(before||{}),...Object.keys(after||{})])){if(key==='id'||['__proto__','constructor','prototype'].includes(key))continue;const a=before?.[key],b=after?.[key],p=path?path+'.'+key:key;if(JSON.stringify(a)===JSON.stringify(b))continue;if(b&&a&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b))diff(a,b,p,result);else result[p]={base:a??null,value:b??null};}return result;}
function setPath(object,path,value){const parts=path.split('.');if(parts.some(k=>['__proto__','constructor','prototype'].includes(k)))throw Error('Invalid field');let p=object;for(const key of parts.slice(0,-1))p=p[key]&&typeof p[key]==='object'?p[key]:(p[key]={});p[parts.at(-1)]=clone(value);}
function patch(document,op){const parent=op.collection==='meta'?document:document[op.collection];let entity=op.collection==='meta'?document.meta:parent[op.id];if(!entity)entity=parent[op.id]={id:op.id};for(const [key,val] of Object.entries(op.patch))setPath(entity,key,val);}
function operations(scope,collection,id,before,after){const d=diff(before||{},after);if(!Object.keys(d).length)return null;return {opId:uid(),scope,collection,id,create:!before,base:Object.fromEntries(Object.entries(d).map(([k,v])=>[k,v.base])),patch:Object.fromEntries(Object.entries(d).map(([k,v])=>[k,v.value]))};}
function shiftScenario(s,sid,newStart){const scenario=s.scenarios[sid],delta=scenario.startDate&&newStart?dayNumber(newStart)-dayNumber(scenario.startDate):0;const changes=[];changes.push(['scenarios',sid,{...scenario,startDate:newStart||null}]);if(!delta)return changes;
for(const kind of ['stops','days','groups','activities','options'])for(const entity of values(s[kind]).filter(x=>x.scenarioId===sid&&!x.archived)){if(kind==='days'&&s.stops[entity.stopId]?.archived)continue;if(kind==='groups'&&s.stops[entity.stopId]?.archived)continue;if(kind==='activities'&&(s.days[entity.dayId]?.archived||s.stops[s.days[entity.dayId]?.stopId]?.archived))continue;if(kind==='options'&&(s.groups[entity.groupId]?.archived||s.stops[s.groups[entity.groupId]?.stopId]?.archived))continue;const next=clone(entity);if(kind==='options'){const parts=next.parts?.length?next.parts:[next];for(const p of parts)if(!p.archived&&!p.confirmed&&!booking(s,p)){for(const field of ['startDate','endDate'])if(p.fields?.[field])p.fields[field]=datePlus(p.fields[field],delta);}}else for(const field of ['startDate','endDate','date'])if(next[field])next[field]=datePlus(next[field],delta);changes.push([kind,entity.id,next]);}
return changes;}
function previewScenarioShift(s,sid,newStart){
 const scenario=s.scenarios[sid],oldStart=scenario?.startDate||null;
 const delta=oldStart&&newStart?dayNumber(newStart)-dayNumber(oldStart):0;
 const changes=shiftScenario(s,sid,newStart);
 const details=[],moved=new Set();
 for(const [kind,id,next] of changes){
  if(kind==='scenarios')continue;
  const previous=s[kind][id],dates=[];
  if(kind==='options'){
   const oldParts=previous.parts?.length?previous.parts:[previous],newParts=next.parts?.length?next.parts:[next];
   oldParts.forEach((part,i)=>{for(const field of ['startDate','endDate'])if(part.fields?.[field]&&part.fields[field]!==newParts[i]?.fields?.[field])dates.push({field,before:part.fields[field],after:newParts[i].fields[field]});});
  }else for(const field of ['startDate','endDate','date'])if(previous[field]&&previous[field]!==next[field])dates.push({field,before:previous[field],after:next[field]});
  if(dates.length){moved.add(kind+':'+id);details.push({kind,id,label:previous.name||previous.title||previous.label||kind+' '+id,dates});}
 }
 const held=[];
 if(delta)for(const option of values(s.options).filter(o=>o.scenarioId===sid&&!o.archived)){
  const parts=option.parts?.length?option.parts:[option];
  for(const part of parts)if(!part.archived&&(part.confirmed||booking(s,part))&&['startDate','endDate'].some(k=>part.fields?.[k])){
   held.push({id:option.id,label:option.label||option.name||'Reserved option',reason:'Confirmed or booked dates remain fixed'});
  }
 }
 const warnings=[];
 if(held.length)warnings.push('Booked or confirmed dates will not move; review them against the new itinerary.');
 if(details.some(d=>d.kind==='options'))warnings.push('Saved quotes are unchanged and may need to be rechecked.');
 return {oldStart,newStart,delta,changes,details,held,warnings};
}
return {values,clone,alive,uid,dayNumber,datePlus,byPosition,stops,groups,options,copyOptionDestinations,copyOptionChanges,journeySlots,itemNotes,scheduledActivity,scheduleActivityChange,activityQuoteChanges,title,booking,status,conditions,needsRecheck,quoteTotal,exchange,cost,budget,duration,zonedStamp,notices,diff,setPath,patch,operations,shiftScenario,previewScenarioShift};
});
