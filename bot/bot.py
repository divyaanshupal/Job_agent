import os
from pathlib import Path
import sqlite3
import sys

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
DB = ROOT / "jobs.db"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    chat_id_str = str(update.effective_chat.id)
    if CHAT_ID and chat_id_str != CHAT_ID:
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT rowid as id, title, company, location, site, apply_url, job_url, score, reason
        FROM jobs
        WHERE status IN ('new', 'scored') AND (score >= 70 OR score IS NULL)
        ORDER BY score DESC
        LIMIT 10
    """)
    jobs = cur.fetchall()

    if not jobs:
        await update.message.reply_text("No new jobs to review.")
        con.close()
        return

    for job in jobs:
        apply_url = job["apply_url"] or job["job_url"]
        is_direct = bool(
            job["apply_url"]
            and any(
                ats in job["apply_url"].lower()
                for ats in ["greenhouse", "lever", "ashby", "workable", "smartrecruiters"]
            )
        )
        apply_type = "⚡ Direct ATS" if is_direct else "👤 Easy Apply / Link"

        msg = (
            f"💼 {job['title'] or 'Role'}\n"
            f"🏢 {job['company'] or 'Company'}\n"
            f"📍 {job['location'] or 'Location'}\n"
            f"🎯 Score: {job['score'] or 'N/A'}/100\n"
            f"💡 Reason: {job['reason'] or 'N/A'}\n"
            f"🏷️ Type: {apply_type}\n"
            f"🔗 {apply_url}"
        )

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Apply", callback_data=f"approved|{job['id']}"),
                InlineKeyboardButton("❌ Skip", callback_data=f"skipped|{job['id']}"),
            ]
        ])

        await update.message.reply_text(msg, reply_markup=kb, disable_web_page_preview=True)
        con.execute("UPDATE jobs SET status = 'sent' WHERE rowid = ?", (job["id"],))

    con.commit()
    con.close()


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    if "|" not in query.data:
        return

    action, job_id = query.data.split("|", 1)

    con = db()
    con.execute("UPDATE jobs SET status = ? WHERE rowid = ?", (action, job_id))
    con.commit()
    con.close()

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.message.reply_text(f"Marked: {action.upper()}")


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN missing in .env")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "digest"], digest))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
