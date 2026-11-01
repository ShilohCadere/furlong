"""Add unpriced forward-route lodging matches using the saved reverse itinerary."""
import re
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def property_name(name):
    for suffix in (" — rental, verify 2 bedrooms", " — 2-room planning estimate",
                   " — 2-room estimate", " (two-room estimate)"):
        name = name.replace(suffix, "")
    return " ".join(name.casefold().split())


def listing_id(link):
    match = re.search(r"\.h(\d+)\.Hotel-Information", link or "")
    return match.group(1) if match else None


def stay_dates(db, trip_id, scenario_id, city, tag):
    days = db.execute("""SELECT day_date,title FROM scenario_itinerary
        WHERE trip_id=? AND scenario_id=? AND city=? ORDER BY day_date""",
        (trip_id, scenario_id, city)).fetchall()
    if not days:
        return None
    try:
        dates = [date.fromisoformat(row["day_date"]) for row in days]
    except ValueError:
        return None
    if any(b - a != timedelta(days=1) for a, b in zip(dates, dates[1:])):
        return None
    start, end = dates[0], dates[-1] + timedelta(days=1)
    if city == "Edinburgh":
        castles = db.execute("""SELECT start_date FROM saved_options WHERE trip_id=?
            AND city=? AND category='castle' AND scenario_tag=?""",
            (trip_id, city, tag)).fetchall()
        boundaries = [r["start_date"] for r in castles if r["start_date"]
                      and start.isoformat() < r["start_date"] < end.isoformat()]
        boundaries += [r["day_date"] for r in days
                       if "castle" in (r["title"] or "").casefold()
                       and any(word in (r["title"] or "").casefold()
                               for word in ("stay", "overnight", "melville", "dalhousie"))
                       and start.isoformat() < r["day_date"] < end.isoformat()]
        if not boundaries:
            # A separate city stay must not accidentally include the castle night.
            return None
        end = date.fromisoformat(min(boundaries))
    return start.isoformat(), end.isoformat()


