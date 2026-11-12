/* Read-only view models. Do not change trip records when formatting a view. */
(function(root,factory){const C=typeof module==='object'&&module.exports?require('./planner-core.js'):root.FurlongCore;const api=factory(C);if(typeof module==='object'&&module.exports)module.exports=api;else root.FurlongPresentation=api;})(typeof globalThis!=='undefined'?globalThis:this,function(C){
'use strict';
const values=o=>Object.values(o||{}),live=x=>x&&!x.archived;
const validDate=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d+'T12:00:00Z'))&&new Date(d+'T12:00:00Z').toISOString().slice(0,10)===d;
function tripContext(s,sid){
 const stops=C.stops(s,sid),dates=[];
 const add=d=>{if(validDate(d))dates.push(d);};add(s.scenarios[sid]?.startDate);
 for(const st of stops){add(st.startDate);if(validDate(st.startDate)&&st.nights!=null&&Number(st.nights)>=0)add(C.datePlus(st.startDate,Number(st.nights)));}
 for(const day of values(s.days).filter(d=>live(d)&&d.scenarioId===sid))add(day.date);
 for(const g of C.groups(s,sid)){const o=s.options[g.selectedId];if(live(o)&&o.scenarioId===sid){add(o.fields?.startDate);add(o.fields?.endDate);}}
 dates.sort();return {start:dates[0]||null,end:dates[dates.length-1]||null,travelers:values(s.travelers).filter(live).length,stops:stops.length,alternative:s.scenarios[sid]?.name||''};
}
function comparisonFacts(o){
 const parts=o.parts||[],first=parts[0]?.fields||o.fields||{},last=parts[parts.length-1]?.fields||first,f=o.fields||{};
 const duration=parts.length?parts.map(p=>C.duration(p)): [C.duration(o)];
 const hours=duration.every(n=>n!==null&&Number.isFinite(n))?duration.reduce((a,b)=>a+b,0):null;
 const durationLabel=hours===null?'Not recorded':`${Math.floor(Math.round(hours*60)/60)}h ${Math.round(hours*60)%60}m${parts.length?' in transit':''}`;
 if(['flight','transport'].includes(o.type))return [
  {label:'Departure',value:[first.departureTime,first.origin].filter(Boolean).join(' · ')||'Not recorded'},
  {label:'Arrival',value:[last.arrivalTime,last.destination].filter(Boolean).join(' · ')||'Not recorded'},
  {label:'Duration',value:durationLabel},
  {label:o.type==='flight'?'Connections':'Mode',value:String((o.type==='flight'?(f.layovers===0?'Nonstop':f.layovers):f.mode)||(parts.length?`${parts.length} legs`:'Not recorded'))}
 ];
 if(['hotel','castle','accommodation'].includes(o.type)){
  const nights=validDate(f.startDate)&&validDate(f.endDate)?C.dayNumber(f.endDate)-C.dayNumber(f.startDate):null;
  return [{label:'Nights',value:nights!==null&&nights>=0?String(nights):'Not set'},
   {label:'Rooms',value:f.rooms==null||f.rooms===''?'Not set':String(f.rooms)},
   {label:'Guests',value:f.guests==null||f.guests===''?'Not set':String(f.guests)},
   {label:'Cancellation',value:f.cancellation||'Not recorded'}];
 }
 return [{label:'Time',value:f.startTime||f.timeBlock||'Anytime'},
  {label:'Duration',value:durationLabel},
  {label:'Travelers',value:f.travelers??f.guests??'Not set'},
  {label:'Reservation',value:f.reservation||'Not recorded'}];
}
function optionStatuses(s,o,g,fx){
 const state=C.status(s,o,g),cost=C.cost(s,o,fx);
 const badges=[state==='Idea'||state==='Shortlisted'?'Saved':state];
 if(g?.selectedId===o.id&&!badges.includes('Selected'))badges.push('Selected');
 if(cost.paid>0)badges.push(!cost.unknown&&cost.paid>=cost.amount-.005?'Paid':'Part paid');
 return badges;
}
function ideaOptions(s,sid,ideaId){return values(s.options).filter(o=>live(o)&&o.scenarioId===sid&&o.ideaId===ideaId&&live(s.groups[o.groupId])&&s.groups[o.groupId].scenarioId===sid);}
function coordinates(record){
 if(record?.lat==null||record?.lng==null||record.lat===''||record.lng==='')return null;
 const lat=Number(record.lat),lng=Number(record.lng);
 return Number.isFinite(lat)&&Number.isFinite(lng)&&Math.abs(lat)<=90&&Math.abs(lng)<=180?[lat,lng]:null;
}
function mapPoints(s,u,sid,{day='',backups=false,unscheduled=false}={}){
 const stops=C.stops(s,sid),stopIds=new Set(stops.map(st=>st.id)),focus=day&&s.days[day];
 if(day&&(!live(focus)||focus.scenarioId!==sid||!stopIds.has(focus.stopId)))return [];
 const points=[],linked=new Set(),scheduled=new Set();
 const push=(kind,record,name,location,stopId,extra={})=>points.push({key:kind+':'+record.id,kind,id:record.id,name,coordinates:coordinates(location),stopId,...extra});
 for(const st of stops)if(!focus||focus.stopId===st.id)push('stop',st,st.name,st,st.id);
 const activities=values(s.activities).filter(a=>live(a)&&a.scenarioId===sid&&live(s.days[a.dayId])&&s.days[a.dayId].scenarioId===sid&&stopIds.has(s.days[a.dayId].stopId));
 for(const a of activities){linked.add(a.ideaId);if(a.optionId)scheduled.add(a.optionId);}
 for(const g of C.groups(s,sid))for(const o of C.options(s,g.id)){
  if(o.scenarioId!==sid)continue;linked.add(o.ideaId);
  if(scheduled.has(o.id)||(!backups&&g.selectedId!==o.id)||(g.stopId&&!stopIds.has(g.stopId))||(focus&&g.stopId!==focus.stopId))continue;
  const idea=u.ideas[o.ideaId];push('option',o,C.title(o,u),idea,g.stopId,{status:C.status(s,o,g)});
 }
 for(const a of activities)if(!focus||a.dayId===focus.id)push('activity',a,a.name||u.ideas[a.ideaId]?.name||'Activity',u.ideas[a.ideaId],s.days[a.dayId].stopId,{time:a.time||a.timeBlock||'Anytime'});
 if(unscheduled&&!day)for(const idea of values(u.ideas).filter(i=>live(i)&&i.originTripId===s.meta.tripId&&!linked.has(i.id)))push('idea',idea,idea.name,idea,null,{status:'Unscheduled'});
 return points;
}
function itineraryDayDate(s,day){return day.date||(validDate(s.stops[day.stopId]?.startDate)?C.datePlus(s.stops[day.stopId].startDate,Number(day.position||0)):null);}
function stopItinerary(s,sid,stopId){
 const stop=s.stops[stopId];if(!live(stop)||stop.scenarioId!==sid)return {days:[],stays:[],unscheduled:[]};
 const days=values(s.days).filter(d=>live(d)&&d.scenarioId===sid&&d.stopId===stopId)
  .sort((a,b)=>(itineraryDayDate(s,a)||'9999').localeCompare(itineraryDayDate(s,b)||'9999')||C.byPosition(a,b))
  .map(day=>({day,activities:values(s.activities).filter(a=>live(a)&&a.scenarioId===sid&&a.dayId===day.id).map(activity=>({activity,option:null})),groups:[]}));
 const byId=new Map(days.map(entry=>[entry.day.id,entry])),byDate=new Map();
 for(const entry of days){const date=itineraryDayDate(s,entry.day);if(date&&!byDate.has(date))byDate.set(date,entry);}
 const stays=[],unscheduled=[];
 const add=(target,group,option)=>{let entry=target.find(entry=>entry.group.id===group.id);if(!entry){entry={group,options:[]};target.push(entry);}entry.options.push(option);};
 for(const group of C.groups(s,sid,stopId)){
  const options=C.options(s,group.id).filter(o=>o.scenarioId===sid);
  if(!options.length){(['hotel','castle','flight','transport'].includes(group.type)?stays:unscheduled).push({group,options:[]});continue;}
  for(const option of options){
   if(['hotel','castle','accommodation','flight','transport'].includes(option.type)){add(stays,group,option);continue;}
   const activity=C.scheduledActivity(s,option);
   // An explicit assignment (including unscheduling) takes precedence over an old quote date.
   const target=activity?byId.get(activity.dayId):byDate.get(option.fields?.startDate);
   if(!target){add(unscheduled,group,option);continue;}
   const row=activity&&target.activities.find(row=>row.activity.id===activity.id);
   if(row&&(!row.activity.optionId||row.activity.optionId===option.id)&&!row.option)row.option=option;
   else add(target.groups,group,option);
  }
 }
 return {days,stays,unscheduled};
}
return {stopItinerary,itineraryDayDate,validDate,tripContext,comparisonFacts,optionStatuses,ideaOptions,coordinates,mapPoints};
});
