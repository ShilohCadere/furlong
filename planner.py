"""Furlong's editable planning graph, additive legacy import and conflict-safe sync.

The existing tables remain intact. A versioned document preserves complete trip
alternatives; user ideas/templates have their own document and explicit ownership.
"""
import copy
import hashlib
import http.client
import ipaddress
import json
import math
import mimetypes
import os
import re
import socket
import sqlite3
import ssl
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urlencode

from contextlib import contextmanager

from flask import redirect, abort, jsonify, request, session, render_template, send_file, url_for
from bs4 import BeautifulSoup

COLLECTIONS = ('scenarios','stops','groups','options','days','activities','tasks','bookings',
               'payments','expenses','travelers','households','reimbursements','dismissals')
USER_COLLECTIONS = ('ideas','templates','preferences')
PLACES = {'dublin':(53.3498,-6.2603),'galway':(53.2707,-9.0568),'edinburgh':(55.9533,-3.1883),
          'london':(51.5074,-.1278),'inverness':(57.4778,-4.2247),'glasgow':(55.8642,-4.2518),
          'glencoe':(56.6826,-5.1023),'st louis':(38.627,-90.1994)}
DEFAULT_FIELDS = {
 'hotel':[('startDate','Check-in','date'),('endDate','Check-out','date'),('rooms','Rooms','number'),('guests','Guests','number'),('roomType','Room type','text'),('cancellation','Cancellation terms','text')],
 'castle':[('startDate','Check-in','date'),('endDate','Check-out','date'),('rooms','Rooms','number'),('guests','Guests','number'),('roomType','Room type','text'),('cancellation','Cancellation terms','text')],
 'flight':[('startDate','Departure date','date'),('endDate','Arrival date','date'),('origin','From airport','text'),('destination','To airport','text'),('departureTime','Departure local time','time'),('arrivalTime','Arrival local time','time'),('originZone','Departure time zone','text'),('destinationZone','Arrival time zone','text'),('carrier','Airline','text'),('flightNumber','Flight number','text'),('layovers','Connections','text'),('baggage','Baggage','text'),('travelers','Travelers','number'),('duration','Duration (hours)','number')],
 'activity':[('startDate','Date','date'),('startTime','Local time','time'),('timeBlock','Time block','text'),('duration','Duration (hours)','number'),('travelers','Travelers','number'),('reservation','Reservation requirements','text')],
 'transport':[('startDate','Start date','date'),('endDate','End date','date'),('origin','From','text'),('destination','To','text'),('departureTime','Departure local time','time'),('arrivalTime','Arrival local time','time'),('originZone','Departure time zone','text'),('destinationZone','Arrival time zone','text'),('operator','Operator','text'),('mode','Mode','text'),('vehicles','Vehicles','number'),('duration','Duration (hours)','number')],
 'restaurant':[('startDate','Date','date'),('startTime','Local time','time'),('guests','Guests','number'),('cuisine','Cuisine','text'),('reservation','Reservation requirements','text')],
 'idea':[]}


def now(): return datetime.now(timezone.utc).isoformat()
def ident(*parts): return uuid.uuid5(uuid.NAMESPACE_URL,'furlong/'+ '/'.join(map(str,parts))).hex

def user_defaults():
    return {'ideas':{}, 'templates':{key:{'id':key,'name':key.capitalize(),
       'fields':[{'key':k,'label':label,'kind':kind} for k,label,kind in fields],
       'summaryFields':[k for k,_,_ in fields[:3]]} for key,fields in DEFAULT_FIELDS.items()},
       'preferences':{'display':{'id':'display','density':'compact','showNotes':True,'tasksEnabled':True,
       'trackReimbursements':False,'mapBackups':False,'mapUnscheduled':False,
       'timeBlocks':[{'name':'Morning','start':'06:00'},{'name':'Afternoon','start':'12:00'},
                     {'name':'Evening','start':'18:00'},{'name':'Anytime','start':''}],
       'taskStatuses':['To do','In progress','Done'],'taskFields':[]}}}


def empty_trip(trip):
    result={key:{} for key in COLLECTIONS}
    result['meta']={'id':'trip','tripId':trip['id'],'name':trip['name'],'currency':'USD',
                    'activeScenario':None,'rateLock':None,'version':2}
    return result


