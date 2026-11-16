"""Deadeye Protective Services - free contract lead finder (Texas, Houston-first)."""
import os, json, smtplib, ssl, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.message import EmailMessage

SAM_KEY = os.environ["SAM_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
SEND_TO = os.environ.get("SEND_TO", GMAIL_USER)

NAICS = ["561612", "561611", "561621"]
STATE = "TX"
KEYWORDS = ["security guard", "guard services", "armed guard", "unarmed guard",
            "security services", "patrol", "protective services", "security officer"]
RSS_FEEDS = []

HOUSTON_AREA = ["houston", "pasadena", "sugar land", "katy", "the woodlands", "conroe",
    "pearland", "baytown", "league city", "galveston", "spring", "humble", "cypress",
    "missouri city", "stafford", "richmond", "rosenberg", "tomball", "friendswood",
    "webster", "channelview", "texas city", "la porte", "deer park", "kingwood",
    "clear lake", "angleton", "lake jackson", "huntsville"]
HOUSTON_ZIP_PREFIXES = ("770", "771", "772", "773", "774", "775")

SEEN_FILE = "seen.json"
seen = set(json.load(open(SEEN_FILE))) if os.path.exists(SEEN_FILE) else set()
leads = []  # (is_houston, text)

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "deadeye-lead-agent"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def where(o):
    pop = o.get("placeOfPerformance") or {}
    city = ((pop.get("city") or {}).get("name") or "")
    zipc = str(pop.get("zip") or "")
    if not city:
        oa = o.get("officeAddress") or {}
        city = oa.get("city") or ""
        zipc = zipc or str(oa.get("zipcode") or "")
    return city, zipc

def is_houston(city, zipc):
    return city.lower() in HOUSTON_AREA or zipc.startswith(HOUSTON_ZIP_PREFIXES)

def sam_leads():
    end = datetime.now()
    start = end - timedelta(days=7)
    for code in NAICS:
        q = urllib.parse.urlencode({
            "api_key": SAM_KEY, "limit": 100, "ncode": code, "state": STATE,
            "postedFrom": start.strftime("%m/%d/%Y"), "postedTo": end.strftime("%m/%d/%Y"),
        })
        try:
            data = json.loads(fetch("https://api.sam.gov/opportunities/v2/search?" + q))
        except Exception as e:
            print("SAM error", code, e); continue
        for o in data.get("opportunitiesData", []):
            uid = "sam:" + str(o.get("noticeId"))
            if uid in seen: continue
            seen.add(uid)
            city, zipc = where(o)
            h = is_houston(city, zipc)
            tag = "HOUSTON AREA" if h else "TEXAS"
            leads.append((h, f"[{tag}] {o.get('title')}\n  Location: {city or 'n/a'}, TX {zipc}\n"
                         f"  Agency: {o.get('fullParentPathName')}\n"
                         f"  Posted: {o.get('postedDate')}  Due: {o.get('responseDeadLine')}\n"
                         f"  {o.get('uiLink')}"))

def rss_leads():
    for feed in RSS_FEEDS:
        try:
            root = ET.fromstring(fetch(feed))
        except Exception as e:
            print("RSS error", feed, e); continue
        for item in root.iter():
            if item.tag.endswith("entry") or item.tag == "item":
                title = link = ""
                for c in item:
                    if c.tag.endswith("title"): title = "".join(c.itertext())
                    if c.tag.endswith("link"): link = c.get("href") or (c.text or "")
                text = title.lower()
                if link in seen or not any(k in text for k in KEYWORDS): continue
                seen.add(link)
                h = any(c in text for c in HOUSTON_AREA)
                leads.append((h, f"[{'HOUSTON AREA' if h else 'WEB'}] {title}\n  {link}"))

sam_leads(); rss_leads()
json.dump(sorted(seen), open(SEEN_FILE, "w"))

if leads:
    leads.sort(key=lambda x: not x[0])  # Houston first
    n_h = sum(1 for h, _ in leads if h)
    msg = EmailMessage()
    msg["Subject"] = f"Deadeye: {len(leads)} new leads ({n_h} Houston area)"
    msg["From"] = GMAIL_USER; msg["To"] = SEND_TO
    msg.set_content("\n\n".join(t for _, t in leads))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD); s.send_message(msg)
print(f"{len(leads)} new leads")
