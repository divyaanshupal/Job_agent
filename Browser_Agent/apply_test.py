"""
apply_test.py  --  Browser-use powered Glassdoor Easy Apply bot
Usage:
    python apply_test.py "https://www.glassdoor.co.in/job-listing/j?jl=..."
"""

import asyncio
import json
import logging
import os
import sys

# Force UTF-8 output so emoji in browser-use logs don't crash on Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

from dotenv import load_dotenv
from browser_use import Agent, BrowserSession, BrowserProfile
from llm import get_llm, get_fallback_llm

logging.basicConfig(level=logging.INFO, format="%(message)s")

# -- Load environment (llm.py also loads it, but load here for PROFILE use)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# -- Load applicant profile
PROFILE_PATH = Path(__file__).resolve().parent / "profile.json"
with open(PROFILE_PATH, "r", encoding="utf-8") as f:
    PROFILE = json.load(f)

RESUME_PATH = Path(PROFILE.get("resume_path", "")).expanduser()


def build_task(job_url: str) -> str:
    resume_note = (
        f"Upload the resume located at: {RESUME_PATH}"
        if RESUME_PATH.exists()
        else "Skip resume upload (file not found)."
    )

    gd_email = PROFILE.get("glassdoor_email", PROFILE["email"])
    gd_password = PROFILE.get("glassdoor_password", "")
    has_password = gd_password and gd_password != "YOUR_GLASSDOOR_PASSWORD"

    auth_instructions = ""
    if has_password:
        auth_instructions = f"""
## Glassdoor Login / Authentication
- If a sign-in wall appears, enter the email: {gd_email}
- Click "Continue" then look for a PASSWORD field (not OTP/Google).
  - If you see "Sign in with Google" or "Send a code", look for a link that says
    "Sign in with password" or "Use password instead" and click it.
  - Enter the password in the password field and submit.
- If login fails (wrong credentials / no account), try:
  a) "Create an account" with the same email and set up a new profile, OR
  b) Look for "Apply as Guest" or "Continue without signing in".
- NEVER wait for an OTP code - always prefer the password sign-in option.
"""
    else:
        auth_instructions = """
## Glassdoor Login / Authentication
- If a sign-in wall appears, look for "Apply as Guest", "Continue without account",
  or "Skip sign-in". Click that option.
- If sign-in is mandatory and no guest option exists, enter the email and look for
  a password field. Stop and report that credentials are needed.
"""

    return f"""
You are an automated job application assistant. Your goal is to apply to the job at:
{job_url}

{auth_instructions}

## Application Form
After authentication (or bypassing it), fill the form with these details:
   - First Name         : {PROFILE["first_name"]}
   - Last Name          : {PROFILE["last_name"]}
   - Email              : {PROFILE["email"]}
   - Phone Number       : {PROFILE["phone"]}
   - Location           : {PROFILE["location"]}
   - LinkedIn URL       : {PROFILE.get("linkedin", "")}
   - GitHub URL         : {PROFILE.get("github", "")}
   - Notice Period      : {PROFILE.get("notice_period", "Immediate")}
   - Work Authorization : {PROFILE.get("work_authorization", "Authorized to work in India")}
   - Willing to Relocate: {PROFILE.get("willing_to_relocate", "Yes")}
   - Expected CTC       : {PROFILE.get("expected_ctc", "")}
   - Cover Note / Summary: {PROFILE.get("summary", "")}

## Resume
{resume_note}

## Experience Fields
If there are "Years of Experience" dropdowns or inputs:
   - Total Experience: ~1 year
   - Node.js / Express: 1 year
   - MongoDB: 1 year

## Other Fields
- "How did you hear about us?" -> "Job Board"
- Answer Yes/No screening questions to keep the application eligible.

## Final Step (IMPORTANT)
Do NOT click the final Submit button. Stop just before it.
Take a screenshot and report:
1. Company name and job title
2. All fields that were filled successfully
3. Any fields that could NOT be filled and why
4. Current state of the page

If a CAPTCHA appears, stop and report it immediately.
"""


async def run_apply(job_url: str):
    llm = get_llm()
    fallback_llm = get_fallback_llm()  # Ollama local — used by Agent if primary LLM fails mid-run

    browser_profile = BrowserProfile(
        headless=False,
        user_data_dir=None,
    )

    browser_session = BrowserSession(browser_profile=browser_profile)

    agent = Agent(
        task=build_task(job_url),
        llm=llm,
        fallback_llm=fallback_llm,
        browser_session=browser_session,
        max_actions_per_step=10,
    )

    print("=" * 60)
    print(" JOB APPLICATION AGENT")
    print(f" Target URL : {job_url}")
    print(f" Applicant  : {PROFILE['first_name']} {PROFILE['last_name']}")
    print(f" Email      : {PROFILE['email']}")
    print("=" * 60)
    print("\n[*] Starting browser agent...\n")

    result = await agent.run(max_steps=50)

    print("\n" + "=" * 60)
    print(" AGENT FINISHED")
    print("=" * 60)
    # Safe print: encode to UTF-8 bytes then decode with replacement to avoid cp1252 crash
    result_str = str(result).encode("utf-8", errors="replace").decode("utf-8")
    print(result_str)


def main():
    if len(sys.argv) < 2:
        print("Usage: python apply_test.py <job_url>")
        print('Example: python apply_test.py "https://www.glassdoor.co.in/job-listing/j?jl=..."')
        sys.exit(1)

    job_url = sys.argv[1].strip()
    asyncio.run(run_apply(job_url))


if __name__ == "__main__":
    main()
