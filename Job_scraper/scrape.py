import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
from jobspy import scrape_jobs

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jobs.db"


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


def save_jobs_to_db(df: pd.DataFrame, db_path: Path = DB_PATH) -> int:
    """Saves jobs to SQLite database with deduplication."""
    if df.empty:
        print("[INFO] No jobs to save.")
        return 0

    df_clean = clean_dataframe_for_sqlite(df)

    conn = sqlite3.connect(db_path)
    try:
        # Check if table 'jobs' already exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs';")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Deduplicate against existing job_url
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
            print("[INFO] All scraped jobs already exist in database (no new jobs to insert).")
            return 0

        # Append new jobs to database
        new_jobs.to_sql("jobs", conn, if_exists="append", index=False)
        conn.commit()

        # Total count
        total_count = conn.execute("SELECT count(*) FROM jobs;").fetchone()[0]
        print(f"[SUCCESS] Saved {len(new_jobs)} new jobs into {db_path.name}! Total in DB: {total_count}")
        return len(new_jobs)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape jobs and save to SQLite DB.")
    parser.add_argument("--search", "-s", type=str, default="Software Engineer", help="Job title / search term")
    parser.add_argument("--location", "-l", type=str, default="India", help="Location (e.g. India, Remote, etc.)")
    parser.add_argument("--results", "-r", type=int, default=15, help="Number of results wanted per site")
    parser.add_argument("--country-indeed", type=str, default="india", help="Country for Indeed (e.g. india, usa)")
    args = parser.parse_args()

    sites = ["indeed", "linkedin", "glassdoor"]

    print(f"==================================================")
    print(f" Starting Job Scraping:")
    print(f" Search Term : '{args.search}'")
    print(f" Location    : '{args.location}'")
    print(f" Target Sites: {', '.join(sites)}")
    print(f" Results/Site: {args.results}")
    print(f" Output DB   : {DB_PATH}")
    print(f"==================================================")

    try:
        jobs = scrape_jobs(
            site_name=sites,
            search_term=args.search,
            location=args.location,
            results_wanted=args.results,
            country_indeed=args.country_indeed,
            hours_old=168,  # past 7 days
            verbose=1
        )
    except Exception as e:
        print(f"[ERROR] Failed during scraping: {e}")
        return

    print(f"\n[INFO] Total jobs fetched: {len(jobs)}")

    if not jobs.empty:
        # Site-wise distribution
        if "site" in jobs.columns:
            print("\nFetched jobs by site:")
            site_counts = jobs["site"].value_counts()
            for site, count in site_counts.items():
                print(f" - {site}: {count} jobs")

        save_jobs_to_db(jobs, DB_PATH)

        # Show preview of first 5 jobs
        print("\n--- Top Scraped Jobs Preview ---")
        preview_cols = [c for c in ["title", "company", "site", "location", "apply_url"] if c in jobs.columns]
        for idx, row in jobs.head(5).iterrows():
            print(f"{idx + 1}. {row.get('title', 'N/A')} at {row.get('company', 'N/A')} ({row.get('site', 'N/A')})")
            if "apply_url" in row and pd.notna(row["apply_url"]):
                print(f"   Apply: {row['apply_url']}")
    else:
        print("[WARN] No jobs were returned by scraper.")


if __name__ == "__main__":
    main()