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
