"""Deadeye Protective Services - free contract lead finder.
Pulls security-guard solicitations in Texas from SAM.gov, plus any Google
Alerts RSS feeds you add, dedupes, and emails a digest."""
import os, json, smtplib, ssl, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.message import EmailMessage

SAM_KEY = os.environ["SAM_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
SEND_TO = os.environ.get("SEND_TO", GMAIL_USER)

NAICS = ["561612", "561611", "561621"]  # guards/patrol, investigation/guard, security systems
STATE = "TX"
KEYWORDS = ["security guard", "guard services", "armed guard", "unarmed guard",
            "security services", "patrol", "protective services", "security officer"]
# Paste Google Alerts RSS feed URLs here (alerts at google.com/alerts -> "Deliver to: RSS feed")
RSS_FEEDS = []

SEEN_FILE = "seen.json"
seen = set(json.load(open(SEEN_FILE))) if os.path.exists(SEEN_FILE) else set()
leads = []

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "deadeye-lead-agent"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

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
            leads.append(f"[Federal] {o.get('title')}\n  Agency: {o.get('fullParentPathName')}\n"
                         f"  Posted: {o.get('postedDate')}  Due: {o.get('responseDeadLine')}\n"
                         f"  {o.get('uiLink')}")

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
                leads.append(f"[Web] {title}\n  {link}")

sam_leads(); rss_leads()
json.dump(sorted(seen), open(SEEN_FILE, "w"))

if leads:
    msg = EmailMessage()
    msg["Subject"] = f"Deadeye: {len(leads)} new contract leads"
    msg["From"] = GMAIL_USER; msg["To"] = SEND_TO
    msg.set_content("\n\n".join(leads))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD); s.send_message(msg)
print(f"{len(leads)} new leads")