def parse_trip_setup(form):
    """Validate the optional route builder before creating any trip records."""
    stops = []
    route_text = form.get('route-stops', '')
    if len(route_text) > 7000:
        abort(400, 'Use up to 50 stops and 365 nights per trip.')
    for line in route_text.splitlines():
        if not line.strip():
            continue
        parts = line.rsplit('|', 1)
        try:
            name, nights = parts[0].strip(), int(parts[1].strip())
        except (IndexError, ValueError):
            abort(400, 'Enter each stop as Place | number of nights.')
        if not name or len(name) > 100 or not 1 <= nights <= 365:
            abort(400, 'Each stop needs a name and 1 to 365 nights.')
        stops.append({'name': name, 'nights': nights})
    if len(stops) > 50 or sum(stop['nights'] for stop in stops) > 365:
        abort(400, 'Use up to 50 stops and 365 nights per trip.')
    start = form.get('route-start', '').strip()
    if start:
        try:
            date.fromisoformat(start) + timedelta(days=sum(stop['nights'] for stop in stops))
        except (ValueError, OverflowError):
            abort(400, 'Use a valid arrival date.')
    amounts = {}
    for key, default in (('setup-budget', 20000), ('setup-food', 0)):
        try:
            value = float(form.get(key, '').strip() or default)
        except ValueError:
            abort(400, 'Use a valid budget amount.')
        if not math.isfinite(value) or not 0 <= value <= 1e9:
            abort(400, 'Use a nonnegative budget amount.')
        amounts[key] = value
    try:
        places = json.loads(form.get('setup-places', '{}'))
    except (ValueError, TypeError):
        abort(400, 'Use valid map locations.')
    if not isinstance(places, dict):
        abort(400, 'Use valid map locations.')
    for stop in stops:
        place = places.get(stop['name'])
        if place is None:
            continue
        try:
            lat, lng = float(place['lat']), float(place['lng'])
        except (KeyError, TypeError, ValueError):
            abort(400, 'Use valid map coordinates.')
        if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            abort(400, 'Use valid map coordinates.')
        stop.update(lat=lat, lng=lng, timeZone=str(place.get('timeZone', ''))[:100],
                    location=str(place.get('label', stop['name']))[:200])
    return {'stops': stops, 'start': start or None,
            'budget': amounts['setup-budget'], 'food': amounts['setup-food']}


def create_route_plan(conn, trip, route_name, setup):
    state = empty_trip(trip)
    sid = uuid.uuid4().hex
    state['meta']['activeScenario'] = sid
    state['scenarios'][sid] = {'id': sid, 'name': route_name,
        'startDate': setup['start'], 'budget': setup['budget'],
        'foodAllowance': setup['food'], 'archived': False}
    start = date.fromisoformat(setup['start']) if setup['start'] else None
    for position, stop in enumerate(setup['stops']):
        stop_id, group_id = uuid.uuid4().hex, uuid.uuid4().hex
        state['stops'][stop_id] = {'id': stop_id, 'scenarioId': sid,
            'name': stop['name'], 'location': stop.get('location', stop['name']), 'position': position,
            'startDate': start.isoformat() if start else None,
            'nights': stop['nights'], 'lat': stop.get('lat'), 'lng': stop.get('lng'),
            'timeZone': stop.get('timeZone', ''),
            'notes': '', 'archived': False}
        state['groups'][group_id] = {'id': group_id, 'scenarioId': sid,
            'stopId': stop_id, 'name': 'Accommodation', 'type': 'hotel',
            'selectedId': None, 'allowance': None, 'position': 0,
            'notes': '', 'archived': False}
        for day in range(stop['nights']):
            day_id = uuid.uuid4().hex
            state['days'][day_id] = {'id': day_id, 'scenarioId': sid,
                'stopId': stop_id, 'position': day,
                'date': (start + timedelta(days=day)).isoformat() if start else None,
                'title': 'Arrival in ' + stop['name'] if day == 0 else '',
                'notes': '', 'archived': False}
        if start:
            start += timedelta(days=stop['nights'])
    conn.execute('CREATE TABLE IF NOT EXISTS planner_trip_documents '
        '(trip_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1, body TEXT NOT NULL, updated_at TEXT NOT NULL)')
    conn.execute('INSERT INTO planner_trip_documents VALUES (?,1,?,?)',
        (trip['id'], json.dumps(state), now()))


