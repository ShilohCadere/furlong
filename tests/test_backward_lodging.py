"""Backward lodging must use live dates without changing existing trip data."""
import sqlite3
import unittest
from urllib.parse import parse_qs, urlsplit

from backward_lodging import add_backward_lodging, booking_link


class BackwardLodgingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE trip_scenarios(id INTEGER PRIMARY KEY,trip_id INTEGER,name TEXT);
            CREATE TABLE scenario_itinerary(trip_id INTEGER,scenario_id INTEGER,day_date TEXT,city TEXT,title TEXT);
            CREATE TABLE saved_options(id INTEGER PRIMARY KEY,trip_id INTEGER,city TEXT,name TEXT,category TEXT,price REAL,link TEXT,notes TEXT,start_date TEXT,end_date TEXT,scenario_tag TEXT);
            CREATE TABLE excluded_seed_options(trip_id INTEGER,city TEXT,name TEXT,category TEXT,scenario_tag TEXT);
            CREATE TABLE scenario_choices(scenario_id INTEGER,option_id INTEGER);
            INSERT INTO trip_scenarios VALUES (1,1,'12 OTG'),(2,1,'12 OTG Backwards'),
                (3,1,'14 OTG'),(4,1,'14 OTG Backwards');
            INSERT INTO scenario_itinerary VALUES
                (1,2,'2027-09-15','London','Arrive London'),
                (1,2,'2027-09-16','London','Stonehenge'),
                (1,2,'2027-09-17','London','Tower of London'),
                (1,2,'2027-09-20','Edinburgh','Arrive Edinburgh'),
                (1,2,'2027-09-21','Edinburgh','Edinburgh Castle and Royal Mile'),
                (1,2,'2027-09-22','Edinburgh','Melville Castle stay'),
                (1,4,'2027-09-14','London','Arrive London'),
                (1,4,'2027-09-15','London','Stonehenge'),
                (1,4,'2027-09-16','London','Tower of London');
            INSERT INTO saved_options VALUES (1,1,'London','Forward Hotel','hotel',900,
                'https://www.expedia.com/.h123.Hotel-Information?chkin=2027-09-25&chkout=2027-09-28&rm1=a2',
                'User verified quote','2027-09-25','2027-09-28','12 OTG');
            INSERT INTO scenario_choices VALUES (1,1);
        """)

    def tearDown(self):
        self.db.close()

    def test_actual_route_names_dates_and_two_rooms(self):
        add_backward_lodging(self.db, 1)
        row = self.db.execute("SELECT * FROM saved_options WHERE name='Forward Hotel' AND scenario_tag='12 OTG Backwards'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual((row['start_date'], row['end_date']), ('2027-09-15','2027-09-18'))
        self.assertIsNone(row['price'])
        params = parse_qs(urlsplit(row['link']).query)
        self.assertEqual(params['chkin'], ['2027-09-15'])
        self.assertEqual(params['chkout'], ['2027-09-18'])
        self.assertEqual((params['rm1'], params['rm2']), (['a2'], ['a2']))
        longer = self.db.execute("SELECT * FROM saved_options WHERE scenario_tag='14 OTG Backwards' LIMIT 1").fetchone()
        self.assertEqual((longer['start_date'],longer['end_date']),('2027-09-14','2027-09-17'))

    def test_preserves_quotes_selections_and_repeat_visits(self):
        original = tuple(self.db.execute('SELECT * FROM saved_options WHERE id=1').fetchone())
        add_backward_lodging(self.db, 1)
        before = [tuple(r) for r in self.db.execute('SELECT * FROM saved_options ORDER BY id')]
        add_backward_lodging(self.db, 1)
        self.assertEqual(before, [tuple(r) for r in self.db.execute('SELECT * FROM saved_options ORDER BY id')])
        self.assertEqual(original, tuple(self.db.execute('SELECT * FROM saved_options WHERE id=1').fetchone()))
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM scenario_choices')],[(1,1)])

    def test_castle_night_stays_separate(self):
        add_backward_lodging(self.db, 1)
        rows = self.db.execute("SELECT * FROM saved_options WHERE city='Edinburgh' AND scenario_tag='12 OTG Backwards'").fetchall()
        self.assertTrue(rows)
        self.assertTrue(all((r['start_date'],r['end_date'])==('2027-09-20','2027-09-22') for r in rows))

    def test_excluded_property_and_renamed_listing_are_not_added(self):
        self.db.execute("INSERT INTO excluded_seed_options VALUES (1,'London','Forward Hotel — 2-room estimate','hotel','12 OTG Backwards')")
        self.db.execute("INSERT INTO saved_options(trip_id,city,name,category,link,scenario_tag) VALUES (1,'London','My renamed apartment','hotel','https://www.expedia.com/.h69712519.Hotel-Information','12 OTG Backwards')")
        add_backward_lodging(self.db, 1)
        self.assertFalse(self.db.execute("SELECT 1 FROM saved_options WHERE name='Forward Hotel' AND scenario_tag='12 OTG Backwards'").fetchone())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM saved_options WHERE link LIKE '%.h69712519.%' AND scenario_tag='12 OTG Backwards'").fetchone()[0],1)

    def test_noncontiguous_old_itinerary_does_not_get_misdated_options(self):
        self.db.execute("INSERT INTO scenario_itinerary VALUES (1,2,'2027-09-25','London','Old duplicated day')")
        add_backward_lodging(self.db, 1)
        self.assertFalse(self.db.execute("SELECT 1 FROM saved_options WHERE city='London' AND scenario_tag='12 OTG Backwards'").fetchone())

    def test_rental_link_has_four_adults_and_no_stale_second_room(self):
        url = booking_link('https://www.expedia.com/.h123.Hotel-Information?rm1=a2&rm2=a2&startDate=2027-08-01&endDate=2027-08-02',
                           'Apartment','London','2027-09-15','2027-09-18',True)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['rm1'], ['a4'])
        self.assertNotIn('rm2',query)
        self.assertNotIn('startDate',query)


if __name__ == '__main__':
    unittest.main()
