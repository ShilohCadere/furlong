"""Real client operations for activity prices and explicit journey placement."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import test_planner


@unittest.skipUnless(shutil.which('node'), 'Node is needed for client operations')
class PlanningDetailsTests(unittest.TestCase):
    setUp = test_planner.PlannerTests.setUp
    tearDown = test_planner.PlannerTests.tearDown
    op = test_planner.PlannerTests.op
    sync = test_planner.PlannerTests.sync

    def test_activity_quote_round_trip_replay_login_and_isolation(self):
        script = """
const fs=require('node:fs'),C=require('./static/planner-core.js');
const b=JSON.parse(fs.readFileSync(0,'utf8')),s=b.state;
const sid=Object.keys(s.scenarios)[0],day=Object.values(s.days).find(d=>d.scenarioId===sid);
const idea={id:'showidea',name:'Urzila Carlson',type:'activity',notes:'Keep the ticket notes',archived:false};
const activity={id:'showactivity',ideaId:idea.id,scenarioId:sid,dayId:day.id,name:idea.name,notes:'£35 per ticket',archived:false};
const changes=C.activityQuoteChanges(s,activity,{amount:35,currency:'GBP',basis:'person',quantity:4,units:1},true);
const operations=[C.operations('user','ideas',idea.id,null,idea),...changes.map(([kind,id,value])=>C.operations('trip',kind,id,s[kind][id],value))];
console.log(JSON.stringify({operations,optionId:changes.find(x=>x[0]==='options')[1]}));
"""
        generated = json.loads(subprocess.check_output(
            ['node', '-e', script], input=json.dumps(self.data).encode(),
            cwd=Path(__file__).resolve().parents[1]))
        response = self.sync(*generated['operations'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sync(*generated['operations']).status_code, 200)
        state = response.json['state']
        option = state['options'][generated['optionId']]
        self.assertEqual(option['quote']['amount'], 35)
        self.assertEqual(option['quote']['quantity'], 4)
        self.assertEqual(state['groups'][option['groupId']]['selectedId'], option['id'])
        self.assertEqual(state['activities']['showactivity']['optionId'], option['id'])
        self.assertEqual(state['activities']['showactivity']['notes'], '£35 per ticket')
        self.assertEqual(state['expenses'], self.s['expenses'])
        self.client.post('/logout')
        self.client.post('/login', data={'username': 'planner', 'password': 'test-only-password'})
        reloaded = self.client.get(self.path).json
        self.assertEqual(reloaded['state'], state)
        self.assertEqual(reloaded['user']['ideas']['showidea']['notes'], 'Keep the ticket notes')
        self.client.post('/logout')
        self.client.post('/register', data={'username': 'someoneelse', 'password': 'test-only-password'})
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_manual_journey_placement_persists_without_moving_dates_or_quotes(self):
        before = self.s['options'][self.oid]
        group = self.s['groups'][self.gid]
        response = self.sync(self.op('groups', self.gid, {
            'stopId': None, 'itineraryPlacement': 'before', 'anchorStopId': None,
        }, {'stopId': group['stopId']}))
        self.assertEqual(response.status_code, 200)
        fresh = self.client.get(self.path).json['state']
        self.assertEqual(fresh['groups'][self.gid]['itineraryPlacement'], 'before')
        self.assertIsNone(fresh['groups'][self.gid]['stopId'])
        self.assertEqual(fresh['options'][self.oid], before)
        self.assertEqual(fresh['stops'], self.s['stops'])

