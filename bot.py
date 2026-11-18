#!/usr/bin/env python3
"""
Telegram bot for the certificate generator.

How the team uses it (in a private chat with the bot):
  Send the Zoom chat .txt file with this as the caption:

      Group: Basics J
      Excellence: Name 1, Name 2
      Good Start: Name 3
      Improvement: Name 4
      Participation: top 10

  (Any list can be left out. You can also send the text first and the file after it.)

The bot replies with a check report, one PDF per student, and a zip with everything.

Setup: see TELEGRAM_BOT.md
"""
import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "make_certificates.py"
MAX_INDIVIDUAL_PDFS = 40

HELP = (
    "Send me the Zoom chat .txt file with this as the caption:\n\n"
    "Group: Basics J\n"
    "Excellence: Name 1, Name 2\n"
    "Good Start: Name 3\n"
    "Improvement: Name 4\n"
    "Participation: top 10\n"
    "Rename: chat name = English Name   (only for nicknames or emoji names)\n\n"
    "Any line can be left out. English names only.\n"
    "You can also send the text first, then the file without a caption.\n\n"
    "/myid shows your Telegram ID (needed once to get access)."
)

KEYS = {
    "group name": "group", "group": "group", "course": "group",
    "excellence": "excellence",
    "good start": "good_start", "goodstart": "good_start", "good_start": "good_start",
    "improvement": "improvement",
    "participation": "participation",
    "rename": "rename",
}
# a line that STARTS with one of these words starts a new section (":" "-" "=" or just a space may follow)
KEY_LINE = re.compile(
    r"^(" + "|".join(sorted((re.escape(k) for k in KEYS), key=len, reverse=True)) + r")\b\s*[:\uff1a=\-\u2013\u2014]*\s*(.*)$",
    re.I)


# --------------------------------------------------------------------------
# Core logic (no Telegram needed - easy to test)
# --------------------------------------------------------------------------
def parse_fields(text):
    """Turn the caption / message text into the session settings.
    Lines the bot can't place are returned in f["ignored"] so nothing is silently misfiled."""
    parts = {"group": [], "excellence": [], "good_start": [], "improvement": [], "rename": []}
    f = {"group": "", "excellence": "", "good_start": "", "improvement": "", "rename": "",
         "participation_n": 0, "ignored": []}
    cur = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = KEY_LINE.match(line)
        if m:
            cur = KEYS[m.group(1).lower()]
            val = m.group(2).strip()
        elif cur is not None and (":" not in line or cur == "rename"):
            val = line  # names continued on the next line
        else:
            f["ignored"].append(line)
            continue
        if cur == "participation":
            n = re.search(r"\d+", val)
            if n:
                f["participation_n"] = int(n.group())
        elif val.strip(", ;"):
            parts[cur].append(val.strip(", ;"))
    f["group"] = " ".join(parts["group"])
    f["rename"] = "; ".join(parts["rename"])
    for k in ("excellence", "good_start", "improvement"):
        f[k] = ", ".join(parts[k])
    return f


def problems_with(f):
    if not f:
        return "I don't have the session details yet."
    if not f["group"]:
        return "Please add the group name, for example:  Group: Basics J"
    if not (f["excellence"] or f["good_start"] or f["improvement"] or f["participation_n"]):
        return "Nothing to make. Add names for Excellence / Good Start / Improvement and/or  Participation: top 10"
    return None


def build_certificates(chat_path, f, work_dir):
    """Run the generator. Returns (list_of_pdfs, zip_path, report_text)."""
    out = Path(work_dir) / "certificates"
    cmd = [sys.executable, "-W", "ignore", str(SCRIPT), "--chat", str(chat_path),
           f"--group={f['group']}", f"--participation-n={f['participation_n']}", f"--out={out}"]
    for flag, key in (("--excellence", "excellence"), ("--good-start", "good_start"),
                      ("--improvement", "improvement"), ("--rename", "rename")):
        if f[key]:
            cmd.append(f"{flag}={f[key]}")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=300, cwd=str(HERE), env=env)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-3:]
        raise RuntimeError(" | ".join(tail) or "the generator failed")
    pdfs = sorted(out.rglob("*.pdf"))
    report = (out / "check_report.txt").read_text(encoding="utf-8")
    return pdfs, Path(work_dir) / "certificates.zip", report


