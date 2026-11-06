const test=require('node:test'),assert=require('node:assert/strict'),C=require('../static/planner-core.js');
const fixture=()=>({meta:{currency:'USD'},scenarios:{s:{id:'s',budget:1000,foodAllowance:20,startDate:'2027-09-01'}},stops:{st:{id:'st',scenarioId:'s',startDate:'2027-09-01',nights:2}},groups:{g:{id:'g',scenarioId:'s',selectedId:'o',stopId:'st'}},options:{o:{id:'o',groupId:'g',scenarioId:'s',fields:{startDate:'2027-09-01'},quote:{amount:100,currency:'GBP',basis:'total',startDate:'2027-09-01'},quoteHistory:[]}},payments:{},bookings:{},expenses:{},days:{},activities:{},dismissals:{}});
test('transatlantic journeys bracket stops using selected dates; routes occur once',()=>{
 const s=fixture();s.stops.last={id:'last',scenarioId:'s',position:1,startDate:'2027-09-10',nights:3};
 for(const [id,date] of [['out','2027-08-31'],['internal','2027-09-04'],['home','2027-09-13']]){
  s.groups[id]={id,scenarioId:'s',type:'flight',stopId:null,selectedId:id};
  s.options[id]={id,scenarioId:'s',groupId:id,fields:{startDate:date}};
 }
 s.options.backup={id:'backup',groupId:'home',fields:{startDate:'2027-08-01'}};
 s.groups.unknown={id:'unknown',scenarioId:'s',type:'flight',stopId:null};
 s.groups.other={id:'other',scenarioId:'other',type:'flight',stopId:null,startDate:'2027-08-01'};
 const original=C.clone(s),slots=C.journeySlots(s,'s');
 assert.deepEqual(slots.before.map(g=>g.id),['out']);assert.deepEqual(slots.after.st.map(g=>g.id),['internal']);
 assert.deepEqual(slots.after.last.map(g=>g.id),['home']);assert.deepEqual(slots.shared.map(g=>g.id),['unknown']);assert.deepEqual(s,original);
 s.groups.home.itineraryPlacement='before';assert.ok(C.journeySlots(s,'s').before.some(g=>g.id==='home'));
 s.groups.home.itineraryPlacement='after';s.groups.home.anchorStopId='st';assert.ok(C.journeySlots(s,'s').after.st.some(g=>g.id==='home'));
 s.stops.last.archived=true;assert.ok(!Object.hasOwn(C.journeySlots(s,'s').after,'last'));
});
test('shared and occurrence notes are retained without duplicating identical text',()=>{
 const user={ideas:{i:{notes:'Source notes\n£35 per ticket'}}};
 assert.deepEqual(C.itemNotes({ideaId:'i',fields:{notes:'Bring confirmation'}},user),['Source notes\n£35 per ticket','Bring confirmation']);
 assert.deepEqual(C.itemNotes({ideaId:'i',notes:'Source notes\n£35 per ticket'},user),['Source notes\n£35 per ticket']);
 assert.deepEqual(C.itemNotes({notes:'Day notes'},user),['Day notes']);
});
test('scheduled activity quotes reach budget once and survive updates and unscheduling',()=>{
 const s=fixture();s.groups={};s.options={};s.days.d={id:'d',scenarioId:'s',stopId:'st',date:'2027-09-11'};
 const a={id:'show',scenarioId:'s',dayId:'d',name:'Urzila Carlson',ideaId:'idea',notes:'Keep these notes',time:'19:00'};
 let seq=0;const q={amount:35,currency:'GBP',basis:'person',quantity:4,units:1};
 const apply=changes=>{for(const [kind,id,value] of changes)s[kind][id]=C.clone(value);};
 const before=C.clone(s);apply(C.activityQuoteChanges(s,a,q,true,()=>`new${++seq}`));
 assert.deepEqual(before.expenses,s.expenses);assert.equal(C.budget(s,'s',{GBP:1.3}).amount,202);
 const oid=s.activities.show.optionId;assert.equal(s.options[oid].fields.startDate,'2027-09-11');assert.equal(s.activities.show.notes,a.notes);
 apply(C.activityQuoteChanges(s,s.activities.show,{...q,amount:40},true));
 assert.equal(Object.keys(s.groups).length,1);assert.equal(Object.keys(s.options).length,1);assert.equal(s.options[oid].quoteHistory.length,1);
 assert.equal(C.budget(C.clone(s),'s',{GBP:1.3}).amount,228);
 s.activities.show.dayId=null;assert.equal(C.budget(s,'s',{GBP:1.3}).amount,228);
 assert.equal(C.budget(s,'other',{GBP:1.3}).amount,0);
 s.groups[s.options[oid].groupId].selectedId=null;
 apply(C.activityQuoteChanges(s,s.activities.show,{...q,amount:50},true));
 assert.equal(C.budget(s,'s',{GBP:1.3}).amount,20); // Editing a quote never silently selects an alternative.
});
test('activity quote validation and unselected references preserve financial meaning',()=>{
 const s=fixture(),a={id:'show',scenarioId:'s',name:'Show',ideaId:'idea',notes:'£50 is only a note'};
 const q={amount:50,currency:'GBP',basis:'total',quantity:1,units:1};let seq=0;
 const changes=C.activityQuoteChanges(s,a,q,false,()=>`x${++seq}`);
 assert.equal(changes.find(x=>x[0]==='groups')[2].selectedId,null);
 const before=C.clone(s);assert.throws(()=>C.activityQuoteChanges(s,a,{...q,amount:-1},true));assert.deepEqual(s,before);
 assert.throws(()=>C.activityQuoteChanges(s,a,{...q,currency:'Pounds'},true));
 assert.throws(()=>C.activityQuoteChanges(s,a,{...q,quantity:0},true));
 s.options.o.scenarioId='other';assert.throws(()=>C.activityQuoteChanges(s,{...a,optionId:'o'},q,true));
 s.options.o.scenarioId='s';s.options.o.bookingId='b';s.bookings.b={id:'b',quote:q};
 assert.throws(()=>C.activityQuoteChanges(s,{...a,optionId:'o'},q,true));
});
test('unit quotes, provisional quotes and unknown prices',()=>{const s=fixture();assert.equal(C.quoteTotal({amount:25,basis:'room-night',quantity:2,units:3}),150);s.options.o.fields.startDate='2027-09-03';const b=C.budget(s,'s',{GBP:1.25});assert.equal(b.amount,145);assert.equal(b.provisional,1);s.options.o.quote.amount=null;assert.equal(C.budget(s,'s',{}).unknown,1);assert.equal(C.budget(s,'s',{}).amount,20);});
test('daily rates move only the unpaid portion; refunds preserve net actuals',()=>{const s=fixture();s.bookings.b={id:'b',quote:s.options.o.quote};s.options.o.bookingId='b';s.payments.p={id:'p',bookingId:'b',amount:40,currency:'GBP',baseAmount:48,baseCurrency:'USD'};assert.equal(C.cost(s,s.options.o,{GBP:1.3}).amount,126);s.payments.r={id:'r',bookingId:'b',amount:10,currency:'GBP',baseAmount:11,baseCurrency:'USD',refund:true};assert.equal(C.cost(s,s.options.o,{GBP:1.3}).amount,128);assert.equal(C.cost(s,s.options.o,{GBP:1.3}).paid,37);});
test('multipart actual bookings count once across groups',()=>{const s=fixture();s.bookings.b={id:'b',quote:s.options.o.quote};s.options.o.parts=[{id:'p1',bookingId:'b',fields:{}},{id:'p2',bookingId:'b',fields:{}}];s.groups.g2={id:'g2',scenarioId:'s',selectedId:'o2'};s.options.o2={...s.options.o,id:'o2',groupId:'g2'};assert.equal(C.budget(s,'s',{GBP:1.25}).amount,145);assert.equal(C.status(s,s.options.o),'Booked / confirmed');s.options.o.parts.push({id:'p3',fields:{},quote:{amount:null}});assert.equal(C.status(s,s.options.o),'Partially booked');});
test('expense actuals and allowance coverage remain separate',()=>{const s=fixture();s.groups={};s.expenses.e={id:'e',scenarioId:'s',amount:100,currency:'GBP'};s.payments.p={expenseId:'e',amount:100,currency:'GBP',baseAmount:119,baseCurrency:'USD'};assert.equal(C.budget(s,'s',{GBP:1.3}).amount,139);s.expenses.e.coveredByAllowance=true;assert.equal(C.budget(s,'s',{GBP:1.3}).amount,20);assert.equal(C.budget(s,'s',{GBP:1.3}).paid,119);});
test('date shift moves flexible plans but leaves reservation and quotes intact',()=>{const s=fixture(),original=C.clone(s.options.o.quote);s.days.d={id:'d',scenarioId:'s',date:'2027-09-01'};let changes=C.shiftScenario(s,'s','2027-09-04');assert.equal(changes.find(x=>x[0]==='days')[2].date,'2027-09-04');assert.equal(changes.find(x=>x[0]==='options')[2].fields.startDate,'2027-09-04');assert.deepEqual(changes.find(x=>x[0]==='options')[2].quote,original);s.bookings.b={id:'b',fields:{startDate:'2027-09-01'}};s.options.o.bookingId='b';changes=C.shiftScenario(s,'s','2027-09-04');assert.equal(changes.find(x=>x[0]==='options')[2].fields.startDate,'2027-09-01');});
test('local times across zones produce correct elapsed duration',()=>{assert.equal(C.duration({fields:{startDate:'2027-09-01',endDate:'2027-09-02',departureTime:'20:00',arrivalTime:'09:00',originZone:'America/Chicago',destinationZone:'Europe/London'}}),7);});
test('nested independent edits generate leaf operations and replay safely',()=>{const before={id:'o',fields:{rooms:1,notes:'old'}},after={...before,fields:{rooms:2,notes:'old'}},op=C.operations('trip','options','o',before,after);assert.deepEqual(op.patch,{'fields.rooms':2});const s={options:{o:C.clone(before)}};s.options.o.fields.notes='other device';C.patch(s,op);assert.equal(s.options.o.fields.notes,'other device');assert.equal(s.options.o.fields.rooms,2);assert.throws(()=>C.setPath(s,'__proto__.bad','x'));});
test('route review notice survives an unselected connection',()=>{const s=fixture();s.groups.g.needsRouteReview=true;const notices=C.notices(s,{ideas:{}},'s',{GBP:1.25});assert.ok(notices.some(n=>n.kind==='route'));s.dismissals.d={signature:notices.find(n=>n.kind==='route').id};assert.equal(C.notices(s,{ideas:{}},'s',{GBP:1.25}).filter(n=>n.kind==='route').length,0);});