def install(app, db_connect, get_trip, data_dir):
    """Register the new workspace; no existing application data is overwritten."""
    data_dir=Path(data_dir)
    @contextmanager
    def db():
        conn=db_connect()
        try:
            # Tests and restored installations may point at a fresh database.
            for table in ('planner_trip_documents','planner_user_documents'):
                owner='trip_id' if table=='planner_trip_documents' else 'user_id'
                conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ({owner} INTEGER PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1, body TEXT NOT NULL, updated_at TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS planner_operations(user_id INTEGER NOT NULL, op_id TEXT NOT NULL, trip_id INTEGER NOT NULL, PRIMARY KEY(user_id,op_id))')
            conn.execute('CREATE TABLE IF NOT EXISTS planner_rates(base TEXT PRIMARY KEY, body TEXT NOT NULL, checked_on TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS planner_files(id TEXT PRIMARY KEY,trip_id INTEGER NOT NULL,user_id INTEGER NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL)')
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
        finally:conn.close()
    with db() as conn:
        for table in ('planner_trip_documents','planner_user_documents'):
            owner='trip_id' if table=='planner_trip_documents' else 'user_id'
            conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ({owner} INTEGER PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1, body TEXT NOT NULL, updated_at TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS planner_operations(user_id INTEGER NOT NULL, op_id TEXT NOT NULL, trip_id INTEGER NOT NULL, PRIMARY KEY(user_id,op_id))')
        conn.execute('CREATE TABLE IF NOT EXISTS planner_rates(base TEXT PRIMARY KEY, body TEXT NOT NULL, checked_on TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS planner_files(id TEXT PRIMARY KEY,trip_id INTEGER NOT NULL,user_id INTEGER NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL)')

    def load_user(conn,uid):
        row=conn.execute('SELECT * FROM planner_user_documents WHERE user_id=?',(uid,)).fetchone()
        if row:return json.loads(row['body']),row['revision']
        body=user_defaults()
        conn.execute('INSERT INTO planner_user_documents VALUES (?,1,?,?)',(uid,json.dumps(body),now()))
        return body,1

    def import_trip(conn,trip,user):
        state=empty_trip(trip);tid=trip['id']
        plans=conn.execute('SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id',(tid,)).fetchall()
        if not plans:
            # Graph-only default. Legacy tables are never seeded on page loads.
            plans=[{'id':'new','name':'Plan A','food_budget':0,'budget_limit':20000}]
        # A deleted seed candidate must not be resurrected by the first import.
        # The tombstone key includes scenario_tag; untagged exclusions are distinct.
        exclusions={
            (row['city'],row['name'],row['category'],row['scenario_tag'])
            for row in conn.execute(
                'SELECT city,name,category,scenario_tag FROM excluded_seed_options WHERE trip_id=?',(tid,)
            )
        }
        originals=[
            row for row in conn.execute('SELECT * FROM saved_options WHERE trip_id=? ORDER BY id',(tid,))
            if (row['city'],row['name'],row['category'],row['scenario_tag'] or '') not in exclusions
        ]
        # The library also keeps research tagged to an archived or renamed route.
        for option in originals:
            idea_id=ident('idea',tid,option['id'])
            location=PLACES.get(option['city'].casefold())
            user['ideas'].setdefault(idea_id,{'id':idea_id,'name':option['name'],'type':option['category'],'location':option['city'],
                'website':option['link'] or '', 'notes':option['notes'] or '', 'favorite':bool(option['is_preferred']),
                'lat':location[0] if location else None,'lng':location[1] if location else None,'createdAt':now(),'archived':False})
        # Generic itinerary_days is an older, trip-wide fallback. Never mix it
        # into a trip that already has scenario-specific itinerary dates.
        has_scenario_days=conn.execute(
            'SELECT 1 FROM scenario_itinerary WHERE trip_id=? LIMIT 1',(tid,)
        ).fetchone() is not None
        for plan in plans:
            sid=ident('scenario',tid,plan['id'])
            source_days=conn.execute('SELECT * FROM scenario_itinerary WHERE trip_id=? AND scenario_id=? ORDER BY day_date,id',(tid,plan['id'])).fetchall() if plan['id']!='new' else []
            if not source_days and plan==plans[0] and not has_scenario_days:
                source_days=[dict(row,day_date=row['trip_date'],city='',notes='') for row in conn.execute('SELECT * FROM itinerary_days WHERE trip_id=? ORDER BY day_number',(tid,))]
            start=next((d['day_date'] for d in source_days if d['day_date']),None)
            state['scenarios'][sid]={'id':sid,'name':plan['name'],'legacyId':plan['id'],'startDate':start,
                'budget':plan['budget_limit'],'foodAllowance':plan['food_budget'],'archived':False}
            state['meta']['activeScenario']=state['meta']['activeScenario'] or sid
            lookup={};last_city=None;stop=None;day_index=0
            for d in source_days:
                city=d['city'] or 'Unassigned stop'
                if city!=last_city:
                    stop_id=ident('stop',sid,d['id'])
                    location=PLACES.get(city.casefold())
                    stop={'id':stop_id,'scenarioId':sid,'name':city,'location':city,'position':sum(x['scenarioId']==sid for x in state['stops'].values()),
                          'startDate':d['day_date'] or None,'nights':1,'notes':'','lat':location[0] if location else None,'lng':location[1] if location else None,'archived':False}
                    state['stops'][stop_id]=stop;lookup.setdefault(city,[]).append(stop_id);last_city=city;day_index=0
                did=ident('day',sid,d['id'])
                state['days'][did]={'id':did,'scenarioId':sid,'stopId':stop['id'],'position':day_index,'date':d['day_date'] or None,'title':d['title'] or 'Day '+str(day_index+1),'notes':d['notes'] or '','archived':False}
                stop['nights']=max(stop['nights'],day_index+1);day_index+=1
                if not str(d['id']).startswith('new') and 'scenario_id' in d.keys():
                    for act in conn.execute('SELECT * FROM day_activities WHERE itinerary_id=? ORDER BY position,id',(d['id'],)):
                        aid=ident('activity',sid,act['id'])
                        state['activities'][aid]={'id':aid,'scenarioId':sid,'dayId':did,'name':act['title'],'time':act['start_time'] or '',
                            'notes':act['notes'],'position':act['position'],'archived':False,'confirmed':False}
            candidates=[o for o in originals if o['scenario_tag'] in (None,plan['name'])]
            choices={r['option_id'] for r in conn.execute('SELECT option_id FROM scenario_choices WHERE scenario_id=?',(plan['id'],))} if plan['id']!='new' else set()
            groups={}
            for opt in candidates:
                city=opt['city'];kind=opt['category']
                idea_id=ident('idea',tid,opt['id'])
                location=PLACES.get(city.casefold())
                user['ideas'].setdefault(idea_id,{'id':idea_id,'name':opt['name'],'type':kind,'location':city,'website':opt['link'] or '',
                    'notes':opt['notes'] or '', 'lat':location[0] if location else None,'lng':location[1] if location else None,'favorite':bool(opt['is_preferred']),'createdAt':now(),'archived':False})
                stop_ids=lookup.get(city,[])
                if not stop_ids and kind not in ('flight','transport'):
                    stop_id=ident('stop',sid,city)
                    state['stops'][stop_id]={'id':stop_id,'scenarioId':sid,'name':city,'location':city,'position':len(state['stops']),
                        'startDate':opt['start_date'],'nights':max(1,(date.fromisoformat(opt['end_date'])-date.fromisoformat(opt['start_date'])).days) if opt['end_date'] and opt['start_date'] else 1,
                        'notes':'','lat':location[0] if location else None,'lng':location[1] if location else None,'archived':False}
                    lookup[city]=[stop_id];stop_ids=[stop_id]
                stop_id=stop_ids[0] if stop_ids else None
                if len(stop_ids)>1 and opt['start_date']:
                    stop_id=min(stop_ids,key=lambda x:abs((date.fromisoformat(state['stops'][x]['startDate'] or opt['start_date'])-date.fromisoformat(opt['start_date'])).days))
                label=(opt['activity_group'] or opt['name']) if kind=='activity' else ('Castle stay' if kind=='castle' else 'Accommodation' if kind=='hotel' else city)
                group_key=(stop_id,kind,label)
                if group_key not in groups:
                    gid=ident('group',sid,*group_key)
                    state['groups'][gid]={'id':gid,'scenarioId':sid,'stopId':stop_id,'name':label,'type':kind,'position':len(groups),
                        'selectedId':None,'allowance':None,'notes':'','archived':False,'startDate':opt['start_date'],'endDate':opt['end_date']}
                    groups[group_key]=gid
                gid=groups[group_key];oid=ident('option',sid,opt['id'])
                fields={'startDate':opt['start_date'] or '', 'endDate':opt['end_date'] or '', 'notes':opt['notes'] or '',
                        'origin':opt['origin'] or '', 'destination':opt['destination'] or '', 'departureTime':opt['departure_time'] or '',
                        'arrivalTime':opt['arrival_time'] or '', 'layovers':opt['layovers'] or '', 'carrier':opt['carrier'] or ''}
                if kind=='flight':
                    fd=conn.execute('SELECT departure_date FROM flight_option_dates WHERE option_id=? AND scenario_id=?',(opt['id'],plan['id'])).fetchone()
                    if fd:fields['startDate']=fd[0]
                if kind=='activity':
                    ad=conn.execute('SELECT activity_date FROM activity_option_dates WHERE option_id=? AND scenario_id=?',(opt['id'],plan['id'])).fetchone()
                    if ad:fields['startDate']=ad[0]
                state['options'][oid]={'id':oid,'scenarioId':sid,'groupId':gid,'ideaId':idea_id,'type':kind,'label':'','fields':fields,
                    'quote':{'amount':opt['price'],'currency':'USD','basis':'total','quantity':1,'units':1,'startDate':fields['startDate'],
                             'endDate':fields['endDate'],'conditions':{},'checkedAt':None},'quoteHistory':[], 'stage':'shortlisted','parts':[],
                    'bookingId':None,'confirmed':False,'archived':False,'position':opt['id']}
                if opt['id'] in choices: state['groups'][gid]['selectedId']=oid
            # Independent, empty decision groups persist even without candidates.
            for stop_id in [x['id'] for x in state['stops'].values() if x['scenarioId']==sid]:
                if not any(g['stopId']==stop_id and g['type'] in ('hotel','castle') for g in state['groups'].values()):
                    gid=ident('group',sid,stop_id,'accommodation')
                    state['groups'][gid]={'id':gid,'scenarioId':sid,'stopId':stop_id,'name':'Accommodation','type':'hotel','position':0,'selectedId':None,'allowance':None,'notes':'','archived':False}
            if plan['id']!='new':
                for exp in conn.execute('SELECT * FROM scenario_expenses WHERE scenario_id=?',(plan['id'],)):
                    eid=ident('expense',sid,exp['id'])
                    state['expenses'][eid]={'id':eid,'scenarioId':sid,'name':exp['name'],'category':exp['category'], 'amount':exp['amount'],
                        'currency':'USD','coveredByAllowance':bool(exp['included_in_allowance']),'archived':False,'allocations':{}}
        return state

    def documents(conn,trip):
        if not conn.execute('SELECT 1 FROM trips WHERE id=? AND user_id=?',
                            (trip['id'], session['user_id'])).fetchone():
            abort(404)
        user,urev=load_user(conn,session['user_id'])
        row=conn.execute('SELECT * FROM planner_trip_documents WHERE trip_id=?',(trip['id'],)).fetchone()
        if row:return json.loads(row['body']),row['revision'],user,urev
        state=import_trip(conn,trip,user)
        conn.execute('INSERT INTO planner_trip_documents VALUES (?,1,?,?)',(trip['id'],json.dumps(state),now()))
        conn.execute('UPDATE planner_user_documents SET body=?,revision=revision+1,updated_at=? WHERE user_id=?',(json.dumps(user),now(),session['user_id']))
        return state,1,user,urev+1

    def bundle(state,rev,user,urev):
        return {'state':state,'revision':rev,'user':user,'userRevision':urev,'userId':session['user_id'],'csrf':app.jinja_env.globals['csrf_token']()}

    @app.post('/trips/<int:trip_id>/delete', endpoint='delete_trip')
    def delete_trip(trip_id):
        get_trip(trip_id)
        with db() as conn:
            trip = conn.execute('SELECT * FROM trips WHERE id=? AND user_id=?',
                                (trip_id, session['user_id'])).fetchone()
            if not trip:
                abort(404)
            document = conn.execute('SELECT body FROM planner_trip_documents WHERE trip_id=?',
                                    (trip_id,)).fetchone()
            name = json.loads(document['body'])['meta']['name'] if document else trip['name']
            if request.form.get('confirm-name', '').strip() != name.strip():
                abort(400, 'Type the trip name to confirm deletion.')
            files = conn.execute('SELECT id FROM planner_files WHERE trip_id=?', (trip_id,)).fetchall()
            # Images and attachments can be reused in another plan or the idea collection.
            references = [row['body'] for row in conn.execute(
                'SELECT body FROM planner_user_documents WHERE user_id=?', (session['user_id'],))]
            references.extend(row['body'] for row in conn.execute(
                'SELECT d.body FROM planner_trip_documents d JOIN trips t ON t.id=d.trip_id '
                'WHERE t.user_id=? AND t.id<>?', (session['user_id'], trip_id)))
            files = [file for file in files if not any(file['id'] in body for body in references)]
            for file in files:
                conn.execute('DELETE FROM planner_files WHERE id=?', (file['id'],))
            for table in ('planner_trip_documents', 'planner_operations'):
                conn.execute(f'DELETE FROM {table} WHERE trip_id=?', (trip_id,))
            # Relational itinerary, options and scenario rows use cascading foreign keys.
            conn.execute('DELETE FROM trips WHERE id=? AND user_id=?',
                         (trip_id, session['user_id']))
        for file in files:
            try:
                (data_dir / 'planner-files' / file['id']).unlink(missing_ok=True)
            except OSError:
                app.logger.warning('Could not remove an unreferenced trip attachment')
        return redirect(url_for('home'))

    @app.get('/api/places')
    def search_places():
        query = request.args.get('name', '').strip()
        if not 2 <= len(query) <= 100:
            abort(400, 'Enter a place name between 2 and 100 characters.')
        try:
            payload = json.loads(public_fetch('https://geocoding-api.open-meteo.com/v1/search?' +
                urlencode({'name': query, 'count': 5, 'language': 'en', 'format': 'json'}))[0])
            results = []
            for place in payload.get('results', [])[:5]:
                lat, lng = float(place['latitude']), float(place['longitude'])
                if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    continue
                label = ', '.join(dict.fromkeys(str(place[key]) for key in ('name', 'admin1', 'country') if place.get(key)))
                results.append({'label': label, 'lat': lat, 'lng': lng,
                                'timeZone': place.get('timezone', '')})
            return jsonify({'results': results})
        except (ValueError, KeyError, TypeError, OSError, http.client.HTTPException):
            return jsonify({'results': [], 'error': 'Place search is unavailable. You can save the stop and add its map location later.'}), 502

    @app.get('/trip/<int:trip_id>/plan',endpoint='planner_workspace')
    def workspace(trip_id):
        get_trip(trip_id)
        return render_template('planner.html',trip_id=trip_id)

    @app.get('/api/planner/<int:trip_id>')
    def planner_get(trip_id):
        trip=get_trip(trip_id)
        with db() as conn: result=bundle(*documents(conn,trip))
        response=jsonify(result);response.headers['Cache-Control']='no-store';return response

    @app.post('/api/planner/<int:trip_id>/sync')
    def planner_sync(trip_id):
        trip=get_trip(trip_id)
        payload=request.get_json(silent=True) or {};ops=payload.get('operations')
        if not isinstance(ops,list) or len(ops)>2000:abort(400,'Send at most 2000 operations at a time.')
        with db() as conn:
            state,rev,user,urev=documents(conn,trip)
            original=copy.deepcopy(state);original_user=copy.deepcopy(user);conflicts=[];new_ids=[]
            for op in ops:
                if not isinstance(op,dict):abort(400)
                opid=op.get('opId','');scope=op.get('scope','trip');collection=op.get('collection');eid=op.get('id','')
                if not re.fullmatch(r'[\w-]{1,100}',opid) or not re.fullmatch(r'[\w-]{1,100}',eid):abort(400,'Invalid operation identity.')
                if opid in new_ids:continue
                if conn.execute('SELECT 1 FROM planner_operations WHERE user_id=? AND op_id=?',(session['user_id'],opid)).fetchone():continue
                if scope not in ('trip','user'):abort(400)
                allowed=USER_COLLECTIONS if scope=='user' else COLLECTIONS+('meta',)
                if collection not in allowed:abort(400,'Invalid collection.')
                target=user if scope=='user' else state
                current=target['meta'] if collection=='meta' else target[collection].get(eid)
                patch=op.get('patch',{});base=op.get('base',{})
                if not isinstance(patch,dict) or not isinstance(base,dict) or len(patch)>70:abort(400)
                if current is None:
                    if not op.get('create'):conflicts.append({'opId':opid,'id':eid,'field':'record','mine':patch,'theirs':None});continue
                    current={'id':eid}
                for field,value in patch.items():
                    if any(part in ('id','__proto__','constructor','prototype') for part in field.split('.')) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:[.][A-Za-z][A-Za-z0-9_]*){0,8}',field):abort(400,'Invalid field.')
                    parent=current
                    parts=field.split('.')
                    for part in parts[:-1]:
                        if not isinstance(parent.get(part),dict):parent[part]={}
                        parent=parent[part]
                    prior=parent.get(parts[-1])
                    if prior!=base.get(field) and prior!=value:
                        conflicts.append({'opId':opid,'id':eid,'collection':collection,'field':field,'mine':value,'theirs':prior})
                    else:parent[parts[-1]]=value
                if collection=='meta':target['meta']=current
                else:target[collection][eid]=current
                new_ids.append(opid)
            if conflicts:return jsonify({'conflicts':conflicts,**bundle(original,rev,original_user,urev)}),409
            validate_graph(state,user)
            if state['meta']['name']!=original['meta']['name']:conn.execute('UPDATE trips SET name=? WHERE id=?',(state['meta']['name'],trip_id))
            conn.execute('UPDATE planner_trip_documents SET body=?,revision=revision+1,updated_at=? WHERE trip_id=?',(json.dumps(state,allow_nan=False),now(),trip_id))
            conn.execute('UPDATE planner_user_documents SET body=?,revision=revision+1,updated_at=? WHERE user_id=?',(json.dumps(user,allow_nan=False),now(),session['user_id']))
            conn.executemany('INSERT INTO planner_operations VALUES (?,?,?)',[(session['user_id'],oid,trip_id) for oid in new_ids])
        return jsonify(bundle(state,rev+1,user,urev+1))

    @app.get('/api/planner/<int:trip_id>/rates')
    def planner_rates(trip_id):
        get_trip(trip_id);base=request.args.get('base','USD').upper()
        if not re.fullmatch('[A-Z]{3}',base):abort(400)
        today=date.today().isoformat()
        with db() as conn:
            cached=conn.execute('SELECT * FROM planner_rates WHERE base=?',(base,)).fetchone()
            if cached and cached['checked_on']==today and request.args.get('refresh')!='1':return jsonify(json.loads(cached['body']))
        try:
            data=json.loads(public_fetch('https://api.frankfurter.dev/v2/rates?'+urlencode({'base':base,'quotes':'USD,EUR,GBP,CAD,AUD,NZD,JPY,CHF,SEK,NOK,DKK'}))[0])
            rates={base:1};dates=[]
            for item in data:
                rate=float(item['rate'])
                if math.isfinite(rate) and rate>0:rates[item['quote']]=1/rate;dates.append(item['date'])
            result={'base':base,'rates':rates,'asOf':min(dates) if dates else today,'cached':False,'provider':'Frankfurter'}
            with db() as conn:conn.execute('INSERT INTO planner_rates VALUES (?,?,?) ON CONFLICT(base) DO UPDATE SET body=excluded.body,checked_on=excluded.checked_on',(base,json.dumps(result),today))
        except (ValueError,KeyError,TypeError,OSError,http.client.HTTPException):
            result=json.loads(cached['body']) if cached else {'base':base,'rates':{base:1},'asOf':None,'provider':'Frankfurter'}
            result.update(cached=True,notice='Rates could not refresh. Last available rates are retained.')
        return jsonify(result)

    @app.post('/api/planner/<int:trip_id>/link-preview')
    def link_preview(trip_id):
        get_trip(trip_id);value=(request.get_json(silent=True) or {}).get('url','')
        try:
            content,final=public_fetch(value)
            soup=BeautifulSoup(content,'html.parser')
            title=soup.find('meta',property='og:title');description=soup.find('meta',attrs={'name':'description'})
            name=title.get('content','') if title else soup.title.get_text(' ',strip=True) if soup.title else ''
            suggestions={'name':name[:160],'website':final,'notes':description.get('content','')[:1000] if description else ''}
            return jsonify({'suggestions':suggestions,'notice':'Review these details before saving. Prices and availability were not verified.'})
        except (ValueError,OSError,http.client.HTTPException):return jsonify({'suggestions':{'website':value},'notice':'This page could not be read. You can enter everything manually.'})

    @app.post('/api/planner/<int:trip_id>/files')
    def upload_file(trip_id):
        get_trip(trip_id);f=request.files.get('file')
        if not f or not f.filename:abort(400)
        name=Path(f.filename).name[:180];ext=Path(name).suffix.lower()
        if ext not in ('.pdf','.png','.jpg','.jpeg','.webp','.txt','.ics','.docx'):abort(400,'Use a PDF, image, text, calendar or Word file.')
        contents=f.read(10*1024*1024+1)
        if len(contents)>10*1024*1024:abort(413,'Files must be 10 MB or smaller.')
        fid=uuid.uuid4().hex;folder=data_dir/'planner-files';folder.mkdir(exist_ok=True)
        path=folder/fid;path.write_bytes(contents);path.chmod(0o600)
        mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
        try:
            with db() as conn:
                if not conn.execute('SELECT 1 FROM trips WHERE id=? AND user_id=?',
                                    (trip_id, session['user_id'])).fetchone():
                    abort(404)
                conn.execute('INSERT INTO planner_files VALUES (?,?,?,?,?,?,?)',
                    (fid, trip_id, session['user_id'], name, mime, len(contents), now()))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return jsonify({'id':fid,'name':name,'size':len(contents),'url':url_for('planner_file',trip_id=trip_id,file_id=fid)})

    @app.get('/trip/<int:trip_id>/planner-files/<file_id>',endpoint='planner_file')
    def download_file(trip_id,file_id):
        # Shared research attachments retain their owner after a source trip is deleted.
        with db() as conn:row=conn.execute('SELECT * FROM planner_files WHERE id=? AND trip_id=? AND user_id=?',(file_id,trip_id,session['user_id'])).fetchone()
        if row is None:abort(404)
        response=send_file(data_dir/'planner-files'/file_id,as_attachment=True,download_name=row['name'],mimetype=row['mime'])
        response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff';return response

    @app.get('/planner-sw.js')
    def planner_sw():
        response=app.send_static_file('planner-sw.js')
        response.headers['Service-Worker-Allowed']='/';response.headers['Cache-Control']='no-cache';return response

    @app.get('/api/planner/<int:trip_id>/export')
    def planner_export(trip_id):
        trip=get_trip(trip_id)
        with db() as conn:result=bundle(*documents(conn,trip))
        result.pop('csrf',None)
        response=jsonify(result);response.headers['Content-Disposition']='attachment; filename=furlong-trip-backup.json';response.headers['Cache-Control']='no-store';return response


def validate_graph(state,user):
    """Validate persisted JSON and cross references, including financial bounds."""
    if len(json.dumps([state,user]))>5_000_000:abort(400,'This trip is too large for one update.')
    def walk(value,depth=0):
        if depth>18:abort(400,'Details are nested too deeply.')
        if isinstance(value,float) and not math.isfinite(value):abort(400,'Use finite numbers.')
        if isinstance(value,str) and len(value)>15000:abort(400,'Text is too long.')
        if isinstance(value,dict):
            if len(value)>10000:abort(400)
            for k,v in value.items():
                if k in ('__proto__','constructor','prototype'):abort(400,'Invalid field.')
                if k in ('website','link') and v and (not isinstance(v,str) or urlsplit(v).scheme not in ('http','https')):abort(400,'Links must use http or https.')
                if k in ('date','startDate','endDate','dueDate') and v:
                    try:date.fromisoformat(v)
                    except (TypeError,ValueError):abort(400,'Use a valid date.')
                if k in ('amount','chargedAmount','baseAmount','allowance','budget','foodAllowance','quantity','units','nights') and v is not None:
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1e9:abort(400,'Use a nonnegative amount or quantity.')
                if k in ('currency','baseCurrency') and v and (not isinstance(v,str) or not re.fullmatch('[A-Z]{3}',v)):abort(400,'Use a three-letter currency code.')
                walk(v,depth+1)
        elif isinstance(value,list):
            if len(value)>1000:abort(400)
            for v in value:walk(v,depth+1)
    walk(state);walk(user)
    for key in COLLECTIONS:
        if not isinstance(state.get(key),dict):abort(400)
        for eid,entity in state[key].items():
            if not isinstance(entity,dict) or entity.get('id')!=eid:abort(400)
            if entity.get('scenarioId') and entity['scenarioId'] not in state['scenarios']:abort(400,'Unknown itinerary alternative.')
    for group in state['groups'].values():
        if group.get('stopId') and group['stopId'] not in state['stops']:abort(400,'Unknown stop.')
        selected=group.get('selectedId')
        if selected and (selected not in state['options'] or state['options'][selected]['groupId']!=group['id']):abort(400,'Select an option from this group.')
    for option in state['options'].values():
        if option.get('ideaId') not in user['ideas']:abort(400,'Unknown idea.')
        if option.get('groupId') not in state['groups']:abort(400,'Unknown decision group.')
        if option.get('scenarioId')!=state['groups'][option['groupId']]['scenarioId']:abort(400,'Options stay within their alternative.')
        if option.get('bookingId') and option['bookingId'] not in state['bookings']:abort(400,'Unknown reservation.')
    for activity in state['activities'].values():
        if activity.get('dayId') and activity['dayId'] not in state['days']:abort(400,'Unknown day.')
    for payment in state['payments'].values():
        target=state['bookings'].get(payment.get('bookingId')) if payment.get('bookingId') else state['expenses'].get(payment.get('expenseId'))
        if target is None:abort(400,'Choose a recorded reservation or expense.')
        currency=(target.get('quote') or {}).get('currency') if payment.get('bookingId') else target.get('currency')
        if currency and payment.get('currency')!=currency:abort(400,'Payment currency must match the original cost.')
    for template in user['templates'].values():
        for field in template.get('fields',[]):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,40}',field.get('key','')):abort(400,'Use a short field key with letters and numbers.')
            if field.get('kind') not in ('text','textarea','number','date','time','url'):abort(400,'Unknown field type.')


