"""Work-with-us inquiries: advertising, sponsorship and partnerships.

POST /api/inquiry (form on /work-with-us/) -> validated, rate-limited by nginx,
stored in $GBS_DATA_DIR/members.db (table inquiries) with a reference like
GU-261110-7F3K, routed to an owner inbox by type, and e-mailed there when SMTP
is configured (SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_FROM). Nothing is
sent to the person who asked (no auto-replies an attacker could aim at others).

Coordinate replies from the droplet:
    gbs inquiries                  list open inquiries, oldest first
    gbs inquiries GU-... replied   set status (new|replied|booked|declined|spam)
"""
from __future__ import annotations

import os
import re
import secrets
import smtplib
import time
from email.message import EmailMessage

KINDS = {
    "display": ("Display or in-feed ads", "advertising"),
    "preroll": ("Video pre-roll", "advertising"),
    "sponsor_read": ("On-air sponsor read", "advertising"),
    "show": ("Show sponsorship", "advertising"),
    "newsletter": ("Newsletter sponsorship", "advertising"),
    "partnership": ("Content or data partnership", "general"),
    "other": ("Something else", "general"),
}
BUDGETS = ["Under CA$500", "CA$500-2,000", "CA$2,000-10,000", "Over CA$10,000", "Not sure yet"]
STATUSES = ("new", "replied", "booked", "declined", "spam")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[a-z]{2,}$", re.I)


def _table(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS inquiries(
        ref TEXT PRIMARY KEY, ts REAL, kind TEXT, org TEXT, name TEXT, email TEXT, website TEXT,
        budget TEXT, start TEXT, message TEXT, route TEXT, status TEXT DEFAULT 'new', updated REAL)""")


def validate(f: dict) -> tuple[dict | None, str]:
    if f.get("company_url"):                       # honeypot field, hidden from people
        return None, "spam"
    g = {k: (f.get(k) or "").strip() for k in ("kind", "org", "name", "email", "website", "budget", "start", "message")}
    if g["kind"] not in KINDS:
        return None, "kind"
    if not g["name"] or len(g["name"]) > 120 or not g["org"] or len(g["org"]) > 160:
        return None, "name"
    if not _EMAIL.match(g["email"]):
        return None, "email"
    if g["budget"] and g["budget"] not in BUDGETS:
        return None, "budget"
    if len(g["message"]) < 20 or len(g["message"]) > 4000:
        return None, "message"
    if g["website"] and not re.match(r"^https?://[^\s]{3,300}$", g["website"]):
        return None, "website"
    if re.search(r"https?://", g["message"]) and len(re.findall(r"https?://", g["message"])) > 3:
        return None, "spam"
    g["start"] = g["start"][:40]
    return g, ""


def save(conn, g: dict, site: dict) -> dict:
    ref = time.strftime("GU-%y%m%d-") + secrets.token_hex(2).upper()
    route = site["emails"].get(KINDS[g["kind"]][1], site["emails"]["general"]) + "@" + site.get("domain", "gubs.ca")
    with conn:
        _table(conn)
        conn.execute("INSERT INTO inquiries(ref, ts, kind, org, name, email, website, budget, start, message, route,"
                     " status, updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,'new',?)",
                     (ref, time.time(), g["kind"], g["org"], g["name"], g["email"], g["website"], g["budget"],
                      g["start"], g["message"], route, time.time()))
    rec = {**g, "ref": ref, "route": route}
    notify(rec)
    return rec


def notify(rec: dict) -> bool:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return False
    msg = EmailMessage()
    msg["Subject"] = f"[{rec['ref']}] {KINDS[rec['kind']][0]}: {rec['org']}"
    msg["From"] = os.environ.get("SMTP_FROM", rec["route"])
    msg["To"] = rec["route"]
    msg["Reply-To"] = rec["email"]
    msg.set_content("\n".join([
        f"Reference: {rec['ref']}", f"Type: {KINDS[rec['kind']][0]}", f"Organisation: {rec['org']}",
        f"Contact: {rec['name']} <{rec['email']}>", f"Website: {rec['website'] or '-'}",
        f"Budget: {rec['budget'] or '-'}", f"Wanted start: {rec['start'] or '-'}", "", rec["message"], "",
        f"Reply to the sender directly, then: gbs inquiries {rec['ref']} replied"]))
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
            s.send_message(msg)
        return True
    except Exception:
        return False


def cli(conn, args: list[str]) -> int:
    with conn:
        _table(conn)
    if len(args) == 2:
        ref, status = args
        if status not in STATUSES:
            print("status must be one of", ", ".join(STATUSES))
            return 2
        with conn:
            n = conn.execute("UPDATE inquiries SET status=?, updated=? WHERE ref=?", (status, time.time(), ref)).rowcount
        print("updated" if n else "no such reference")
        return 0 if n else 1
    rows = conn.execute("SELECT ref, ts, kind, org, name, email, budget, status FROM inquiries "
                        "WHERE status IN ('new','replied') ORDER BY ts").fetchall()
    for r in rows:
        age = int((time.time() - r[1]) / 3600)
        print(f"{r[0]}  {r[7]:<8} {age:>4}h  {KINDS.get(r[2], (r[2],))[0]:<26} {r[3]} / {r[4]} <{r[5]}>  {r[6] or ''}")
    if not rows:
        print("no open inquiries")
    return 0
