"""Trip setup, whole-trip deletion, and place lookup regressions."""
import json
import unittest
import uuid
from unittest.mock import patch

import app as f
import planner
import test_planner


class TripManagementTests(unittest.TestCase):
    setUp = test_planner.PlannerTests.setUp
    tearDown = test_planner.PlannerTests.tearDown

    def test_route_builder_creates_independent_stops_days_and_map_locations(self):
        response = self.client.post('/', data={
            'trip-name': 'A fresh journey', 'first-route-name': 'Coast route',
            'route-stops': 'Dublin | 2\nGalway | 3\nEdinburgh | 2',
            'route-start': '2027-09-10', 'setup-budget': '20000', 'setup-food': '5120',
            'setup-places': json.dumps({'Dublin': {'label': 'Dublin, Ireland',
                'lat': 53.3498, 'lng': -6.2603, 'timeZone': 'Europe/Dublin'}})
        })
        self.assertEqual(response.status_code, 302)
        tid = int(response.location.split('/')[2])
        fresh = self.client.get(f'/api/planner/{tid}').get_json()
        state = fresh['state']
        stops = sorted(state['stops'].values(), key=lambda stop: stop['position'])
        self.assertEqual([stop['name'] for stop in stops], ['Dublin', 'Galway', 'Edinburgh'])
        self.assertEqual([stop['startDate'] for stop in stops], ['2027-09-10', '2027-09-12', '2027-09-15'])
        self.assertEqual(stops[0]['lat'], 53.3498)
        self.assertEqual(stops[0]['timeZone'], 'Europe/Dublin')
        self.assertIsNone(stops[1]['lat'])
        self.assertEqual(len(state['groups']), 3)
        self.assertEqual(len(state['days']), 7)
        self.assertEqual(len(state['options']), 0)
        scenario = next(iter(state['scenarios'].values()))
        self.assertEqual(scenario['foodAllowance'], 5120)
        self.assertEqual(scenario['name'], 'Coast route')
        self.assertEqual(fresh['user']['ideas'], self.u['ideas'])
        original = self.client.get(self.path).get_json()
        self.assertEqual(original['state'], self.s)
        self.client.post('/logout')
        self.client.post('/login', data={'username': 'planner', 'password': 'test-only-password'})
        self.assertEqual(self.client.get(f'/api/planner/{tid}').get_json()['state'], state)

    def test_invalid_setup_leaves_no_partial_trip(self):
        for values in ({'route-stops': 'Dublin | nope'}, {'route-stops': 'Dublin | 0'},
                       {'route-start': '2027-02-30'}, {'setup-food': 'nan'},
                       {'route-stops': 'Dublin | 2', 'setup-places': '[]'},
                       {'route-stops': 'Dublin | 2', 'setup-places': '{"Dublin":{"lat":999,"lng":0}}'}):
            with self.subTest(values=values):
                response = self.client.post('/', data={'trip-name': 'Invalid', **values})
                self.assertEqual(response.status_code, 400)
        with f.get_db_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trips').fetchone()[0], 1)

    def test_delete_requires_confirmation_and_removes_trip_data(self):
        path = f'/trips/{self.tid}/delete'
        self.assertEqual(self.client.post(path, data={'confirm-name': 'Wrong name'}).status_code, 400)
        file_id = uuid.uuid4().hex
        folder = f.DATA_DIR / 'planner-files'
        folder.mkdir(exist_ok=True)
        attachment = folder / file_id
        attachment.write_bytes(b'test attachment')
        with f.get_db_connection() as conn:
            uid = conn.execute('SELECT user_id FROM trips WHERE id=?', (self.tid,)).fetchone()[0]
            conn.execute('INSERT INTO planner_files VALUES (?,?,?,?,?,?,?)',
                (file_id, self.tid, uid, 'test.txt', 'text/plain', 15, planner.now()))
            conn.execute('INSERT INTO planner_operations VALUES (?,?,?)', (uid, 'delete-check', self.tid))
        response = self.client.post(path, data={'confirm-name': 'Europe'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(attachment.exists())
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.client.post(self.path + '/sync', json={'operations': []}).status_code, 404)
        with f.get_db_connection() as conn:
            for table in ('trips', 'trip_scenarios', 'saved_options', 'scenario_itinerary',
                          'planner_trip_documents', 'planner_operations', 'planner_files'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0, table)
            user = json.loads(conn.execute('SELECT body FROM planner_user_documents WHERE user_id=?', (uid,)).fetchone()[0])
            self.assertEqual(user['ideas'], self.u['ideas'])
        # An ordinary new trip retains the collection but starts without planning occurrences.
        self.client.post('/', data={'trip-name': 'Start again'})
        with f.get_db_connection() as conn:
            tid = conn.execute('SELECT id FROM trips').fetchone()[0]
        self.assertEqual(self.client.get(f'/api/planner/{tid}').get_json()['state']['options'], {})

    def test_deleting_trip_preserves_reusable_research_attachment(self):
        file_id = uuid.uuid4().hex
        folder = f.DATA_DIR / 'planner-files'
        folder.mkdir(exist_ok=True)
        attachment = folder / file_id
        attachment.write_bytes(b'reusable image')
        url = f'/trip/{self.tid}/planner-files/{file_id}'
        try:
            with f.get_db_connection() as conn:
                uid = conn.execute('SELECT user_id FROM trips WHERE id=?', (self.tid,)).fetchone()[0]
                user = self.u
                idea = next(iter(user['ideas'].values()))
                idea['image'] = {'id': file_id, 'url': url, 'name': 'image.png'}
                conn.execute('UPDATE planner_user_documents SET body=? WHERE user_id=?', (json.dumps(user), uid))
                conn.execute('INSERT INTO planner_files VALUES (?,?,?,?,?,?,?)',
                    (file_id, self.tid, uid, 'image.png', 'image/png', 14, planner.now()))
            self.assertEqual(self.client.post(f'/trips/{self.tid}/delete', data={'confirm-name': 'Europe'}).status_code, 302)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertTrue(attachment.exists())
            self.client.post('/logout')
            self.client.post('/register', data={'username': 'image-other', 'password': 'test-only-password'})
            self.assertEqual(self.client.get(url).status_code, 404)
        finally:
            attachment.unlink(missing_ok=True)

    def test_unmigrated_trip_can_be_deleted_and_other_accounts_cannot_delete(self):
        self.client.post('/', data={'trip-name': 'Unused trip'})
        with f.get_db_connection() as conn:
            tid = conn.execute('SELECT MAX(id) FROM trips').fetchone()[0]
        self.assertEqual(self.client.post(f'/trips/{tid}/delete', data={'confirm-name': 'Unused trip'}).status_code, 302)
        self.client.post('/logout')
        self.client.post('/register', data={'username': 'other', 'password': 'test-only-password'})
        self.assertEqual(self.client.post(f'/trips/{self.tid}/delete', data={'confirm-name': 'Europe'}).status_code, 404)

    def test_renamed_trip_uses_current_name_on_home_and_for_confirmation(self):
        with f.get_db_connection() as conn:
            state = dict(self.s)
            state['meta'] = {**state['meta'], 'name': ' Renamed trip '}
            conn.execute('UPDATE planner_trip_documents SET body=? WHERE trip_id=?',
                         (json.dumps(state), self.tid))
        self.assertIn(b'Type <strong> Renamed trip </strong>', self.client.get('/').data)
        self.assertEqual(self.client.post(f'/trips/{self.tid}/delete', data={'confirm-name': 'Europe'}).status_code, 400)
        self.assertEqual(self.client.post(f'/trips/{self.tid}/delete', data={'confirm-name': 'Renamed trip'}).status_code, 302)

    def test_delete_requires_csrf_outside_test_mode(self):
        f.app.config['TESTING'] = False
        try:
            response = self.client.post(f'/trips/{self.tid}/delete', data={'confirm-name': 'Europe'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.get(self.path).status_code, 200)
        finally:
            f.app.config['TESTING'] = True

    def test_places_offer_candidates_and_handle_failures(self):
        response_data = {'results': [
            {'name': 'Dublin', 'admin1': 'Leinster', 'country': 'Ireland',
             'latitude': 53.3498, 'longitude': -6.2603, 'timezone': 'Europe/Dublin'},
            {'name': 'Bad coordinate', 'latitude': 999, 'longitude': 0}]}
        with patch('planner.public_fetch', return_value=(json.dumps(response_data), '')) as fetch:
            response = self.client.get('/api/places?name=Dublin')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json['results']), 1)
            self.assertEqual(response.json['results'][0]['timeZone'], 'Europe/Dublin')
            self.assertIn('name=Dublin', fetch.call_args.args[0])
        with patch('planner.public_fetch', side_effect=OSError('offline')):
            self.assertEqual(self.client.get('/api/places?name=Dublin').status_code, 502)
        self.assertEqual(self.client.get('/api/places?name=D').status_code, 400)
        self.client.post('/logout')
        self.assertEqual(self.client.get('/api/places?name=Dublin').status_code, 302)
