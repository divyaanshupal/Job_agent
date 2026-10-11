import os
import sys
import json
import sqlite3
import argparse
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
from jobspy import scrape_jobs

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jobs.db"

# ---------------------------------------------------------
# Search Queries & Synonyms
# ---------------------------------------------------------
# Curated search roles covering interns, freshers & entry/mid SDE
DEFAULT_SEARCH_TERMS = [
    # Internship roles
    "sde intern",
    "software engineering intern",
    "backend intern",
    "full stack intern",
    "swe intern",
    "intern software engineer",
    # Full-time developer roles
    "software developer",
    "software development engineer",
    "software engineer",
    "backend engineer",
    "full stack developer",
    "frontend engineer",
    "junior software engineer",
    "associate software engineer"
]

# Targeted Locations & Modes:
# 1. India on-site/hybrid
# 2. Remote (Global & India)
DEFAULT_SEARCH_LOCATIONS = [
    {"location": "India", "is_remote": False},
    {"location": "India", "is_remote": True},
    {"location": "", "is_remote": True},  # Worldwide remote
]


def clean_dataframe_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares and cleans pandas DataFrame for SQLite insertion."""
    if df.empty:
        return df

    df = df.copy()

    # Ensure apply_url column exists
    if "apply_url" not in df.columns:
        if "job_url_direct" in df.columns and "job_url" in df.columns:
            df["apply_url"] = df["job_url_direct"].combine_first(df["job_url"])
        elif "job_url" in df.columns:
            df["apply_url"] = df["job_url"]
        elif "job_url_direct" in df.columns:
            df["apply_url"] = df["job_url_direct"]
        else:
            df["apply_url"] = None

    # Add timestamp
    df["scraped_at"] = datetime.now().isoformat()

    # Serialize list and dict columns so SQLite doesn't throw interface errors
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
            df[col] = df[col].apply(
                lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x
            )

    return df


def filter_relevant_jobs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Quality filter: Ensures scraped jobs match software engineering/intern roles
    and match targeted location criteria (India, Hybrid in India, Remote worldwide).
    """
    if df.empty or "title" not in df.columns:
        return df

    # Keywords for software developer/intern roles
    role_keywords = [
        "sde", "software", "swe", "backend", "back-end", "front-end", "frontend",
        "full stack", "fullstack", "web developer", "developer", "engineer", "intern"
    ]
    pattern_role = "|".join(role_keywords)

    # Exclude non-tech irrelevant jobs that sometimes slip through search algorithms
    exclude_keywords = [
        "sales", "marketing", "accountant", "nurse", "receptionist",
        "telecaller", "bpo", "graphic designer", "content writer"
    ]
    pattern_exclude = "|".join(exclude_keywords)

    # Filter by Title
    matched = df["title"].str.contains(pattern_role, case=False, na=False)
    not_excluded = ~df["title"].str.contains(pattern_exclude, case=False, na=False)
    filtered_df = df[matched & not_excluded].copy()

    return filtered_df


def save_jobs_to_db(df: pd.DataFrame, db_path: Path = DB_PATH) -> int:
    """Saves jobs to SQLite database with deduplication."""
    if df.empty:
        return 0

    df_clean = clean_dataframe_for_sqlite(df)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs';")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            try:
                existing_urls = pd.read_sql(
                    "SELECT DISTINCT job_url FROM jobs WHERE job_url IS NOT NULL", conn
                )["job_url"].tolist()
                new_jobs = df_clean[~df_clean["job_url"].isin(existing_urls)]
            except Exception:
                new_jobs = df_clean
        else:
            new_jobs = df_clean

        if new_jobs.empty:
            return 0

        # Append new jobs to database
        new_jobs.to_sql("jobs", conn, if_exists="append", index=False)
        conn.commit()

        total_count = conn.execute("SELECT count(*) FROM jobs;").fetchone()[0]
        print(f" [DB] Inserted {len(new_jobs)} new jobs. Total records in DB: {total_count}")
        return len(new_jobs)
    finally:
        conn.close()


def scrape_batch(
    terms: list[str],
    location_configs: list[dict],
    results_per_query: int = 10,
    sites: list[str] = None
):
    """
    Executes intelligent batch scraping across search terms, locations, and modes.
    """
    if sites is None:
        sites = ["indeed", "linkedin", "glassdoor"]

    total_added = 0
    total_fetched = 0

    print("=" * 65)
    print(" [*] SMART JOB SCRAPER ACTIVATED")
    print(f" Roles to Search     : {len(terms)} queries")
    print(f" Locations & Modes   : India (On-site/Hybrid) + Worldwide Remote")
    print(f" Platforms           : {', '.join(sites)}")
    print(f" Results Target/Call : {results_per_query}")
    print(f" Database            : {DB_PATH}")
    print("=" * 65)

    for i, term in enumerate(terms, 1):
        for loc_cfg in location_configs:
            loc = loc_cfg["location"]
            is_remote = loc_cfg["is_remote"]
            mode_label = "Remote Worldwide" if (is_remote and not loc) else ("Remote India" if is_remote else f"{loc} (On-site/Hybrid)")

            print(f"\n>> [{i}/{len(terms)}] Scraping: '{term}' | Mode: {mode_label}...")

            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=term,
                    location=loc if loc else None,
                    is_remote=is_remote,
                    results_wanted=results_per_query,
                    country_indeed="india",
                    hours_old=168,  # Last 7 days
                    verbose=0
                )
            except Exception as e:
                print(f"   [!] Scrape warning for '{term}' ({mode_label}): {e}")
                continue

            if df is not None and not df.empty:
                fetched_count = len(df)
                total_fetched += fetched_count

                # Apply quality role filter
                relevant_df = filter_relevant_jobs(df)
                saved_count = save_jobs_to_db(relevant_df, DB_PATH)
                total_added += saved_count

                print(f"   [+] Fetched: {fetched_count} | Relevant & New Saved: {saved_count}")
            else:
                print(f"   [-] No jobs returned for this combination.")

            # Gentle delay to avoid aggressive rate limiting
            time.sleep(1.5)

    print("\n" + "=" * 65)
    print(" [DONE] SCRAPING CYCLE FINISHED")
    print(f" Total Postings Examined : {total_fetched}")
    print(f" Total New Jobs Stored   : {total_added}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Smart Job Scraper with Synonym Expansion & Remote/India Filters")
    parser.add_argument("--search", "-s", type=str, default=None, help="Custom search term (optional)")
    parser.add_argument("--results", "-r", type=int, default=10, help="Results wanted per query combination")
    parser.add_argument("--quick", action="store_true", help="Quick mode (runs top 3 queries only)")
    args = parser.parse_args()

    if args.search:
        search_terms = [args.search]
    elif args.quick:
        search_terms = [
            "sde intern",
            "backend intern",
            "software development engineer"
        ]
    else:
        search_terms = DEFAULT_SEARCH_TERMS

    scrape_batch(
        terms=search_terms,
        location_configs=DEFAULT_SEARCH_LOCATIONS,
        results_per_query=args.results
    )


if __name__ == "__main__":
    main()