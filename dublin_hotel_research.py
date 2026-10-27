"""Dublin September 2027 hotel research, 4 adults in two separate rooms.

Prices: twice Expedia's 2026-10-27 total for ONE room with two adults
over the requested dates, not a verified simultaneous two-room quote.
Do not replace user edits, notes, preferences, or pre-existing choices.
"""
# Five comparables per scenario, preserving independently editable options.
# Date ranges for forward routes are working itinerary assumptions; check
# against local database dates before using any as a final reservation quote.
PLANS = {
 "12 OTG": ("2027-09-16","2027-09-18",{
  "Premier Inn Dublin - Jervis Street":418,"Premier Inn Dublin City Centre (Temple Bar)":474,
  "Keavans Port":492,"Beckett Locke":510,"Maldron Hotel Pearse Street":603}),
 "14 OTG": ("2027-09-14","2027-09-17",{
  "Premier Inn Dublin - Jervis Street":549,"Premier Inn Dublin City Centre (Temple Bar)":611,
  "Keavans Port":784,"Beckett Locke":670,"Maldron Hotel Pearse Street":813}),
 "Backwards 12 OTG": ("2027-09-26","2027-09-28",{
  "Premier Inn Dublin - Jervis Street":296,"Premier Inn Dublin City Centre (Temple Bar)":313,
  "Keavans Port":319,"Beckett Locke":332,"Maldron Hotel Pearse Street":375}),
 "Backwards 14 OTG": ("2027-09-25","2027-09-28",{
  "Premier Inn Dublin - Jervis Street":516,"Premier Inn Dublin City Centre (Temple Bar)":639,
  "Keavans Port":606,"Beckett Locke":672,"Maldron Hotel Pearse Street":683})
}
LINKS = {
 "Premier Inn Dublin - Jervis Street":"https://www.premierinn.com/",
 "Premier Inn Dublin City Centre (Temple Bar)":"https://www.premierinn.com/gb/en/hotels/republic-of-ireland/dublin/dublin/dublin-city-centre-temple-bar.html",
 "Keavans Port":"https://www.jdwetherspoon.com/pubs/keavans-port-dublin/",
 "Beckett Locke":"https://www.lockeliving.com/en/dublin/beckett-locke",
 "Maldron Hotel Pearse Street":"https://www.maldronhotels.com/pearse-street/"
}

def seed_dublin_hotel_research(db,trip_id):
    known={r["name"] for r in db.execute("SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for scenario,(checkin,checkout,prices) in PLANS.items():
        actual=scenario if scenario in known else {"12 OTG":"S1","14 OTG":"L1"}.get(scenario,scenario)
        if actual not in known: continue
        # Do not insert research with dates that disagree with the actual
        # itinerary: local Furlong database is authoritative.
        days=[r["day_date"] for r in db.execute("""SELECT day_date FROM scenario_itinerary d
            JOIN trip_scenarios s ON s.id=d.scenario_id
            WHERE d.trip_id=? AND s.name=? AND d.city='Dublin'
            ORDER BY day_date""",(trip_id,actual)).fetchall()]
        if not days or days[0] != checkin: continue
        for name,one_room_price in prices.items():
            tagged_name=name+" — 2-room planning estimate"
            if db.execute("""SELECT 1 FROM saved_options WHERE trip_id=? AND city='Dublin'
              AND category='hotel' AND name=? AND scenario_tag=?""",
              (trip_id,tagged_name,actual)).fetchone():continue
            if db.execute("""SELECT 1 FROM excluded_seed_options WHERE trip_id=?
              AND city='Dublin' AND category='hotel' AND name=? AND scenario_tag=?""",
              (trip_id,tagged_name,actual)).fetchone():continue
            db.execute("""INSERT INTO saved_options
               (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
               VALUES (?,'Dublin',?,'hotel',?,?,'',?,?,?)""",
               (trip_id,tagged_name,2*one_room_price,LINKS[name],checkin,checkout,actual))
