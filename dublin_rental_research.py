"""Date-scoped Dublin vacation rental research for Europe 2027.
Prices are Expedia search totals for 4 adults with a two-bedroom filter,
retrieved 2026-10-27. The listing response did not provide confirmed unit
bedroom count; users must verify two separate bedrooms before booking.
Preserve existing user choices and notes. Do not automatically select.
"""
PLANS = {
 "12 OTG":("2027-09-16","2027-09-18",[
  ("Broc House Suites",579,"12848538"),
  ("Delightful Howth Village apartment",632,"106782417"),
  ("Cosy and Modern flat in Dublin City",1443,"121662052"),
 ]),
 "14 OTG":("2027-09-14","2027-09-17",[
  ("Broc House Suites",769,"12848538"),
  ("Grafton Street District Apartments",984,"109638223"),
  ("Parnell Square Apartments",995,"7725621"),
  ("St. Stephen's Green Apartments",1007,"21498559"),
  ("Saint Patrick's District Apartments",1067,"109803895"),
 ]),
 "Backwards 12 OTG":("2027-09-26","2027-09-28",[
  ("Delightful 2-bedroom apartment in Dublin",487,"122698154"),
  ("Broc House Suites",536,"12848538"),
  ("Howth townhouse apartment 2",571,"132031885"),
  ("Modern Central Dublin Apartment Near Bolton Square",875,"133858570"),
 ]),
 "Backwards 14 OTG":("2027-09-25","2027-09-28",[
  ("Delightful 2-bedroom apartment in Dublin",756,"122698154"),
  ("Broc House Suites",760,"12848538"),
  ("Parnell Square Apartments",962,"7725621"),
  ("Grafton Street District Apartments",962,"109638223"),
  ("St. Stephen's Green Apartments",1000,"21498559"),
 ]),
}

def seed_dublin_rentals(db,trip_id):
    scenarios={r["name"] for r in db.execute("SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for scenario,(start,end,options) in PLANS.items():
        tag=scenario if scenario in scenarios else {"12 OTG":"S1","14 OTG":"L1"}.get(scenario,scenario)
        if tag not in scenarios: continue
        days=[r["day_date"] for r in db.execute("""SELECT d.day_date FROM scenario_itinerary d
          JOIN trip_scenarios s ON s.id=d.scenario_id
          WHERE d.trip_id=? AND s.name=? AND d.city='Dublin'
          ORDER BY d.day_date""",(trip_id,tag))]
        if not days or days[0]!=start: continue
        for label,price,hid in options:
            title=label+" — vacation rental (verify 2 bedrooms)"
            if db.execute("""SELECT 1 FROM saved_options
                 WHERE trip_id=? AND city='Dublin' AND category='hotel'
                   AND scenario_tag=? AND name=?""",(trip_id,tag,title)).fetchone():continue
            if db.execute("""SELECT 1 FROM excluded_seed_options
                 WHERE trip_id=? AND city='Dublin' AND category='hotel'
                   AND scenario_tag=? AND name=?""",(trip_id,tag,title)).fetchone():continue
            url=("https://www.expedia.com/.h"+hid+".Hotel-Information?chkin="
                 +start+"&chkout="+end+"&rm1=a4")
            db.execute("""INSERT INTO saved_options
                 (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
                 VALUES (?,'Dublin',?,'hotel',?,?,'',?,?,?)""",
                 (trip_id,title,price,url,start,end,tag))
