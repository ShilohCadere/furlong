const test=require('node:test'),assert=require('node:assert/strict'),P=require('../static/planner-presentation.js');
const fixture=()=>({meta:{currency:'USD',tripId:12},scenarios:{s:{id:'s',name:'Main route',budget:1000,startDate:'2027-09-01'},other:{id:'other',name:'Alternative'}},stops:{a:{id:'a',scenarioId:'s',name:'Edinburgh',startDate:'2027-09-01',nights:3,lat:55.95,lng:-3.18},b:{id:'b',scenarioId:'other',name:'London',startDate:'2028-02-01',nights:8,lat:51.5,lng:-.1}},groups:{g:{id:'g',scenarioId:'s',stopId:'a',selectedId:'o'},x:{id:'x',scenarioId:'other',stopId:'b',selectedId:'x'}},options:{o:{id:'o',scenarioId:'s',groupId:'g',ideaId:'i',type:'hotel',fields:{startDate:'2027-09-01',endDate:'2027-09-04'},quote:{amount:100,currency:'USD',basis:'total'}},x:{id:'x',scenarioId:'other',groupId:'x',ideaId:'i',fields:{startDate:'2028-02-01'}}},days:{d:{id:'d',scenarioId:'s',stopId:'a',date:'2027-09-02'}},activities:{},travelers:{t:{id:'t',name:'Traveler'},removed:{id:'removed',archived:true}},payments:{},bookings:{}});
const user=()=>({ideas:{i:{id:'i',name:'Hotel',originTripId:12,lat:55.96,lng:-3.19},local:{id:'local',name:'Museum',originTripId:12,lat:55.9,lng:-3.1},foreign:{id:'foreign',name:'Private other trip',originTripId:99,lat:51,lng:0}}});
test('trip header uses the selected alternative, checkout dates and real traveler count without modifying records',()=>{
 const s=fixture(),before=structuredClone(s);
 assert.deepEqual(P.tripContext(s,'s'),{start:'2027-09-01',end:'2027-09-04',travelers:1,stops:1,alternative:'Main route'});
 assert.equal(P.tripContext(s,'other').end,'2028-02-09');assert.deepEqual(s,before);
});
test('comparison facts preserve unknowns and do not infer zero-price, nonstop, rooms or travel times',()=>{
 const unknown=P.comparisonFacts({type:'flight',fields:{origin:'DUB',destination:'EDI'}});
 assert.equal(unknown.find(x=>x.label==='Duration').value,'Not recorded');assert.equal(unknown.find(x=>x.label==='Connections').value,'Not recorded');
 const hotel=P.comparisonFacts({type:'hotel',fields:{startDate:'2027-09-01',endDate:'2027-09-04'}});
 assert.equal(hotel[0].value,'3');assert.equal(hotel[1].value,'Not set');
 const overnight=P.comparisonFacts({type:'flight',fields:{startDate:'2027-09-01',endDate:'2027-09-02',departureTime:'23:00',arrivalTime:'02:00',originZone:'Europe/London',destinationZone:'Europe/London',layovers:0}});
 assert.equal(overnight.find(x=>x.label==='Duration').value,'3h 0m');assert.equal(overnight.find(x=>x.label==='Connections').value,'Nonstop');
 const parts=P.comparisonFacts({type:'flight',parts:[{fields:{duration:2}},{fields:{}}]});
 assert.equal(parts.find(x=>x.label==='Duration').value,'Not recorded');
});
test('payment badges distinguish selected, booked, part paid and paid, including refunds',()=>{
 const s=fixture(),o=s.options.o,g=s.groups.g;
 assert.deepEqual(P.optionStatuses(s,o,g,{}),['Selected']);
 o.bookingId='b';s.bookings.b={id:'b',quote:o.quote};
 s.payments.p={id:'p',bookingId:'b',amount:25,currency:'USD',baseAmount:25,baseCurrency:'USD'};
 assert.deepEqual(P.optionStatuses(s,o,g,{}),['Booked','Selected','Part paid']);
 s.payments.p.amount=100;s.payments.p.baseAmount=100;assert.ok(P.optionStatuses(s,o,g,{}).includes('Paid'));
 s.payments.refund={id:'refund',bookingId:'b',amount:10,currency:'USD',baseAmount:10,baseCurrency:'USD',refund:true};
 assert.ok(P.optionStatuses(s,o,g,{}).includes('Part paid'));assert.ok(!P.optionStatuses(s,o,g,{}).includes('Paid'));
});
test('saved idea pricing and map points stay scoped to the current alternative and trip',()=>{
 const s=fixture(),u=user(),before=JSON.stringify([s,u]);
 assert.deepEqual(P.ideaOptions(s,'s','i').map(o=>o.id),['o']);
 const points=P.mapPoints(s,u,'s',{unscheduled:true});
 assert.deepEqual(points.map(p=>p.key),['stop:a','option:o','idea:local']);
 assert.ok(!points.some(p=>p.name==='Private other trip'));assert.equal(JSON.stringify([s,u]),before);
 assert.deepEqual(P.mapPoints(s,u,'s',{day:'missing'}),[]);
 s.days.other={id:'other',scenarioId:'other',stopId:'b'};assert.deepEqual(P.mapPoints(s,u,'s',{day:'other'}),[]);
});
test('scheduled activities have one pin and day filters exclude other dates and archived records',()=>{
 const s=fixture(),u=user();s.activities.act={id:'act',scenarioId:'s',dayId:'d',optionId:'o',ideaId:'i',name:'Hotel check-in',time:'15:00'};
 assert.deepEqual(P.mapPoints(s,u,'s',{day:'d'}).map(p=>p.key),['stop:a','activity:act']);
 s.activities.act.archived=true;assert.deepEqual(P.mapPoints(s,u,'s',{day:'d'}).map(p=>p.key),['stop:a','option:o']);
 s.stops.a.archived=true;assert.deepEqual(P.mapPoints(s,u,'s',{day:'d'}),[]);
});
test('coordinates accept the equator and prime meridian while rejecting missing or invalid locations',()=>{
 assert.deepEqual(P.coordinates({lat:0,lng:0}),[0,0]);
 for(const record of [{lat:'',lng:0},{lat:null,lng:0},{lat:91,lng:10},{lat:0,lng:181},{lat:'invalid',lng:0}])assert.equal(P.coordinates(record),null);
});
test('city itinerary places activities under their assigned days and keeps accommodation separate without duplicating options',()=>{
 const s=fixture();s.options.o.type='activity';s.options.o.fields.startDate='2027-09-02';
 s.activities.act={id:'act',scenarioId:'s',dayId:'d',optionId:'o',ideaId:'i',name:'Museum'};
 s.groups.hotel={id:'hotel',scenarioId:'s',stopId:'a',type:'hotel'};
 s.options.hotel={id:'hotel',groupId:'hotel',scenarioId:'s',type:'hotel',fields:{startDate:'2027-09-02'}};
 s.options.dated={id:'dated',groupId:'g',scenarioId:'s',type:'restaurant',fields:{startDate:'2027-09-02'}};
 s.options.open={id:'open',groupId:'g',scenarioId:'s',type:'activity',fields:{}};
 const before=structuredClone(s),layout=P.stopItinerary(s,'s','a');
 assert.equal(layout.days[0].activities[0].option.id,'o');assert.deepEqual(layout.days[0].groups[0].options.map(o=>o.id),['dated']);
 assert.deepEqual(layout.stays[0].options.map(o=>o.id),['hotel']);assert.deepEqual(layout.unscheduled[0].options.map(o=>o.id),['open']);
 assert.deepEqual(s,before);
});
test('explicit unscheduling and another city or scenario take precedence over stale activity dates',()=>{
 const s=fixture();s.options.o.type='activity';s.options.o.fields.startDate='2027-09-02';
 s.activities.act={id:'act',scenarioId:'s',dayId:null,optionId:'o',ideaId:'i'};
 let layout=P.stopItinerary(s,'s','a');assert.equal(layout.days[0].groups.length,0);assert.equal(layout.unscheduled[0].options[0].id,'o');
 s.activities.act.dayId='elsewhere';s.days.elsewhere={id:'elsewhere',scenarioId:'s',stopId:'new',date:'2027-09-02'};
 layout=P.stopItinerary(s,'s','a');assert.equal(layout.unscheduled[0].options[0].id,'o');
 assert.deepEqual(P.stopItinerary(s,'s','b'),{days:[],stays:[],unscheduled:[]});
});
