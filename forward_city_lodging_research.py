"""Forward-route 2027 city lodging research (fetched October 27, 2026).

Hotels: two times the searched total for one room/two adults; simultaneous
availability of two rooms has not been verified. Rentals: searched total for
four adults with two-bedroom filter; inspect actual unit configuration.
No existing options or selections are changed. Dates in user's local scenario
database are authoritative; mismatches skip a row rather than misdate it.
"""
# (city, arrival, checkout, lodging type, name, USD four-person estimate, Expedia listing id)
SHARED=[
 ("Inverness","2027-09-23","2027-09-25","rental","Waverley Inn Apartments",454,"60534060"),
 ("Inverness","2027-09-23","2027-09-25","rental","City Apartment No.3 May Court",563,"70034060"),
 ("Inverness","2027-09-23","2027-09-25","rental","City Apartment No.1 May Court",563,"102552343"),
 ("Inverness","2027-09-23","2027-09-25","rental","Heart of Inverness Modern Apartment",749,"75814905"),
 ("Inverness","2027-09-23","2027-09-25","rental","Stunning Spacious Apartment on River Ness",815,"66708249"),
 ("London","2027-09-25","2027-09-28","rental","South Kensington Apartments",562,"69712519"),
 ("London","2027-09-25","2027-09-28","rental","Stylish 2 Bedroom Flat Shepherd's Bush",565,"136693067"),
 ("London","2027-09-25","2027-09-28","rental","Avari Apartments Hatton Collection",693,"92330920"),
 ("London","2027-09-25","2027-09-28","rental","Grand Plaza Serviced Apartments",705,"914263"),
 ("London","2027-09-25","2027-09-28","rental","Heinze Building by City Living London",712,"74798995"),
 ("London","2027-09-25","2027-09-28","hotel","Vancouver Studios (two-room estimate)",1280,"520898"),
 ("London","2027-09-25","2027-09-28","hotel","Native Hyde Park (two-room estimate)",1338,"5297150"),
]
BY_PLAN={
 "12 OTG":[
 ("Galway","2027-09-18","2027-09-20","rental","Wildlands (check location and bedroom type)",436,"102676107"),
 ("Galway","2027-09-18","2027-09-20","rental","Ower Retreat (check location)",1464,"131975631"),
 ("Galway","2027-09-18","2027-09-20","rental","Gort Na Coiribe Two Bedroom",2282,"119843887"),
 ("Edinburgh","2027-09-20","2027-09-22","hotel","Edinburgh City Hotel (two-room estimate)",604,"128424906"),
 ("Edinburgh","2027-09-20","2027-09-22","hotel","Premier Inn Edinburgh Leith Waterfront (two-room estimate)",740,"11785420"),
 ("Edinburgh","2027-09-20","2027-09-22","rental","Stylish George Street Apartment",419,"73637223"),
 ],
 "14 OTG":[
 ("Galway","2027-09-17","2027-09-20","rental","Robins Roost 2 (outside Galway city)",548,"114094769"),
 ("Galway","2027-09-17","2027-09-20","rental","Mayfly Cottage (outside Galway city)",783,"133867511"),
 ("Galway","2027-09-17","2027-09-20","rental","22 Town Place",1100,"93531718"),
 ("Galway","2027-09-17","2027-09-20","rental","Ower Retreat (check location)",2141,"131975631"),
 ("Edinburgh","2027-09-20","2027-09-22","rental","Stylish George Street Apartment",419,"73637223"),
 ("Edinburgh","2027-09-20","2027-09-22","hotel","Morrison Central ApartHotel (two-room estimate)",696,"69639796"),
 ]
}
def seed_forward_city_lodging(db,trip_id):
    known={r["name"] for r in db.execute("SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for public,legacy in (("12 OTG","S1"),("14 OTG","L1")):
        tag=public if public in known else legacy
        if tag not in known:continue
        for city,start,end,kind,name,price,hid in SHARED+BY_PLAN[public]:
            dates=[r["day_date"] for r in db.execute("""SELECT d.day_date FROM scenario_itinerary d
                JOIN trip_scenarios s ON s.id=d.scenario_id
                WHERE d.trip_id=? AND s.name=? AND d.city=? ORDER BY d.day_date""",(trip_id,tag,city))]
            if not dates or dates[0]!=start:continue
            label=name+(" — rental, verify 2 bedrooms" if kind=="rental" else "")
            if db.execute("""SELECT 1 FROM saved_options WHERE trip_id=? AND city=?
                AND name=? AND category='hotel' AND scenario_tag=?""",
                (trip_id,city,label,tag)).fetchone():continue
            if db.execute("""SELECT 1 FROM excluded_seed_options WHERE trip_id=? AND city=?
                AND name=? AND category='hotel' AND scenario_tag=?""",
                (trip_id,city,label,tag)).fetchone():continue
            link=f"https://www.expedia.com/.h{hid}.Hotel-Information?chkin={start}&chkout={end}&rm1=a{4 if kind=='rental' else 2}"
            db.execute("""INSERT INTO saved_options
              (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
              VALUES (?,?,?,'hotel',?,?,'',?,?,?)""",(trip_id,city,label,price,link,start,end,tag))