def public_fetch(url,redirects=0):
    """Read public pages without credentials, private-network access or redirects to it."""
    if not isinstance(url,str) or len(url)>2048 or redirects>3:raise ValueError('Invalid URL')
    u=urlsplit(url)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:raise ValueError('Public URL required')
    port=u.port or (443 if u.scheme=='https' else 80)
    if port not in (80,443):raise ValueError('Unsupported port')
    addresses=socket.getaddrinfo(u.hostname,port,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Public address required')
    connection=(http.client.HTTPSConnection(u.hostname,port,timeout=6,context=ssl.create_default_context()) if u.scheme=='https' else http.client.HTTPConnection(u.hostname,port,timeout=6))
    try:
        connection.connect()
        if not ipaddress.ip_address(connection.sock.getpeername()[0]).is_global:raise ValueError('Public address required')
        connection.request('GET',(u.path or '/')+('?' +u.query if u.query else ''),headers={'User-Agent':'Furlong/2.0 (+https://github.com/ShilohCadere/furlong)','Accept':'application/json,text/html;q=0.9'})
        response=connection.getresponse()
        if response.status in (301,302,303,307,308):return public_fetch(urljoin(url,response.getheader('Location','')),redirects+1)
        if response.status!=200:raise ValueError('Page unavailable')
        content=response.read(1_000_001)
        if len(content)>1_000_000:raise ValueError('Page too large')
        return content,url
    finally:connection.close()
