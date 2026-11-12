"""Regression tests for Saved Options. Run: python -m unittest discover -s tests -v"""
import tempfile
import unittest
from pathlib import Path

import app as furlong


class SavedOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_database = furlong.DATABASE
        self.old_testing = furlong.app.config.get("TESTING", False)
        furlong.app.config["TESTING"] = True
        self.old_import_setting = furlong.app.config.get("ENABLE_EUROPE_IMPORT", False)
        furlong.app.config["ENABLE_EUROPE_IMPORT"] = True
        furlong.DATABASE = Path(self.tmp.name) / "test.db"
        furlong.init_db()
        self.client = furlong.app.test_client()
        registered=self.client.post("/register",data={"username":"testuser","password":"correct-horse-battery"})
        self.assertEqual(registered.status_code,302)
        with furlong.get_db_connection() as conn:
            user_id=conn.execute("SELECT id FROM users WHERE username='testuser'").fetchone()[0]
            conn.execute("INSERT INTO trips (name,destination,user_id) VALUES (?,?,?)", ("Test trip", "Ireland",user_id))
            self.trip_id = conn.execute("SELECT id FROM trips").fetchone()[0]

    def tearDown(self):
        furlong.app.config["ENABLE_EUROPE_IMPORT"] = self.old_import_setting
        furlong.DATABASE = self.old_database
        furlong.app.config["TESTING"] = self.old_testing
        self.tmp.cleanup()

    def add(self, name, city="Galway", price="400", category="hotel"):
        return self.client.post(
            f"/trip/{self.trip_id}/options/add",
            data={"city":city,"name":name,"price":price,"category":category},
            follow_redirects=True
        )

    def test_new_account_does_not_claim_unowned_trips_by_default(self):
        import os
        from unittest.mock import patch
        old_database = furlong.DATABASE
        try:
            with tempfile.TemporaryDirectory() as temp:
                furlong.DATABASE = Path(temp) / "fresh.db"
                furlong.init_db()
                with furlong.get_db_connection() as db:
                    db.execute("INSERT INTO trips(name,destination) VALUES (?,?)",
                               ("Legacy private trip", "Unknown"))
                with patch.dict(os.environ, {"FURLONG_CLAIM_LEGACY_TRIPS": "0"}):
                    client = furlong.app.test_client()
                    response = client.post("/register", data={
                        "username": "freshuser", "password": "strong-password-123"
                    })
                    self.assertEqual(response.status_code, 302)
                    self.assertNotIn(b"Legacy private trip", client.get("/").data)
                with furlong.get_db_connection() as db:
                    owner = db.execute("SELECT user_id FROM trips WHERE name=?",
                                       ("Legacy private trip",)).fetchone()[0]
                    self.assertIsNone(owner)
        finally:
            furlong.DATABASE = old_database

    def test_csrf_rejects_missing_and_invalid_tokens(self):
        # Existing functional tests run with their historical direct POST setup;
        # this test explicitly checks production CSRF enforcement.
        old_testing = furlong.app.config.get("TESTING", False)
        furlong.app.config["TESTING"] = False
        try:
            self.assertEqual(self.client.post("/", data={"trip-name": "Forged"}).status_code, 400)
            self.assertEqual(self.client.post("/", data={
                "trip-name": "Forged", "_csrf_token": "wrong"
            }).status_code, 400)
            page = self.client.get("/")
            import re
            token = re.search(rb'name="_csrf_token" value="([^"]+)"', page.data)
            self.assertIsNotNone(token)
            response = self.client.post("/", data={
                "trip-name": "Protected", "first-route-name": "Main route",
                "_csrf_token": token.group(1).decode()
            })
            self.assertEqual(response.status_code, 302)
        finally:
            furlong.app.config["TESTING"] = old_testing

    def test_accounts_keep_trips_private_and_login_restores_them(self):
        trip=self.trip_id
        self.client.post("/logout")
        self.assertEqual(self.client.get(f"/trip/{trip}").status_code,302)
        self.assertEqual(self.client.post("/register",data={
            "username":"anotheruser","password":"another-long-password"}).status_code,302)
        self.assertEqual(self.client.get(f"/trip/{trip}").status_code,404)
        self.assertNotIn(b"Test trip",self.client.get("/").data)
        self.assertEqual(self.client.post("/trips/import-europe-2027").status_code,302)
        with furlong.get_db_connection() as db:
            owned=db.execute("""SELECT user_id FROM trips WHERE name='Europe 2027'
                ORDER BY id DESC LIMIT 1""").fetchone()["user_id"]
            another=db.execute("SELECT id FROM users WHERE username='anotheruser'").fetchone()["id"]
            self.assertEqual(owned,another)
        self.client.post("/logout")
        self.client.post("/login",data={"username":"testuser","password":"correct-horse-battery"})
        self.assertEqual(self.client.get(f"/trip/{trip}").status_code,200)
        self.assertIn(b"Test trip",self.client.get("/").data)
        self.assertEqual(self.client.post("/login",data={
            "username":"testuser","password":"wrong-password"}).status_code,401)

    def test_multiple_options_and_preference_preserves_alternatives(self):
        self.assertEqual(self.add("Eyre Square").status_code, 200)
        self.assertEqual(self.add("The Western",price="510").status_code, 200)
        with furlong.get_db_connection() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM saved_options ORDER BY id")]
        self.client.post(f"/trip/{self.trip_id}/options/{ids[0]}/prefer")
        res = self.client.post(f"/trip/{self.trip_id}/options/{ids[1]}/prefer",follow_redirects=True)
        self.assertIn(b"The Western",res.data)
        self.assertIn(b"Eyre Square",res.data)
        with furlong.get_db_connection() as db:
            entries = db.execute("SELECT name,is_preferred FROM saved_options ORDER BY id").fetchall()
        self.assertEqual([(x["name"],x["is_preferred"]) for x in entries],[("Eyre Square",0),("The Western",1)])

    def test_scenarios_are_independent_and_budget_updates(self):
        self.add("Eyre Square",price="1006")
        self.add("Four Seasons",price="960")
        self.assertEqual(self.client.get(f"/trip/{self.trip_id}/workspace").status_code,200)
        self.client.post(f"/trip/{self.trip_id}/workspace/scenarios",data={"name":"L1"})
        with furlong.get_db_connection() as db:
            plans=db.execute("SELECT * FROM trip_scenarios ORDER BY id").fetchall()
            hotels=db.execute("SELECT id FROM saved_options ORDER BY id").fetchall()
        for s,h in zip(plans,hotels):
            response=self.client.post(f"/trip/{self.trip_id}/workspace/choose",data={
                "scenario_id":s["id"],"option_id":h["id"],"city":"Galway","category":"hotel"
            },follow_redirects=True)
            self.assertEqual(response.status_code,200)
        first=self.client.get(f"/trip/{self.trip_id}/workspace?scenario={plans[0]['id']}")
        second=self.client.get(f"/trip/{self.trip_id}/workspace?scenario={plans[1]['id']}")
        self.assertIn(b"$1006",first.data)
        self.assertIn(b"$960",second.data)
        self.client.post(f"/trip/{self.trip_id}/workspace/settings",data={"scenario_id":plans[0]["id"],"budget_limit":"20000","other_costs":"15000"})
        updated=self.client.get(f"/trip/{self.trip_id}/workspace?scenario={plans[0]['id']}")
        self.assertIn(b"$1006",updated.data)
        self.assertNotIn(b"$16006",updated.data)

    def test_option_edit_dates_and_validation(self):
        self.add("Eyre Square")
        with furlong.get_db_connection() as db:
            oid=db.execute("SELECT id FROM saved_options").fetchone()[0]
        url=f"/trip/{self.trip_id}/options/{oid}/edit"
        payload={"city":"Galway","name":"Eyre Square","category":"hotel","price":"1100",
                 "start_date":"2027-09-02","end_date":"2027-09-05"}
        self.assertEqual(self.client.post(url,data=payload).status_code,302)
        self.assertIn(b"2027-09-02",self.client.get(f"/trip/{self.trip_id}/options").data)
        payload["end_date"]="2027-09-01"
        self.assertEqual(self.client.post(url,data=payload).status_code,400)

    def test_europe_import_is_idempotent_and_reconciles_totals(self):
        first=self.client.post("/trips/import-europe-2027",follow_redirects=True)
        self.assertEqual(first.status_code,200)
        second=self.client.post("/trips/import-europe-2027",follow_redirects=True)
        self.assertEqual(second.status_code,200)
        with furlong.get_db_connection() as db:
            trips=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchall()
            self.assertEqual(len(trips),1)
            scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=?",(trips[0]["id"],)).fetchall()
            self.assertEqual(len(scenarios),2)
            for plan in scenarios:
                picked=db.execute("""SELECT o.price FROM scenario_choices sc
                    JOIN saved_options o ON o.id=sc.option_id WHERE sc.scenario_id=?""",(plan["id"],)).fetchall()
                total=round(plan["other_costs"]+sum(row["price"] or 0 for row in picked),2)
                self.assertEqual(total,{"S1":18939,"L1":19817}[plan["name"]])
                # Edinburgh is now two independently selected stays:
                # two city nights and one castle night.
                self.assertEqual(len(picked),9)

    def test_edinburgh_apartment_candidates_both_routes_idempotent(self):
        for _ in range(2):
            self.client.post("/trips/import-europe-2027")
        names=("Destiny Scotland – Hill Street Apartments",
               "Wilde Aparthotels – Grassmarket",
               "No.1 Apartments – Edinburgh")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            for variant in ("S1","L1"):
                for name in names:
                    rows=db.execute("""SELECT * FROM saved_options
                        WHERE trip_id=? AND scenario_tag=? AND city='Edinburgh'
                        AND category='hotel' AND name=?""",(trip,variant,name)).fetchall()
                    self.assertEqual(len(rows),1)
                    self.assertIsNone(rows[0]["price"])
                    self.assertEqual((rows[0]["start_date"],rows[0]["end_date"]),
                        ("2027-09-05","2027-09-07"))
                    self.assertIn("To investigate",rows[0]["notes"])

    def test_europe_options_cannot_cross_scenarios(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            s1=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
            l1_option=db.execute("""SELECT id FROM saved_options WHERE trip_id=?
                AND scenario_tag='L1' AND city='Galway' LIMIT 1""",(trip,)).fetchone()["id"]
        page=self.client.get(f"/trip/{trip}/workspace?scenario={s1}")
        self.assertEqual(page.status_code,200)
        self.assertNotIn(f'value="{l1_option}"'.encode(),page.data)
        denied=self.client.post(f"/trip/{trip}/workspace/choose",data={
            "scenario_id":s1,"option_id":l1_option,"city":"Galway","category":"hotel"
        })
        self.assertEqual(denied.status_code,400)

    def test_all_europe_cities_have_alternatives_without_resetting_choices(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            plans=db.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=?",(trip,)).fetchall()
            before={p["name"]:db.execute("SELECT other_costs FROM trip_scenarios WHERE id=?",(p["id"],)).fetchone()[0] for p in plans}
        for plan in plans:
            page=self.client.get(f"/trip/{trip}/workspace?scenario={plan['id']}")
            self.assertEqual(page.status_code,200)
            self.assertIn(b"flight-route-group",page.data)
            self.assertIn(b"flight-option-card",page.data)
        with furlong.get_db_connection() as db:
            for plan in plans:
                for city in ("Dublin","Galway","Edinburgh","Inverness","London"):
                    count=db.execute("""SELECT count(*) FROM saved_options WHERE trip_id=?
                        AND city=? AND category='hotel' AND scenario_tag=?""",
                        (trip,city,plan["name"])).fetchone()[0]
                    self.assertGreaterEqual(count,3,(plan["name"],city))
                self.assertEqual(db.execute("SELECT other_costs FROM trip_scenarios WHERE id=?",
                    (plan["id"],)).fetchone()[0],before[plan["name"]])
            count_before=db.execute("SELECT count(*) FROM saved_options WHERE trip_id=?",(trip,)).fetchone()[0]
        self.client.get(f"/trip/{trip}/workspace")
        with furlong.get_db_connection() as db:
            count_after=db.execute("SELECT count(*) FROM saved_options WHERE trip_id=?",(trip,)).fetchone()[0]
        self.assertEqual(count_before,count_after)

    def test_flight_and_excursion_sections(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            scenario=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
        result=self.client.get(f"/trip/{trip}/workspace?scenario={scenario}")
        self.assertEqual(result.status_code,200)
        self.assertIn(b'Flights & connections',result.data)
        self.assertIn(b'Excursions & experiences',result.data)
        self.assertIn(b'Places to stay',result.data)
        flight=self.client.post(f"/trip/{trip}/flights/add",data={
            "route":"STL - DUB","name":"Test flight via ORD","origin":"STL","destination":"DUB",
            "layovers":"ORD 90m","carrier":"United","price":"4400","scenario_tag":"S1"
        },follow_redirects=True)
        self.assertEqual(flight.status_code,200)
        self.assertIn(b'Test flight via ORD',flight.data)
        excursion=self.client.post(f"/trip/{trip}/excursions/add",data={
            "city":"Galway","name":"Cliffs tour","start_date":"2027-09-04","price":"255"
        },follow_redirects=True)
        self.assertEqual(excursion.status_code,200)
        self.assertIn(b'Cliffs tour',excursion.data)

    def test_corrected_12_otg_forward_dates_and_safe_reconciliation(self):
        legs=[("STL","DUB","2027-09-14"),("SNN","EDI","2027-09-19"),
              ("INV","LHR","2027-09-24"),("LHR","STL","2027-09-27")]
        for origin,destination,expected in legs:
            flight={"origin":origin,"destination":destination,"city":origin+" to "+destination}
            self.assertEqual(furlong.confirmed_four_route_date(flight,"12 OTG"),expected)
        with furlong.get_db_connection() as db:
            db.execute("INSERT INTO trip_scenarios(trip_id,name) VALUES (?,?)",(self.trip_id,"12 OTG"))
            sid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title)
                VALUES (?,?,?,?,?)""",(self.trip_id,sid,"2027-09-16","Dublin","Arrival in Dublin"))
            db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title)
                VALUES (?,?,?,?,?)""",(self.trip_id,sid,"2027-09-28","Departure","Fly home"))
            db.execute("""INSERT INTO saved_options(trip_id,city,name,category,scenario_tag,start_date,end_date)
                VALUES (?,?,?,?,?,?,?)""",
                (self.trip_id,"Dublin","Outdated stay","hotel","12 OTG","2027-09-16","2027-09-18"))
            db.execute("""INSERT INTO saved_options(trip_id,city,name,category,scenario_tag,start_date,end_date)
                VALUES (?,?,?,?,?,?,?)""",
                (self.trip_id,"Dublin","Already quoted stay","hotel","12 OTG","2027-09-15","2027-09-17"))
            furlong.reconcile_12_otg_forward(db,self.trip_id,sid)
            furlong.reconcile_12_otg_forward(db,self.trip_id,sid)
            days=[x[0] for x in db.execute("SELECT day_date FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",(sid,))]
            self.assertEqual(days,["2027-09-15","2027-09-27"])
            rows=[tuple(x) for x in db.execute("SELECT name,start_date,end_date FROM saved_options WHERE trip_id=? ORDER BY id",(self.trip_id,))]
            self.assertIn(("Outdated stay","2027-09-15","2027-09-17"),rows)
            self.assertIn(("Already quoted stay","2027-09-15","2027-09-17"),rows)

    def test_all_four_itinerary_flight_leg_dates(self):
        legs={
            "12 OTG":[("STL","DUB","2027-09-14"),("SNN","EDI","2027-09-19"),
                      ("INV","LHR","2027-09-24"),("LHR","STL","2027-09-27")],
            "14 OTG":[("STL","DUB","2027-09-13"),("SNN","EDI","2027-09-20"),
                      ("INV","LHR","2027-09-25"),("LHR","STL","2027-09-28")],
            "12 OTG Backwards":[("STL","LHR","2027-09-14"),("LHR","INV","2027-09-18"),
                                ("EDI","SNN","2027-09-23"),("DUB","STL","2027-09-27")],
            "14 OTG Backwards":[("STL","LHR","2027-09-13"),("LHR","INV","2027-09-17"),
                                ("EDI","SNN","2027-09-22"),("DUB","STL","2027-09-28")],
        }
        for route_name,flights in legs.items():
            for origin,destination,expected in flights:
                flight={"origin":origin,"destination":destination,"city":origin+" to "+destination}
                self.assertEqual(furlong.confirmed_four_route_date(flight,route_name),expected)

    def test_four_itineraries_have_separate_dated_flights_and_can_delete(self):
        cases=[
            ("12 OTG","STL","DUB","2027-09-14"),
            ("14 OTG","STL","DUB","2027-09-13"),
            ("12 OTG Backwards","STL","LHR","2027-09-14"),
            ("14 OTG Backwards","STL","LHR","2027-09-13"),
        ]
        with furlong.get_db_connection() as db:
            for name,_,_,_ in cases:
                db.execute("INSERT INTO trip_scenarios(trip_id,name) VALUES (?,?)",(self.trip_id,name))
            db.execute("""INSERT INTO saved_options(trip_id,city,name,category,origin,destination)
                VALUES (?,?,?,?,?,?)""",(self.trip_id,"STL to Dublin","Dublin outbound","flight","STL","DUB"))
            shared=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("""INSERT INTO saved_options(trip_id,city,name,category,origin,destination)
                VALUES (?,?,?,?,?,?)""",(self.trip_id,"STL to London","London outbound","flight","STL","LHR"))
            backwards=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for name,origin,dest,expected in cases:
            with furlong.get_db_connection() as db:
                sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",(self.trip_id,name)).fetchone()[0]
            page=self.client.get(f"/trip/{self.trip_id}/workspace?scenario={sid}")
            self.assertEqual(page.status_code,200)
            flight_id=shared if dest=="DUB" else backwards
            with furlong.get_db_connection() as db:
                stored=db.execute("SELECT departure_date FROM flight_option_dates WHERE option_id=? AND scenario_id=?",(flight_id,sid)).fetchone()
                self.assertEqual(stored["departure_date"],expected)
            self.assertIn(expected.encode(),page.data)
        with furlong.get_db_connection() as db:
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='12 OTG'",(self.trip_id,)).fetchone()[0]
        response=self.client.post(f"/trip/{self.trip_id}/options/{shared}/remove",
                                  data={"return_workspace":"1","scenario_id":sid})
        self.assertEqual(response.status_code,302)
        self.assertIn("#flights",response.headers["Location"])
        with furlong.get_db_connection() as db:
            self.assertIsNone(db.execute("SELECT id FROM saved_options WHERE id=?",(shared,)).fetchone())

    def test_editorial_workspace_has_route_switcher_and_city_gallery(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
        res=self.client.get(f"/trip/{trip}/workspace")
        self.assertEqual(res.status_code,200)
        self.assertIn(b'scenario-active',res.data)
        self.assertIn(b'workspace-preferences',res.data)
        self.assertIn(b'atlas-city-gallery',res.data)
        self.assertIn(b'furlong-bear.svg',res.data)
        self.assertNotIn(b'atlas-stamp',res.data)

    def test_hotel_cards_and_independent_itineraries(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            ids={row["name"]:row["id"] for row in db.execute(
                "SELECT id,name FROM trip_scenarios WHERE trip_id=?",(trip,))}
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scenario_itinerary WHERE scenario_id=?",(ids["S1"],)).fetchone()[0],14)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scenario_itinerary WHERE scenario_id=?",(ids["L1"],)).fetchone()[0],16)
            day=db.execute("SELECT id FROM scenario_itinerary WHERE scenario_id=? AND day_date='2027-09-04'",(ids["S1"],)).fetchone()["id"]
        page=self.client.get(f"/trip/{trip}/workspace?scenario={ids['S1']}")
        self.assertIn(b'hotel-comparison-card',page.data)
        self.assertIn(b'Choose this stay',page.data)
        day_page=self.client.get(f"/trip/{trip}/itinerary?scenario={ids['S1']}")
        self.assertIn(b'Cliffs of Moher',day_page.data)
        added=self.client.post(f"/trip/{trip}/itinerary/activity",data={
            "scenario_id":ids["S1"],"itinerary_id":day,"title":"Our own Galway stop",
            "start_time":"15:00"},follow_redirects=True)
        self.assertEqual(added.status_code,200)
        self.assertIn(b'Our own Galway stop',added.data)
        with furlong.get_db_connection() as db:
            activity=db.execute("SELECT id FROM day_activities WHERE title='Our own Galway stop'").fetchone()["id"]
            new_day=db.execute("SELECT id FROM scenario_itinerary WHERE scenario_id=? AND day_date='2027-09-05'",(ids["S1"],)).fetchone()["id"]
        moved=self.client.post(f"/trip/{trip}/itinerary/activity/{activity}/edit",data={
            "scenario_id":ids["S1"],"itinerary_id":new_day,
            "title":"Our moved Galway stop","start_time":"16:00","notes":"Move test"
        },follow_redirects=True)
        self.assertEqual(moved.status_code,200)
        with furlong.get_db_connection() as db:
            item=db.execute("SELECT itinerary_id,title FROM day_activities WHERE id=?",(activity,)).fetchone()
            self.assertEqual(item["itinerary_id"],new_day)
            self.assertEqual(item["title"],"Our moved Galway stop")
        other=self.client.get(f"/trip/{trip}/itinerary?scenario={ids['L1']}")
        self.assertNotIn(b'Our own Galway stop',other.data)
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM day_activities WHERE title='Our moved Galway stop'").fetchone()[0],1)

    def test_allowance_expenses_and_extra_costs(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
        url=f"/trip/{trip}/workspace/expense"
        self.assertEqual(self.client.post(url,data={"scenario_id":sid,"category":"excursion",
            "name":"Tour tickets","amount":"250","included_in_allowance":"1"}).status_code,302)
        self.assertEqual(self.client.post(url,data={"scenario_id":sid,"category":"food",
            "name":"Extra meal","amount":"50","included_in_allowance":"0"}).status_code,302)
        page=self.client.get(f"/trip/{trip}/workspace?scenario={sid}")
        self.assertIn(b'$14164',page.data)  # selected options + $50 extra; legacy flight allowance excluded
        self.assertIn(b'Tour tickets',page.data)
        self.assertIn(b'Extra meal',page.data)

    def test_city_jumps_and_inline_unpriced_quote_edit(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
            option=db.execute("""SELECT * FROM saved_options WHERE trip_id=? AND city='Galway'
                AND category='hotel' AND price IS NULL AND scenario_tag='S1' LIMIT 1""",(trip,)).fetchone()
        page=self.client.get(f"/trip/{trip}/workspace?scenario={sid}")
        self.assertIn(b'href="#hotel-galway"',page.data)
        self.assertIn(b'id="hotel-galway"',page.data)
        self.assertIn(b'Edit details',page.data)
        self.assertIn(f'id="hotel-editor-{option["id"]}"'.encode(),page.data)
        self.assertIn(f'/trip/{trip}/options/{option["id"]}/edit'.encode(),page.data)
        self.assertIn(b'Group quote (USD, all rooms)',page.data)
        self.assertIn(b'Booking link',page.data)
        self.assertIn(b'Save changes',page.data)
        self.assertNotIn(b'Edit other hotel details',page.data)
        changed=self.client.post(f"/trip/{trip}/options/{option['id']}/edit",data={
            "return_workspace":"1","scenario_id":sid,
            "city":"Galway","name":option["name"],"category":"hotel",
            "price":"925.50","start_date":option["start_date"],
            "end_date":option["end_date"],"notes":option["notes"]
        })
        self.assertEqual(changed.status_code,302)
        self.assertIn(f"scenario={sid}#hotel-galway",changed.headers["Location"])
        with furlong.get_db_connection() as db:
            edited=db.execute("SELECT price,scenario_tag FROM saved_options WHERE id=?",(option["id"],)).fetchone()
            self.assertEqual(edited["price"],925.5)
            self.assertEqual(edited["scenario_tag"],"S1")
        refreshed=self.client.get(changed.headers["Location"])
        self.assertIn(b'$926',refreshed.data)

    def test_city_hub_navigation_and_route_isolation(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            plans={row["name"]:row["id"] for row in db.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=?",(trip,))}
        workspace=self.client.get(f"/trip/{trip}/workspace?scenario={plans['S1']}")
        self.assertEqual(workspace.status_code,200)
        self.assertIn(f"/trip/{trip}/city/Galway?scenario={plans['S1']}".encode(),workspace.data)
        page=self.client.get(f"/trip/{trip}/city/Galway?scenario={plans['S1']}")
        self.assertEqual(page.status_code,200)
        route=[b'Dublin',b'Galway',b'Edinburgh',b'Inverness',b'London']
        city_gallery=workspace.data.split(b'class="atlas-city-gallery"')[1].split(b'class="hotel-city-sections"')[0]
        offsets=[city_gallery.index(name) for name in route]
        self.assertEqual(offsets,sorted(offsets))
        self.assertIn(b"Cliffs of Moher",page.data)
        self.assertIn(b"Eyre Square Townhouse",page.data)
        other=self.client.get(f"/trip/{trip}/city/Galway?scenario={plans['L1']}")
        self.assertEqual(other.status_code,200)
        self.assertNotEqual(page.data,other.data)
        self.assertEqual(self.client.get(f"/trip/{trip}/city/Nowhere?scenario={plans['S1']}").status_code,404)
        self.assertNotIn(b'href="/trip/'+str(trip).encode()+b'/city/Transit',page.data)
        self.assertEqual(self.client.get(f"/trip/{trip}/city/Transit?scenario={plans['S1']}").status_code,404)
        itinerary=self.client.get(f"/trip/{trip}/itinerary?scenario={plans['S1']}")
        self.assertIn(b"Galway to Edinburgh",itinerary.data)

    def test_budget_playground_is_read_only_and_scenario_scoped(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            plans={p["name"]:p["id"] for p in db.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=?",(trip,))}
            before=db.execute("SELECT COUNT(*) FROM scenario_choices").fetchone()[0]
            expenses=db.execute("SELECT COUNT(*) FROM scenario_expenses").fetchone()[0]
        s1=self.client.get(f"/trip/{trip}/budget-playground?scenario={plans['S1']}")
        self.assertEqual(s1.status_code,200)
        self.assertIn(b'<h1>Budget</h1>',s1.data)
        self.assertIn(b'Quote needed',s1.data)
        self.assertIn(b'$14,114',s1.data)
        self.assertIn(b'pg-option',s1.data)
        l1=self.client.get(f"/trip/{trip}/budget-playground?scenario={plans['L1']}")
        self.assertEqual(l1.status_code,200)
        self.assertIn(b'$15,317',l1.data)
        self.assertEqual(self.client.get(f"/trip/{trip}/budget-playground?scenario=999999").status_code,404)
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scenario_choices").fetchone()[0],before)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scenario_expenses").fetchone()[0],expenses)

    def test_apartment_candidates_restored_without_staycity(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            for variant in ("S1","L1"):
                for city,name in (("Dublin","Broc House Suites"),("Galway","Canal Court"),
                    ("Edinburgh","Aparthotel Adagio Edinburgh Royal Mile"),
                    ("Inverness","23 Innes Street Apartment"),
                    ("London","Citadines Holborn-Covent Garden")):
                    row=db.execute("""SELECT id,price FROM saved_options WHERE trip_id=? AND city=?
                        AND name=? AND scenario_tag=?""",(trip,city,name,variant)).fetchone()
                    self.assertIsNotNone(row,(variant,city,name))
                    self.assertIsNone(row["price"])
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM saved_options WHERE trip_id=?
                AND name='Staycity Aparthotels Dublin City Centre'""",(trip,)).fetchone()[0],0)
            before=db.execute("SELECT COUNT(*) FROM saved_options WHERE trip_id=?",(trip,)).fetchone()[0]
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM saved_options WHERE trip_id=?",(trip,)).fetchone()[0],before)

    def test_deleted_europe_candidate_stays_deleted(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
            option=db.execute("""SELECT id FROM saved_options WHERE trip_id=? AND city='Galway'
                AND scenario_tag='S1' AND name='Canal Court'""",(trip,)).fetchone()
            self.assertIsNotNone(option)
            oid=option["id"]
        deleted=self.client.post(f"/trip/{trip}/options/{oid}/remove",
            data={"return_workspace":"1","scenario_id":sid})
        self.assertEqual(deleted.status_code,302)
        self.assertIn("#stays",deleted.headers["Location"])
        self.client.get(f"/trip/{trip}/workspace?scenario={sid}")
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            self.assertIsNone(db.execute("SELECT id FROM saved_options WHERE id=?",(oid,)).fetchone())
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM saved_options
                WHERE trip_id=? AND name='Canal Court' AND scenario_tag='S1'""",(trip,)).fetchone()[0],0)
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM saved_options
                WHERE trip_id=? AND name='Canal Court' AND scenario_tag='L1'""",(trip,)).fetchone()[0],1)
        page=self.client.get(f"/trip/{trip}/workspace?scenario={sid}")
        self.assertIn(b'hotel-delete-btn',page.data)

    def test_add_stay_from_workspace_keeps_scenarios_separate(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            ids={row["name"]:row["id"] for row in db.execute(
                "SELECT id,name FROM trip_scenarios WHERE trip_id=?",(trip,))}
        added=self.client.post(f"/trip/{trip}/options/add",data={
            "return_workspace":"1","scenario_id":ids["S1"],"city":"Galway",
            "category":"hotel","name":"New apartment test","price":"999",
            "start_date":"2027-09-03","end_date":"2027-09-05"})
        self.assertEqual(added.status_code,302)
        self.assertIn("scenario="+str(ids["S1"])+"#hotel-galway",added.headers["Location"])
        with furlong.get_db_connection() as db:
            row=db.execute("SELECT scenario_tag FROM saved_options WHERE trip_id=? AND name=?",
                           (trip,"New apartment test")).fetchone()
            self.assertEqual(row["scenario_tag"],"S1")
        self.assertIn(b"New apartment test",self.client.get(
            f"/trip/{trip}/workspace?scenario={ids['S1']}").data)
        self.assertNotIn(b"New apartment test",self.client.get(
            f"/trip/{trip}/workspace?scenario={ids['L1']}").data)
        self.assertEqual(self.client.post(f"/trip/{trip}/options/add",data={
            "return_workspace":"1","scenario_id":999999,"city":"Galway",
            "category":"hotel","name":"Invalid plan"}).status_code,400)

    def test_quick_hotel_quote_does_not_validate_unrelated_fields(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
            hotel=db.execute("""SELECT id FROM saved_options WHERE trip_id=? AND name='Harbour Hotel'
                AND scenario_tag='S1'""",(trip,)).fetchone()
            self.assertIsNotNone(hotel)
            oid=hotel["id"]
            db.execute("UPDATE saved_options SET link='legacy.example',notes=? WHERE id=?",("x"*1100,oid))
        res=self.client.post(f"/trip/{trip}/options/{oid}/quote",
            data={"price":"1250.50","scenario_id":sid})
        self.assertEqual(res.status_code,302)
        self.assertIn("scenario="+str(sid),res.headers["Location"])
        with furlong.get_db_connection() as db:
            row=db.execute("SELECT price,link FROM saved_options WHERE id=?",(oid,)).fetchone()
            self.assertEqual(row["price"],1250.50)
            self.assertEqual(row["link"],"legacy.example")
        self.assertEqual(self.client.post(f"/trip/{trip}/options/{oid}/quote",
            data={"price":"-10","scenario_id":sid}).status_code,400)

    def test_harbour_hotel_url_can_be_updated_without_editing_other_fields(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'",(trip,)).fetchone()["id"]
            oid=db.execute("""SELECT id FROM saved_options WHERE trip_id=? AND
                name='Harbour Hotel' AND scenario_tag='S1'""",(trip,)).fetchone()["id"]
            db.execute("UPDATE saved_options SET notes=? WHERE id=?",("x"*1100,oid))
        url="https://example.com/harbour?"+"ref="+"a"*550
        response=self.client.post(f"/trip/{trip}/options/{oid}/link",
            data={"scenario_id":sid,"link":url})
        self.assertEqual(response.status_code,302)
        with furlong.get_db_connection() as db:
            row=db.execute("SELECT link,notes,price FROM saved_options WHERE id=?",(oid,)).fetchone()
            self.assertEqual(row["link"],url)
            self.assertEqual(len(row["notes"]),1100)
            self.assertIsNone(row["price"])
        self.assertEqual(self.client.post(f"/trip/{trip}/options/{oid}/link",
            data={"scenario_id":sid,"link":"javascript:alert(1)"}).status_code,400)
        self.assertEqual(self.client.post(f"/trip/{trip}/options/{oid}/link",
            data={"scenario_id":999999,"link":"https://example.com"}).status_code,404)

    def test_edinburgh_city_and_castle_stays_are_independent(self):
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()["id"]
            for variant,total in (("S1",1829),("L1",1829)):
                sid=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",
                    (trip,variant)).fetchone()["id"]
                rows=db.execute("""SELECT sc.category,o.name,o.price,o.start_date,o.end_date
                    FROM scenario_choices sc JOIN saved_options o ON o.id=sc.option_id
                    WHERE sc.scenario_id=? AND sc.city='Edinburgh' ORDER BY sc.category""",
                    (sid,)).fetchall()
                self.assertEqual({row["category"] for row in rows},{"hotel","castle"})
                self.assertAlmostEqual(sum(row["price"] for row in rows),total,places=2)
                self.assertEqual({(row["start_date"],row["end_date"]) for row in rows},
                    {("2027-09-05","2027-09-07"),("2027-09-07","2027-09-08")})
        page=self.client.get(f"/trip/{trip}/workspace?scenario={sid}")
        self.assertEqual(page.status_code,200)
        self.assertIn(b"Castle night",page.data)
        self.assertIn(b"Choose castle",page.data) if b"Choose castle" in page.data else self.assertIn(b"Current castle",page.data)
        self.client.post("/trips/import-europe-2027")
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM scenario_choices
                WHERE scenario_id=? AND city='Edinburgh' AND category='castle'""",
                (sid,)).fetchone()[0],1)

    def test_bad_price_rejected(self):
        self.assertEqual(self.add("Bad",price="-5").status_code,400)
        self.assertEqual(self.add("Bad",price="nan").status_code,400)

    def test_bad_external_link_rejected(self):
        res=self.client.post(f"/trip/{self.trip_id}/options/add",data={"city":"Dublin","name":"Unsafe","link":"javascript:alert(1)"})
        self.assertEqual(res.status_code,400)

    def test_other_trip_isolation(self):
        self.add("Galway stay")
        with furlong.get_db_connection() as db:
            db.execute("INSERT INTO trips (name) VALUES ('Other')")
            option_id=db.execute("SELECT id FROM saved_options").fetchone()[0]
            other_id=db.execute("SELECT MAX(id) FROM trips").fetchone()[0]
        self.assertEqual(self.client.post(f"/trip/{other_id}/options/{option_id}/prefer").status_code,404)
        self.assertEqual(self.client.post(f"/trip/{other_id}/options/{option_id}/remove",follow_redirects=True).status_code,404)
        self.assertIn(b"Galway stay",self.client.get(f"/trip/{self.trip_id}/options").data)


if __name__ == "__main__":
    unittest.main()