test('date shifts preserve archived descendants and unrelated scenarios',()=>{const s=fixture();s.scenarios.other={id:'other',startDate:'2027-09-01'};s.stops.arch={id:'arch',scenarioId:'s',startDate:'2027-08-31',archived:true};s.days.archday={id:'archday',scenarioId:'s',stopId:'arch',date:'2027-08-31'};s.groups.archgroup={id:'archgroup',scenarioId:'s',stopId:'arch',archived:true};s.options.archopt={id:'archopt',scenarioId:'s',groupId:'archgroup',fields:{startDate:'2027-08-31'}};s.stops.other={id:'other',scenarioId:'other',startDate:'2027-09-01'};const before=C.clone(s),changes=C.shiftScenario(s,'s','2027-09-08');assert.ok(!changes.some(([kind,id])=>['arch','archday','archgroup','archopt','other'].includes(id)));assert.equal(changes.find(([kind,id])=>kind==='stops'&&id==='st')[2].startDate,'2027-09-08');assert.deepEqual(s,before);});
test('confirmed and archived multipart reservations never shift',()=>{const s=fixture();s.options.o.parts=[{id:'flex',fields:{startDate:'2027-09-01'}},{id:'confirmed',confirmed:true,fields:{startDate:'2027-09-01'}},{id:'archived',archived:true,fields:{startDate:'2027-09-01'}}];const changes=C.shiftScenario(s,'s','2027-09-04');const parts=changes.find(([kind,id])=>kind==='options'&&id==='o')[2].parts;assert.equal(parts[0].fields.startDate,'2027-09-04');assert.equal(parts[1].fields.startDate,'2027-09-01');assert.equal(parts[2].fields.startDate,'2027-09-01');});

test('shift preview describes exact changes and held bookings without mutating state',()=>{const s=fixture(),before=C.clone(s);s.days.d={id:'d',scenarioId:'s',date:'2027-09-01',title:'Arrival'};s.options.held={id:'held',scenarioId:'s',groupId:'g',bookingId:'b',fields:{startDate:'2027-09-01'}};s.bookings.b={id:'b',fields:{startDate:'2027-09-01'}};const snapshot=C.clone(s),preview=C.previewScenarioShift(s,'s','2027-09-04');assert.equal(preview.delta,3);assert.ok(preview.details.some(x=>x.kind==='days'&&x.dates[0].after==='2027-09-04'));assert.ok(preview.held.some(x=>x.id==='held'));assert.ok(preview.warnings.length);assert.deepEqual(s,snapshot);assert.deepEqual(preview.changes,C.shiftScenario(s,'s','2027-09-04'));});
