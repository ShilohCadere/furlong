"""Regression tests for Saved Options. Run: python -m unittest discover -s tests -v"""
import tempfile
import unittest
from pathlib import Path

import app as furlong


class SavedOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_database = furlong.DATABASE
        furlong.DATABASE = Path(self.tmp.name) / "test.db"
        furlong.init_db()
        self.client = furlong.app.test_client()
        with furlong.get_db_connection() as conn:
            conn.execute("INSERT INTO trips (name,destination) VALUES (?,?)", ("Test trip", "Ireland"))
            self.trip_id = conn.execute("SELECT id FROM trips").fetchone()[0]

    def tearDown(self):
        furlong.DATABASE = self.old_database
        self.tmp.cleanup()

    def add(self, name, city="Galway", price="400", category="hotel"):
        return self.client.post(
            f"/trip/{self.trip_id}/options/add",
            data={"city":city,"name":name,"price":price,"category":category},
            follow_redirects=True
        )

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
        self.assertIn(b"$16006",updated.data)

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
                self.assertEqual(len(picked),8)

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
            self.assertIn(b"choices",page.data)
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
        self.assertEqual(self.client.post(f"/trip/{other_id}/options/{option_id}/remove",follow_redirects=True).status_code,200)
        self.assertIn(b"Galway stay",self.client.get(f"/trip/{self.trip_id}/options").data)


if __name__ == "__main__":
    unittest.main()
