"""Redesigned workspace: migration, independent plans, sync, privacy and actuals."""
import copy
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import app as f


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.previous=f.DATABASE
        self.testing=f.app.config['TESTING']
        f.DATABASE=Path(self.tmp.name)/'planner.db';f.app.config['TESTING']=True;f.init_db()
        self.client=f.app.test_client()
        self.client.post('/register',data={'username':'planner','password':'test-only-password'})
        self.client.post('/',data={'trip-name':'Europe','destination':'Europe'})
        with f.get_db_connection() as db:
            self.tid=db.execute('SELECT id FROM trips').fetchone()[0]
            legacy=db.execute('SELECT id FROM trip_scenarios').fetchone()[0]
        self.client.post(f'/trip/{self.tid}/itinerary/day',data={'scenario_id':legacy,'day_date':'2027-09-01','city':'Edinburgh','title':'Arrival'})
        self.client.post(f'/trip/{self.tid}/options/add',data={'city':'Edinburgh','category':'hotel','name':'Researched hotel','price':'300','start_date':'2027-09-01','end_date':'2027-09-03','link':'https://example.com/hotel'})
        self.path=f'/api/planner/{self.tid}'
        self.data=self.client.get(self.path).get_json();self.s=self.data['state'];self.u=self.data['user']
        self.sid=next(iter(self.s['scenarios']));self.oid=next(iter(self.s['options']));self.gid=self.s['options'][self.oid]['groupId']
    def test_auth_sessions_are_permanent_and_account_scoped(self):
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.permanent)
            self.assertEqual(sess.get('username'),'planner')
        self.client.post('/logout')
        self.assertEqual(self.client.get('/').status_code,302)
        response=self.client.post('/login',data={
            'username':'planner','password':'wrong-password'
        })
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.get('/').status_code,302)
        self.assertEqual(self.client.post('/login',data={
            'username':'planner','password':'test-only-password'
        }).status_code,302)
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.permanent)

    def test_removed_account_session_is_invalidated(self):
        with f.get_db_connection() as db:
            db.execute('DELETE FROM trips WHERE user_id=(SELECT id FROM users WHERE username=?)',('planner',))
            db.execute('DELETE FROM users WHERE username=?',('planner',))
        response=self.client.get('/')
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id',sess)

    def test_legacy_workspace_redirect_does_not_mutate_legacy_data(self):
        with f.get_db_connection() as db:
            before=db.execute('SELECT COUNT(*) FROM scenario_itinerary').fetchone()[0]
            scenario=db.execute('SELECT id FROM trip_scenarios WHERE trip_id=?',(self.tid,)).fetchone()[0]
            revision=db.execute('SELECT revision FROM planner_trip_documents WHERE trip_id=?',(self.tid,)).fetchone()[0]
        response=self.client.get(f'/trip/{self.tid}/workspace?scenario={scenario}')
        self.assertEqual(response.status_code,302)
        self.assertIn(f'/trip/{self.tid}/plan?scenario={scenario}',response.headers['Location'])
        with f.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scenario_itinerary').fetchone()[0],before)
            self.assertEqual(db.execute('SELECT revision FROM planner_trip_documents WHERE trip_id=?',(self.tid,)).fetchone()[0],revision)

    def test_migrated_trip_rejects_legacy_mutations_without_changing_data(self):
        with f.get_db_connection() as db:
            before=db.execute('SELECT COUNT(*) FROM saved_options WHERE trip_id=?',(self.tid,)).fetchone()[0]
            revision=db.execute('SELECT revision FROM planner_trip_documents WHERE trip_id=?',(self.tid,)).fetchone()[0]
        response=self.client.post(f'/trip/{self.tid}/options/add',data={
            'city':'London','category':'hotel','name':'Stale legacy option','price':'100'
        })
        self.assertEqual(response.status_code,409)
        with f.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM saved_options WHERE trip_id=?',(self.tid,)).fetchone()[0],before)
            self.assertEqual(db.execute('SELECT revision FROM planner_trip_documents WHERE trip_id=?',(self.tid,)).fetchone()[0],revision)

    def tearDown(self):
        f.DATABASE=self.previous;f.app.config['TESTING']=self.testing;self.tmp.cleanup()
    def op(self,col,id,patch,base=None,scope='trip',create=False):
        return {'opId':uuid.uuid4().hex,'scope':scope,'collection':col,'id':id,'patch':patch,'base':base or {},'create':create}
    def sync(self,*ops):return self.client.post(self.path+'/sync',json={'operations':list(ops)})
    def test_main_trip_routes_enter_redesigned_workspace(self):
        r=self.client.get(f'/trip/{self.tid}/plan')
        self.assertEqual(r.status_code,200)
        self.assertIn(b'planner-core.js',r.data)
        self.assertIn(b'conflict-dialog',r.data)
        self.assertIn(b'/plan',self.client.get('/').data)
    def test_migration_is_additive_idempotent_and_preserves_quotes(self):
        with f.get_db_connection() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if not r[0].startswith('planner_')]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        one=self.client.get(self.path).get_json();two=self.client.get(self.path).get_json()
        self.assertEqual(one['state'],two['state']);self.assertEqual(one['user'],two['user'])
        option=one['state']['options'][self.oid];self.assertEqual(option['quote']['amount'],300)
        self.assertEqual(one['user']['ideas'][option['ideaId']]['website'],'https://example.com/hotel')
        with f.get_db_connection() as db:self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
    def test_initial_import_respects_excluded_seed_tombstones(self):
        with f.get_db_connection() as db:
            db.execute("""INSERT INTO excluded_seed_options
                (trip_id,city,name,category,scenario_tag) VALUES (?,?,?,?,?)""",
                (self.tid,'Edinburgh','Researched hotel','hotel',''))
            db.execute('DELETE FROM planner_trip_documents WHERE trip_id=?',(self.tid,))
        imported=self.client.get(self.path).get_json()
        self.assertEqual(imported['state']['options'],{})
        # Previously imported user-library ideas are independent of trip migration.
        with f.get_db_connection() as db:
            self.assertEqual(db.execute(
                'SELECT COUNT(*) FROM saved_options WHERE trip_id=?',(self.tid,)
            ).fetchone()[0],1)
        self.assertEqual(self.client.get(self.path).get_json()['state'],imported['state'])

    def test_first_journey_opens_planner_after_creation(self):
        response=self.client.post('/',data={
            'trip-name':'First journey','destination':'Scotland',
            'first-route-name':'Main route'
        })
        self.assertEqual(response.status_code,302)
        with f.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='First journey'").fetchone()
        self.assertIsNotNone(trip)
        self.assertIn(f'/trip/{trip[0]}/plan',response.headers['Location'])

    def test_invalid_journey_form_does_not_create_trip(self):
        with f.get_db_connection() as db:
            initial=db.execute('SELECT COUNT(*) FROM trips').fetchone()[0]
        for data in [
            {'trip-name':'  ','first-route-name':'Main route'},
            {'trip-name':'x'*121,'first-route-name':'Main route'},
            {'trip-name':'Valid','first-route-name':' '},
            {'trip-name':'Valid','first-route-name':'Main route','destination':'x'*201},
        ]:
            response=self.client.post('/',data=data)
            self.assertEqual(response.status_code,400)
        with f.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trips').fetchone()[0],initial)

    def test_initial_import_does_not_mix_old_generic_days_into_scenario_plans(self):
        with f.get_db_connection() as db:
            db.execute('INSERT INTO itinerary_days (trip_id,day_number,title,trip_date) VALUES (?,?,?,?)',
                       (self.tid,1,'Old generic itinerary','2027-08-31'))
            db.execute('DELETE FROM scenario_itinerary WHERE trip_id=? AND day_date=?',
                       (self.tid,'2027-09-01'))
            db.execute('INSERT INTO trip_scenarios (trip_id,name) VALUES (?,?)',
                       (self.tid,'New September plan'))
            new_plan=db.execute('SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?',
                                (self.tid,'New September plan')).fetchone()[0]
            db.execute('INSERT INTO scenario_itinerary (trip_id,scenario_id,day_date,city,title,notes) VALUES (?,?,?,?,?,?)',
                       (self.tid,new_plan,'2027-09-14','Dublin','Arrival',''))
            db.execute('DELETE FROM planner_trip_documents WHERE trip_id=?',(self.tid,))
        state=self.client.get(self.path).get_json()['state']
        self.assertNotIn('2027-08-31',{d['date'] for d in state['days'].values()})
        self.assertIn('2027-09-14',{d['date'] for d in state['days'].values()})

    def test_initial_import_avoids_empty_hotel_group_when_castle_exists(self):
        with f.get_db_connection() as db:
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,start_date,end_date)
                VALUES (?,?,?,?,?,?,?)""",
                (self.tid,'Edinburgh','Castle option','castle',450,'2027-09-01','2027-09-03'))
            db.execute('DELETE FROM planner_trip_documents WHERE trip_id=?',(self.tid,))
        state=self.client.get(self.path).get_json()['state']
        for stop in state['stops'].values():
            if stop['name']!='Edinburgh':continue
            groups=[g for g in state['groups'].values() if g['stopId']==stop['id']]
            if any(g['type']=='castle' for g in groups):
                self.assertFalse(any(g['type']=='hotel' and not any(
                    o['groupId']==g['id'] for o in state['options'].values()) for g in groups))

    def test_unrelated_nested_fields_merge_from_stale_clients(self):
        old=self.s['options'][self.oid]['fields']
        a=self.op('options',self.oid,{'fields.notes':'First client'},{'fields.notes':old['notes']})
        b=self.op('options',self.oid,{'fields.rooms':2})
        self.assertEqual(self.sync(a).status_code,200);r=self.sync(b)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['state']['options'][self.oid]['fields']['notes'],'First client')
        self.assertEqual(r.json['state']['options'][self.oid]['fields']['rooms'],2)
    def test_same_field_conflict_keeps_both_and_is_atomic(self):
        self.assertEqual(self.sync(self.op('options',self.oid,{'label':'Remote'},{'label':''})).status_code,200)
        r=self.sync(self.op('options',self.oid,{'label':'Offline'},{'label':''}),self.op('meta','trip',{'name':'Must not apply'},{'name':'Europe'}))
        self.assertEqual(r.status_code,409);self.assertEqual(r.json['conflicts'][0]['mine'],'Offline');self.assertEqual(r.json['conflicts'][0]['theirs'],'Remote')
        self.assertEqual(self.client.get(self.path).json['state']['meta']['name'],'Europe')
    def test_replayed_operations_are_idempotent(self):
        op=self.op('options',self.oid,{'label':'One operation'},{'label':''})
        self.assertEqual(self.sync(op).status_code,200);self.assertEqual(self.sync(op).status_code,200)
        with f.get_db_connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM planner_operations WHERE op_id=?',(op['opId'],)).fetchone()[0],1)
    def test_empty_group_remains_after_removing_last_option(self):
        r=self.sync(self.op('options',self.oid,{'archived':True},{'archived':False}))
        self.assertEqual(r.status_code,200);self.assertIn(self.gid,r.json['state']['groups']);self.assertEqual(r.json['state']['options'][self.oid]['quote']['amount'],300)
    def test_named_alternative_and_repeated_occurrences_share_only_idea(self):
        old=self.s['options'][self.oid];newid='alternative2';newgroup='group2';newoption='occurrence2'
        scenario=copy.deepcopy(self.s['scenarios'][self.sid]);scenario.pop('id');scenario['name']='Scotland first'
        group=copy.deepcopy(self.s['groups'][self.gid]);group.pop('id');group.update(scenarioId=newid,stopId=None,selectedId=None)
        option=copy.deepcopy(old);option.pop('id');option.update(groupId=newgroup,scenarioId=newid)
        r=self.sync(self.op('scenarios',newid,scenario,create=True),self.op('groups',newgroup,group,create=True),self.op('options',newoption,option,create=True))
        self.assertEqual(r.status_code,200)
        r=self.sync(self.op('options',newoption,{'fields.startDate':'2027-10-01'},{'fields.startDate':old['fields']['startDate']}))
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['state']['options'][self.oid]['fields']['startDate'],'2027-09-01')
        self.assertEqual(r.json['state']['options'][newoption]['ideaId'],old['ideaId'])
    def test_booking_and_actual_payment_survive_switching_active_plan(self):
        booking={'name':'Actual reservation','fields':{'startDate':'2027-09-01'},'quote':{'amount':300,'currency':'GBP','basis':'total'},'canceled':False}
        payment={'bookingId':'booked','amount':100,'currency':'GBP','baseAmount':123,'baseCurrency':'USD','date':'2027-08-01','archived':False}
        r=self.sync(self.op('bookings','booked',booking,create=True),self.op('options',self.oid,{'bookingId':'booked'}),self.op('payments','deposit',payment,create=True))
        self.assertEqual(r.status_code,200)
        r=self.sync(self.op('options',self.oid,{'archived':True},{'archived':False}))
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['state']['payments']['deposit']['baseAmount'],123);self.assertIn('booked',r.json['state']['bookings'])
    def test_unknown_cost_does_not_require_quote_to_save(self):
        r=self.sync(self.op('options',self.oid,{'quote.amount':None},{'quote.amount':300}))
        self.assertEqual(r.status_code,200);self.assertIsNone(r.json['state']['options'][self.oid]['quote']['amount'])
    def test_forged_references_invalid_prices_urls_and_prototype_fields_rejected(self):
        for patch,base in [({'groupId':'foreign'},{'groupId':self.gid}),({'quote.amount':-1},{'quote.amount':300}),({'fields.startDate':'bad-date'},{'fields.startDate':'2027-09-01'}),({'__proto__.polluted':'x'}, {})]:
            with self.subTest(patch=patch):self.assertEqual(self.sync(self.op('options',self.oid,patch,base)).status_code,400)
        idea=self.s['options'][self.oid]['ideaId']
        self.assertEqual(self.sync(self.op('ideas',idea,{'website':'javascript:alert(1)'},{'website':'https://example.com/hotel'},scope='user')).status_code,400)
    def test_login_ownership_and_csrf_remain_enforced(self):
        guest=f.app.test_client();self.assertEqual(guest.get(self.path).status_code,302)
        guest.post('/register',data={'username':'other','password':'another-test-password'})
        self.assertEqual(guest.get(self.path).status_code,404);self.assertEqual(guest.post(self.path+'/sync',json={'operations':[]}).status_code,404)
        f.app.config['TESTING']=False
        self.assertEqual(self.client.post(self.path+'/sync',json={'operations':[]}).status_code,400)
        self.assertEqual(self.client.post(self.path+'/sync',json={'operations':[]},headers={'X-CSRF-Token':self.data['csrf']}).status_code,200)
    def test_rates_cache_and_failure_preserve_original_currency(self):
        payload=json.dumps([{'quote':'GBP','rate':.8,'date':'2026-10-30'}]).encode()
        with patch('planner.public_fetch',return_value=(payload,'https://api.frankfurter.dev')):
            r=self.client.get(self.path+'/rates?base=USD');self.assertEqual(r.json['rates']['GBP'],1.25)
        with patch('planner.public_fetch',side_effect=OSError('Unavailable')):
            r=self.client.get(self.path+'/rates?base=USD&refresh=1');self.assertEqual(r.json['rates']['GBP'],1.25);self.assertTrue(r.json['cached'])
    def test_link_fill_is_reviewable_and_manual_entry_survives_failure(self):
        with patch('planner.public_fetch',return_value=(b'<title>Useful hotel</title><meta name="description" content="A place to stay">','https://example.com/hotel')):
            r=self.client.post(self.path+'/link-preview',json={'url':'https://example.com/hotel'})
            self.assertEqual(r.json['suggestions']['name'],'Useful hotel');self.assertNotIn('price',r.json['suggestions'])
        with patch('planner.public_fetch',side_effect=ValueError('Private address')):
            self.assertEqual(self.client.post(self.path+'/link-preview',json={'url':'http://127.0.0.1/'}).status_code,200)
    def test_trip_rename_is_reflected_on_journeys_page(self):
        r=self.sync(self.op('meta','trip',{'name':'Renamed journey'},{'name':'Europe'}));self.assertEqual(r.status_code,200)
        self.assertIn(b'Renamed journey',self.client.get('/').data)
    def test_export_contains_graph_but_no_session_token(self):
        r=self.client.get(self.path+'/export');self.assertEqual(r.status_code,200);self.assertNotIn('csrf',r.json);self.assertIn(self.oid,r.json['state']['options'])