# --------------------------------------------------------------------------
# Telegram part
# --------------------------------------------------------------------------
ALLOWED = {int(x) for x in re.split(r"[,\s]+", os.environ.get("ALLOWED_USER_IDS", "")) if x.isdigit()}
ALLOW_ANYONE = os.environ.get("ALLOW_ANYONE") == "1"


def is_allowed(update):
    uid = update.effective_user.id if update.effective_user else None
    return ALLOW_ANYONE or (uid in ALLOWED)


async def deny(update):
    uid = update.effective_user.id if update.effective_user else "?"
    await update.message.reply_text(
        f"You don't have access yet. Your Telegram ID is {uid}. "
        "Send it to the person who runs this bot so they can add it.")


async def cmd_help(update, context):
    await update.message.reply_text(HELP)


async def cmd_myid(update, context):
    await update.message.reply_text(f"Your Telegram ID: {update.effective_user.id}")


async def on_text(update, context):
    if not is_allowed(update):
        return await deny(update)
    f = parse_fields(update.message.text)
    if not any([f["group"], f["excellence"], f["good_start"], f["improvement"], f["participation_n"]]):
        return await update.message.reply_text(HELP)
    context.user_data["fields"] = f
    p = problems_with(f)
    if p:
        return await update.message.reply_text(p)
    note = ("\nI did not understand these lines and ignored them: " + " | ".join(f["ignored"])) if f["ignored"] else ""
    await update.message.reply_text("Got it. Now send the Zoom chat .txt file (no caption needed)." + note)


async def on_document(update, context):
    msg = update.message
    if not is_allowed(update):
        return await deny(update)
    doc = msg.document
    if not (doc.file_name or "").lower().endswith(".txt"):
        return await msg.reply_text("Please send the Zoom chat as a .txt file.")
    f = parse_fields(msg.caption) if msg.caption else context.user_data.get("fields")
    p = problems_with(f)
    if p:
        return await msg.reply_text(p + "\n\n" + HELP)
    note = ""
    if f.get("ignored"):
        note = "\nI did not understand these lines and ignored them: " + " | ".join(f["ignored"])
    await msg.reply_text("Working on it..." + note)
    with tempfile.TemporaryDirectory() as tmp:
        chat = Path(tmp) / "chat.txt"
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(str(chat))
        try:
            pdfs, zpath, report = await asyncio.to_thread(build_certificates, chat, f, tmp)
        except Exception as e:  # show a readable reason instead of failing silently
            logging.exception("generation failed")
            return await msg.reply_text(f"Sorry, it failed: {e}")
        await msg.reply_text(report[:3900])
        if len(pdfs) <= MAX_INDIVIDUAL_PDFS:
            for pdf in pdfs:
                with open(pdf, "rb") as fh:
                    await msg.reply_document(fh, filename=pdf.name)
                await asyncio.sleep(0.6)  # stay under Telegram's flood limit
        else:
            await msg.reply_text(f"{len(pdfs)} certificates - too many to send one by one, see the zip.")
        with open(zpath, "rb") as fh:
            await msg.reply_document(fh, filename="certificates.zip")
    context.user_data.pop("fields", None)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Set the TELEGRAM_BOT_TOKEN environment variable first (see TELEGRAM_BOT.md).")
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not ALLOWED and not ALLOW_ANYONE:
        logging.warning("ALLOWED_USER_IDS is empty: nobody can use the bot yet. Send /myid to it to get an ID.")
    
    # --- UPDATED TIMEOUTS & RETRIES FOR STABLE CLOUD HOSTING ---
    app = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    app.add_handler(CommandHandler(["start", "help"], cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    
    # --- ADDED BOOTSTRAP RETRIES TO PREVENT TIMEDOUT CRASHES ---
    app.run_polling(bootstrap_retries=-1, drop_pending_updates=True)


if __name__ == "__main__":
    main()
