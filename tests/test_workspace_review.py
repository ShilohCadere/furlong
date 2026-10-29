"""Workspace review regressions: navigation, alternatives, route dates and totals."""
import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
import app as furlong


class WorkspaceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=furlong.DATABASE
        self.old_testing=furlong.app.config['TESTING']
        furlong.DATABASE=Path(self.tmp.name)/'review.db'
        furlong.app.config['TESTING']=True
        furlong.init_db()
        self.client=furlong.app.test_client()
        self.client.post('/register',data={'username':'reviewer','password':'correct-horse-battery'})
        with furlong.get_db_connection() as db:
            uid=db.execute('SELECT id FROM users').fetchone()[0]
            self.trip=db.execute("INSERT INTO trips(name,destination,user_id) VALUES ('Review trip','Europe',?)",(uid,)).lastrowid
            self.sid=db.execute("INSERT INTO trip_scenarios(trip_id,name,other_costs,food_budget) VALUES (?,'Forward',9999,700)",(self.trip,)).lastrowid
            self.other=db.execute("INSERT INTO trip_scenarios(trip_id,name) VALUES (?,'Backwards')",(self.trip,)).lastrowid
            self.hotel=db.execute("INSERT INTO saved_options(trip_id,city,name,category) VALUES (?,'Edinburgh','City stay','hotel')",(self.trip,)).lastrowid
        self.url=f'/trip/{self.trip}'

    def tearDown(self):
        furlong.DATABASE=self.old_db
        furlong.app.config['TESTING']=self.old_testing
        self.tmp.cleanup()

    def add_experience(self,name,group='Stonehenge',price='100'):
        r=self.client.post(self.url+'/excursions/add',data={'scenario_id':self.sid,'city':'London','name':name,'activity_group':group,'price':price,'start_date':'2027-09-24'})
        self.assertEqual(r.status_code,302)
        self.assertIn(f'scenario={self.sid}',r.location)
        with furlong.get_db_connection() as db:
            return db.execute('SELECT id FROM saved_options WHERE name=?',(name,)).fetchone()[0]

    def choose(self,oid,city):
        return self.client.post(self.url+'/workspace/choose',data={'scenario_id':self.sid,'category':'activity','city':city,'option_id':oid})

    def doc(self,sid=None):
        return BeautifulSoup(self.client.get(self.url+f'/workspace?scenario={sid or self.sid}').data,'html.parser')

    def test_navigation_and_castle_dates(self):
        doc=self.doc()
        self.assertEqual(doc.select_one('.sidebar-city-jumps a')['href'],'#hotel-edinburgh')
        self.assertEqual(doc.select_one('.atlas-city-tile')['href'],self.url+f'/city/Edinburgh?scenario={self.sid}')
        self.assertIsNotNone(doc.select_one('#hotel-edinburgh'))
        self.assertNotIn('Sep 7–8',doc.get_text())
        self.assertFalse(doc.select('input[value="2027-09-07"], input[value="2027-09-08"]'))
        self.assertNotIn('FLIGHT ALLOWANCE',doc.get_text())
        self.assertFalse(doc.select('input[name="other_costs"]'))

    def test_multiple_experiences_and_replacing_only_one_alternative(self):
        a=self.add_experience('Stonehenge coach','Stonehenge','100')
        b=self.add_experience('Stonehenge private','Stonehenge','150')
        c=self.add_experience('Tower admission','Tower of London','50')
        for oid,city in [(a,'London · Stonehenge'),(c,'London · Tower of London'),(b,'London · Stonehenge')]:
            self.assertEqual(self.choose(oid,city).status_code,302)
        with furlong.get_db_connection() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT option_id FROM scenario_choices WHERE scenario_id=?',(self.sid,))},{b,c})
        doc=self.doc()
        self.assertEqual(len(doc.select('#excursions article')),3)
        self.assertEqual(doc.select('.atlas-metrics strong')[2].text,'$900')
        pg=BeautifulSoup(self.client.get(self.url+f'/budget-playground?scenario={self.sid}').data,'html.parser')
        self.assertEqual(pg.select('#pg-total')[0].text,'$900')
        self.choose('','London · Stonehenge')
        with furlong.get_db_connection() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT option_id FROM scenario_choices WHERE scenario_id=?',(self.sid,))],[c])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM saved_options WHERE category='activity'").fetchone()[0],3)

    def test_shared_experience_dates_persist_independently_after_new_login(self):
        oid=self.add_experience('Shared experience')
        with furlong.get_db_connection() as db:
            db.execute('UPDATE saved_options SET scenario_tag=NULL WHERE id=?',(oid,))
        data={'scenario_id':self.sid,'name':'Shared experience','price':'100','start_date':'2027-09-25','notes':'Meet at 9','link':'https://example.com/book'}
        self.assertEqual(self.client.post(self.url+f'/excursions/{oid}/edit',data=data).status_code,302)
        self.assertEqual(self.client.post(self.url+f'/excursions/{oid}/edit',data={**data,'scenario_id':self.other,'start_date':'2027-09-19'}).status_code,302)
        self.client=furlong.app.test_client()
        self.client.post('/login',data={'username':'reviewer','password':'correct-horse-battery'})
        self.assertIn('2027-09-25',self.doc().select_one('#excursions').get_text())
        self.assertIn('2027-09-19',self.doc(self.other).select_one('#excursions').get_text())
        self.assertEqual(self.client.post(self.url+f'/excursions/{oid}/edit',data={**data,'start_date':'invalid'}).status_code,400)
        self.assertEqual(self.client.post(self.url+f'/excursions/{oid}/edit',data={**data,'link':'javascript:alert(1)'}).status_code,400)
        # Clearing a date is intentional and must survive another GET.
        self.client.post(self.url+f'/excursions/{oid}/edit',data={**data,'start_date':''})
        self.assertIn('Date needed',self.doc().select_one('#excursions').get_text())

    def test_legacy_activity_choice_survives_then_can_be_replaced(self):
        with furlong.get_db_connection() as db:
            oid=db.execute("INSERT INTO saved_options(trip_id,city,name,category,price) VALUES (?,'London','Original tour','activity',80)",(self.trip,)).lastrowid
            db.execute("INSERT INTO scenario_choices VALUES (?,'London','activity',?)",(self.sid,oid))
        alt=self.add_experience('Alternate tour','Original tour','90')
        self.assertIn('Selected experience',self.doc().select_one('#excursions').get_text())
        self.choose(alt,'London · Original tour')
        with furlong.get_db_connection() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT option_id FROM scenario_choices WHERE scenario_id=?',(self.sid,))],[alt])

    def test_deletion_and_access_controls(self):
        oid=self.add_experience('Protected tour')
        self.choose(oid,'London · Stonehenge')
        bad={'scenario_id':self.other,'name':'Wrong route','price':'200'}
        self.assertEqual(self.client.post(self.url+f'/excursions/{oid}/edit',data=bad).status_code,400)
        self.assertEqual(self.client.post(self.url+'/excursions/add',data={'scenario_id':99999,'name':'Bad','city':'London'}).status_code,404)
        self.client.post(self.url+f'/options/{oid}/remove',data={'return_workspace':'1','scenario_id':self.sid})
        with furlong.get_db_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scenario_choices').fetchone()[0],0)
        self.client.post('/logout')
        self.client.post('/register',data={'username':'outsider','password':'correct-horse-battery'})
        self.assertEqual(self.client.post(self.url+'/excursions/add',data={'city':'London','name':'Forbidden'}).status_code,404)
        self.assertEqual(self.client.get(self.url+'/workspace').status_code,404)

    def test_card_editors_and_flight_return_to_current_route(self):
        r=self.client.post(self.url+'/flights/add',data={'scenario_id':self.sid,'scenario_tag':'Forward','name':'Flight A','route':'STL → DUB','flight_date':'2027-09-14'})
        self.assertIn(f'scenario={self.sid}#flights',r.location)
        self.add_experience('Experience A')
        doc=self.doc()
        for card in doc.select('#flights article, #excursions article'):
            button=card.select_one('.open-hotel-editor')
            self.assertIsNotNone(button)
            self.assertIsNotNone(card.select_one('#'+button['data-editor']))
        for form in doc.select('form'):
            self.assertFalse(form.select('form'),'Nested forms invalidate browser submission')
        # All dialog controls have a valid, unique destination.
        ids=[node['id'] for node in doc.select('[id]')]
        self.assertEqual(len(ids),len(set(ids)))

    def test_city_identity_follows_name_when_card_order_changes(self):
        with furlong.get_db_connection() as db:
            for city,day in [('Dublin','2027-09-15'),('Galway','2027-09-17'),('London','2027-09-25')]:
                db.execute("INSERT INTO saved_options(trip_id,city,name,category,start_date,end_date) VALUES (?,?,?,'hotel',?,?)",(self.trip,city,city+' stay',day,'2027-09-29'))
        before={a.select_one('strong').text:a['data-city-color'] for a in self.doc().select('.atlas-city-tile')}
        with furlong.get_db_connection() as db:
            db.execute("UPDATE saved_options SET start_date='2027-09-13' WHERE city='London'")
        after={a.select_one('strong').text:a['data-city-color'] for a in self.doc().select('.atlas-city-tile')}
        self.assertEqual(before,after)
        self.assertEqual(after,{'Dublin':'dublin','Galway':'galway','London':'london','Edinburgh':'edinburgh'})
        doc=self.doc()
        self.assertEqual(doc.select_one('#hotel-edinburgh')['data-city-color'],'edinburgh')
        self.assertEqual(doc.select_one('.sidebar-city-jumps a[href="#hotel-edinburgh"]')['data-city-color'],'edinburgh')
        city=BeautifulSoup(self.client.get(self.url+f'/city/Edinburgh?scenario={self.sid}').data,'html.parser')
        self.assertEqual(city.body['data-city-color'],'edinburgh')

    def test_flight_and_ground_gradients_follow_endpoint_direction(self):
        for sid,start,end in [(self.sid,'SNN','EDI'),(self.other,'EDI','SNN')]:
            response=self.client.post(self.url+'/flights/add',data={'scenario_id':sid,'name':'Flight '+start,'route':start+' → '+end,'origin':start,'destination':end})
            self.assertEqual(response.status_code,302)
        with furlong.get_db_connection() as db:
            db.execute("INSERT INTO saved_options(trip_id,city,name,category) VALUES (?,'Scotland rail','ScotRail Inverness to Edinburgh — official tickets','transport')",(self.trip,))
        doc=self.doc()
        cards=doc.select('.flight-option-card')
        self.assertEqual({(c['data-route-from'],c['data-route-to']) for c in cards},{('galway','edinburgh'),('edinburgh','galway')})
        rail=doc.select_one('#ground .atlas-choice')
        self.assertEqual((rail['data-route-from'],rail['data-route-to']),('inverness','edinburgh'))
        options=BeautifulSoup(self.client.get(self.url+'/options').data,'html.parser')
        self.assertEqual(len(options.select('.option-card[data-route-from]')),3)
        pg=BeautifulSoup(self.client.get(self.url+f'/budget-playground?scenario={self.sid}').data,'html.parser')
        self.assertTrue(pg.select('.playground-option[data-route-from]'))

    def test_excursion_and_itinerary_use_the_destination_identity(self):
        self.add_experience('London experience')
        with furlong.get_db_connection() as db:
            db.execute("INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title) VALUES (?,?,'2027-09-24','London','Explore London')",(self.trip,self.sid))
        doc=self.doc()
        self.assertEqual(doc.select_one('.experience-group')['data-city-color'],'london')
        itinerary=BeautifulSoup(self.client.get(self.url+f'/itinerary?scenario={self.sid}').data,'html.parser')
        self.assertEqual(itinerary.select_one('.itinerary-story-day')['data-city-color'],'london')
