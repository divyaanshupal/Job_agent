import sqlite3
from datetime import datetime
from jobspy import scrape_jobs

DB = "jobs.db"

SEARCHES = [
    {"term": "backend developer node.js", "location": "India"},
    {"term": "software development engineer fintech", "location": "India"},
    {"term": "backend engineer remote", "location": "India"},
]

def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_url TEXT PRIMARY KEY,
        apply_url TEXT,
        site TEXT, title TEXT, company TEXT, location TEXT,
        date_posted TEXT, description TEXT,
        score INTEGER, reason TEXT,
        status TEXT DEFAULT 'new',   -- new | scored | sent | approved | skipped | applied | failed
        created_at TEXT
    )""")
    con.commit()
    return con

def run():
    con = init_db()
    added = 0
    for s in SEARCHES:
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=s["term"],
                location=s["location"],
                results_wanted=30,
                hours_old=24,
                country_indeed="India",
                linkedin_fetch_description=True,
            )
        except Exception as e:
            print("scrape failed:", s["term"], e)
            continue

        for _, r in df.iterrows():
            try:
                con.execute(
                    "INSERT INTO jobs (job_url, apply_url, site, title, company, location, date_posted, description, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (r["job_url"], r.get("job_url_direct"), r["site"], r["title"],
                     r["company"], r["location"], str(r["date_posted"]),
                     r.get("description"), datetime.utcnow().isoformat()),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass  # duplicate, skip
    con.commit()
    print(f"{added} new jobs added")

if __name__ == "__main__":
    run()


    #test