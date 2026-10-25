"""User-journey checks beyond the Saved Options regression suite."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

from bs4 import BeautifulSoup
import app as furlong


class ReleaseJourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_database = furlong.DATABASE
        self.old_testing = furlong.app.config.get('TESTING', False)
        furlong.app.config['TESTING'] = True
        furlong.DATABASE = Path(self.tmp.name) / "journey.db"
        furlong.init_db()
        self.client = furlong.app.test_client()
        self.client.post('/register', data={'username': 'alice', 'password': 'alice-example-password'})
        self.client.post('/', data={'trip-name': 'Journey', 'destination': 'Scotland'})
        with furlong.get_db_connection() as db:
            self.trip = db.execute('SELECT id FROM trips').fetchone()[0]
        self.client.get(f'/trip/{self.trip}/workspace')
        with furlong.get_db_connection() as db:
            self.sid = db.execute('SELECT id FROM trip_scenarios').fetchone()[0]

    def tearDown(self):
        furlong.DATABASE = self.old_database
        furlong.app.config['TESTING'] = self.old_testing
        self.tmp.cleanup()

    def day(self, when, title):
        res = self.client.post(f'/trip/{self.trip}/itinerary/day', data={
            'scenario_id': self.sid, 'day_date': when, 'city': 'Edinburgh', 'title': title})
        self.assertEqual(res.status_code, 302)
        with furlong.get_db_connection() as db:
            return db.execute('SELECT id FROM scenario_itinerary WHERE scenario_id=? AND day_date=?',
                              (self.sid, when)).fetchone()[0]

    def test_overview_uses_current_itinerary_and_links_to_real_days(self):
        for day in range(1, 5):
            self.day(f'2027-09-0{day}', f'Journey day {day}')
        page = self.client.get(f'/trip/{self.trip}')
        soup = BeautifulSoup(page.data, 'html.parser')
        count = soup.select_one('.overview-day-count')
        self.assertIsNotNone(count, 'Overview reports no days after four dated days were created')
        self.assertEqual(' '.join(count.get_text(' ', strip=True).split()), '4 days planned')
        links = soup.select('.overview-day-link')
        self.assertEqual(len(links), 3)
        for link in links:
            path, fragment = link['href'].split('#', 1)
            itinerary = BeautifulSoup(self.client.get(path).data, 'html.parser')
            self.assertIsNotNone(itinerary.find(id=fragment), link['href'])

    def test_overview_shows_upcoming_days_for_an_in_progress_trip(self):
        for day in range(1, 6):
            self.day(f'2027-09-0{day}', f'Journey day {day}')
        class TripDate(date):
            @classmethod
            def today(cls):
                return cls(2027, 9, 3)
        with patch.object(furlong, 'date', TripDate):
            soup = BeautifulSoup(self.client.get(f'/trip/{self.trip}').data, 'html.parser')
        self.assertEqual([x.get_text(strip=True) for x in soup.select('.overview-day-name')],
                         ['Journey day 3', 'Journey day 4', 'Journey day 5'])

    def test_overview_route_selection_is_scoped_and_rejects_unknown_routes(self):
        self.day('2027-09-01', 'First route only')
        self.client.post(f'/trip/{self.trip}/workspace/scenarios', data={'name': 'Plan B'})
        with furlong.get_db_connection() as db:
            second = db.execute("SELECT id FROM trip_scenarios WHERE name='Plan B'").fetchone()[0]
        page = self.client.get(f'/trip/{self.trip}?scenario={second}')
        self.assertNotIn(b'First route only', page.data)
        self.assertEqual(self.client.get(f'/trip/{self.trip}?scenario=99999').status_code, 404)
        page = self.client.get(f'/trip/{self.trip}?scenario={self.sid}')
        soup = BeautifulSoup(page.data, 'html.parser')
        self.assertIn(f'scenario={self.sid}', soup.select_one('.overview-day-link')['href'])

    def test_equal_and_descriptive_times_remain_stable_after_clock_times(self):
        day = self.day('2027-09-01', 'Stable order')
        for title, when in [('Flexible', ''), ('Morning note', 'Morning'),
                            ('First booking', '10:00'), ('Second booking', '10:00 AM')]:
            self.client.post(f'/trip/{self.trip}/itinerary/activity', data={
                'scenario_id': self.sid, 'itinerary_id': day, 'title': title, 'start_time': when})
        page = BeautifulSoup(self.client.get(f'/trip/{self.trip}/itinerary').data, 'html.parser')
        self.assertEqual([x.get_text(strip=True) for x in page.select('.itinerary-activity strong')],
                         ['First booking', 'Second booking', 'Morning note', 'Flexible'])

    def test_activities_sort_by_time_with_untimed_last_in_both_views(self):
        day = self.day('2027-09-01', 'Arrival')
        for title, when in [('Untimed walk', ''), ('Late dinner', '7:00 PM'),
                            ('Breakfast', '08:30'), ('Museum', '10:00 AM')]:
            res = self.client.post(f'/trip/{self.trip}/itinerary/activity', data={
                'scenario_id': self.sid, 'itinerary_id': day, 'title': title, 'start_time': when})
            self.assertEqual(res.status_code, 302)
        self.client.post(f'/trip/{self.trip}/options/add', data={
            'city': 'Edinburgh', 'name': 'Hotel', 'category': 'hotel', 'price': '300'})
        page = BeautifulSoup(self.client.get(f'/trip/{self.trip}/itinerary?scenario={self.sid}').data,
                             'html.parser')
        self.assertEqual([x.get_text(strip=True) for x in page.select('.itinerary-activity strong')],
                         ['Breakfast', 'Museum', 'Late dinner', 'Untimed walk'])
        city = self.client.get(f'/trip/{self.trip}/city/Edinburgh?scenario={self.sid}').get_data(as_text=True)
        self.assertLess(city.index('Breakfast'), city.index('Late dinner'))
        self.assertLess(city.index('Late dinner'), city.index('Untimed walk'))

    def test_invalid_expense_flag_is_rejected_without_server_error(self):
        page = self.client.post(f'/trip/{self.trip}/workspace/expense', data={
            'scenario_id': self.sid, 'category': 'food', 'name': 'Dinner',
            'amount': '20', 'included_in_allowance': 'unexpected'})
        self.assertEqual(page.status_code, 400)
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scenario_expenses').fetchone()[0], 0)

    def test_foreign_account_cannot_read_or_change_trip_through_any_trip_route(self):
        day = self.day('2027-09-01', 'Private plan')
        self.client.post(f'/trip/{self.trip}/itinerary/activity', data={
            'scenario_id': self.sid, 'itinerary_id': day, 'title': 'Private activity'})
        self.client.post(f'/trip/{self.trip}/options/add', data={
            'city': 'Edinburgh', 'name': 'Private hotel', 'category': 'hotel', 'price': '300'})
        with furlong.get_db_connection() as db:
            before = list(db.iterdump())
        other = furlong.app.test_client()
        other.post('/register', data={'username': 'bob', 'password': 'bob-example-password'})
        with furlong.get_db_connection() as db:
            before = list(db.iterdump())
        for rule in furlong.app.url_map.iter_rules():
            if 'trip_id' not in rule.arguments:
                continue
            values = {'trip_id': self.trip, 'option_id': 1, 'activity_id': 1,
                      'expense_id': 1, 'city': 'Edinburgh'}
            with furlong.app.test_request_context():
                url = rule.build({k: values[k] for k in rule.arguments})[1]
            for method in rule.methods & {'GET', 'POST'}:
                with self.subTest(url=url, method=method):
                    self.assertEqual(other.open(url, method=method).status_code, 404)
        with furlong.get_db_connection() as db:
            self.assertEqual(list(db.iterdump()), before)

    def test_itinerary_and_quote_survive_new_login_and_database_initialization(self):
        self.day('2027-09-01', 'Persisted plan')
        self.client.post(f'/trip/{self.trip}/options/add', data={
            'city': 'Edinburgh', 'name': 'Quoted hotel', 'category': 'hotel', 'price': '300'})
        with furlong.get_db_connection() as db:
            oid = db.execute('SELECT id FROM saved_options').fetchone()[0]
        self.client.post(f'/trip/{self.trip}/options/{oid}/quote', data={'price': '444.25'})
        self.client.post('/logout')
        furlong.init_db()
        fresh = furlong.app.test_client()
        fresh.post('/login', data={'username': 'alice', 'password': 'alice-example-password'})
        self.assertIn(b'Persisted plan', fresh.get(f'/trip/{self.trip}/itinerary').data)
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT price FROM saved_options WHERE id=?', (oid,)).fetchone()[0], 444.25)

    def test_legacy_days_remain_visible_after_opening_workspace(self):
        self.client.post(f'/trip/{self.trip}/itinerary/add-day')
        with furlong.get_db_connection() as db:
            db.execute('UPDATE itinerary_days SET title=? WHERE trip_id=?', ('Legacy plan', self.trip))
        page = self.client.get(f'/trip/{self.trip}/itinerary')
        self.assertIn(b'Legacy plan', page.data)

    def test_playground_get_preserves_every_persisted_row(self):
        self.day('2027-09-01', 'Read-only check')
        with furlong.get_db_connection() as db:
            before = list(db.iterdump())
        res = self.client.get(f'/trip/{self.trip}/budget-playground?scenario={self.sid}')
        self.assertEqual(res.status_code, 200)
        with furlong.get_db_connection() as db:
            self.assertEqual(list(db.iterdump()), before)


if __name__ == '__main__':
    unittest.main()