def booking_link(link, name, city, start, end, rental):
    parts = urlsplit(link or "")
    host = (parts.hostname or "").lower()
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if host == "expedia.com" or host.endswith(".expedia.com"):
        query = {k: v for k, v in query.items()
                 if not re.fullmatch(r"rm\d+", k)
                 and k not in ("chkin", "chkout", "startDate", "endDate")}
        query.update(chkin=start, chkout=end, rm1="a4" if rental else "a2")
        if not rental:
            query["rm2"] = "a2"
    elif host == "booking.com" or host.endswith(".booking.com"):
        query = {k: v for k, v in query.items()
                 if not k.startswith(("checkin", "checkout", "group_children", "age"))}
        query.update(checkin=start, checkout=end, group_adults="4",
                     group_children="0", no_rooms="1" if rental else "2")
    elif host == "airbnb.com" or host.endswith(".airbnb.com"):
        query.update(check_in=start, check_out=end, adults="4", children="0", infants="0")
    else:
        # Official home pages cannot reliably preselect dates. Use an explicitly
        # dated property-name search rather than inventing supplier parameters.
        parts = urlsplit("https://www.booking.com/searchresults.html")
        query = dict(ss=name + ", " + city, checkin=start, checkout=end,
                     group_adults="4", group_children="0", no_rooms="1" if rental else "2")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def add_backward_lodging(db, trip_id):
    routes = db.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=?", (trip_id,)).fetchall()
    for route in routes:
        tag = route["name"]
        if tag in ("12 OTG Backwards", "Backwards 12 OTG"):
            source_tags, public = ("12 OTG", "S1"), "12 OTG"
        elif tag in ("14 OTG Backwards", "Backwards 14 OTG"):
            source_tags, public = ("14 OTG", "L1"), "14 OTG"
        else:
            continue
        sources = [dict(r) for r in db.execute("""SELECT city,name,link FROM saved_options
            WHERE trip_id=? AND category='hotel' AND scenario_tag IN (?,?) ORDER BY id""",
            (trip_id, *source_tags))]
        sources += [dict(city=city, name=name, link=f"https://www.expedia.com/.h{hid}.Hotel-Information",
                         rental=kind == "rental")
                    for scope, city, kind, name, hid in CANDIDATES if scope in ("shared", public)]
        for candidate in sources:
            city, name, link = candidate["city"], candidate["name"], candidate["link"]
            if " + " in name and "castle" in name.casefold():
                continue
            dates = stay_dates(db, trip_id, route["id"], city, tag)
            if not dates:
                continue
            key, hid = property_name(name), listing_id(link)
            existing = db.execute("""SELECT name,link FROM saved_options WHERE trip_id=?
                AND city=? AND category='hotel' AND (scenario_tag=? OR scenario_tag IS NULL)""",
                (trip_id, city, tag)).fetchall()
            if any(property_name(r["name"]) == key or (hid and listing_id(r["link"]) == hid)
                   for r in existing):
                continue
            excluded = db.execute("""SELECT name FROM excluded_seed_options WHERE trip_id=?
                AND city=? AND category='hotel' AND scenario_tag IN (?, '')""",
                (trip_id, city, tag)).fetchall()
            if any(property_name(r["name"]) == key for r in excluded):
                continue
            rental = candidate.get("rental", any(word in name.casefold()
                         for word in ("rental", "apartment", "cottage", "retreat", "town place", "wildlands")))
            title = name.replace(" (two-room estimate)", "")
            if candidate.get("rental") and " — rental" not in title:
                title += " — rental, verify 2 bedrooms"
            notes = ("Quote needed for this route; total to be verified by traveler. "
                     + ("Four adults; verify two private bedrooms and unit layout."
                        if rental else "Four adults in two rooms, two adults per room."))
            url = booking_link(link, title, city, *dates, rental)
            if "searchresults.html" in url:
                notes += " Link opens a dated property-name search; select this exact property."
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
                VALUES (?,?,?,'hotel',NULL,?,?,?,?,?)""",
                (trip_id, city, title, url, notes, *dates, tag))


# Existing forward-route researched listings; no prices are transferred.
CANDIDATES = [('shared', 'Inverness', 'rental', 'Waverley Inn Apartments', '60534060'),
 ('shared', 'Inverness', 'rental', 'City Apartment No.3 May Court', '70034060'),
 ('shared', 'Inverness', 'rental', 'City Apartment No.1 May Court', '102552343'),
 ('shared', 'Inverness', 'rental', 'Heart of Inverness Modern Apartment', '75814905'),
 ('shared', 'Inverness', 'rental', 'Stunning Spacious Apartment on River Ness', '66708249'),
 ('shared', 'London', 'rental', 'South Kensington Apartments', '69712519'),
 ('shared', 'London', 'rental', "Stylish 2 Bedroom Flat Shepherd's Bush", '136693067'),
 ('shared', 'London', 'rental', 'Avari Apartments Hatton Collection', '92330920'),
 ('shared', 'London', 'rental', 'Grand Plaza Serviced Apartments', '914263'),
 ('shared', 'London', 'rental', 'Heinze Building by City Living London', '74798995'),
 ('shared', 'London', 'hotel', 'Vancouver Studios (two-room estimate)', '520898'),
 ('shared', 'London', 'hotel', 'Native Hyde Park (two-room estimate)', '5297150'),
 ('12 OTG', 'Galway', 'rental', 'Wildlands (check location and bedroom type)', '102676107'),
 ('12 OTG', 'Galway', 'rental', 'Ower Retreat (check location)', '131975631'),
 ('12 OTG', 'Galway', 'rental', 'Gort Na Coiribe Two Bedroom', '119843887'),
 ('12 OTG', 'Edinburgh', 'hotel', 'Edinburgh City Hotel (two-room estimate)', '128424906'),
 ('12 OTG',
  'Edinburgh',
  'hotel',
  'Premier Inn Edinburgh Leith Waterfront (two-room estimate)',
  '11785420'),
 ('12 OTG', 'Edinburgh', 'rental', 'Stylish George Street Apartment', '73637223'),
 ('14 OTG', 'Galway', 'rental', 'Robins Roost 2 (outside Galway city)', '114094769'),
 ('14 OTG', 'Galway', 'rental', 'Mayfly Cottage (outside Galway city)', '133867511'),
 ('14 OTG', 'Galway', 'rental', '22 Town Place', '93531718'),
 ('14 OTG', 'Galway', 'rental', 'Ower Retreat (check location)', '131975631'),
 ('14 OTG', 'Edinburgh', 'rental', 'Stylish George Street Apartment', '73637223'),
 ('14 OTG', 'Edinburgh', 'hotel', 'Morrison Central ApartHotel (two-room estimate)', '69639796'),
 ('shared', 'Inverness', 'hotel', 'Aye Stay', '36969201'),
 ('shared', 'Inverness', 'hotel', 'Ballifeary Guest House', '4468662')]
