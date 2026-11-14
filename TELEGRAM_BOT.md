# Telegram bot: setup (about 10 minutes, once)

The bot runs on a computer you control. It must stay on and online while the team uses it.

## 1. Create the bot
1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a name and a username (it must end in `bot`).
3. BotFather gives you a **token**. Keep it private, anyone with it can control the bot.

## 2. Install (once)
Install Python 3.10 or newer, then in the `certificate-agent` folder run:
```
pip install -r requirements.txt
```

## 3. Get access for the team
Only people whose Telegram ID is on the list can use the bot.
1. Start the bot once with no list (step 4 without `ALLOWED_USER_IDS`).
2. Each team member sends `/myid` to the bot and sends you the number it replies with.
3. Stop the bot, then start it again with all the IDs in `ALLOWED_USER_IDS`, separated by commas.

## 4. Run it
Windows (PowerShell):
```
$env:TELEGRAM_BOT_TOKEN="123456:ABC..."
$env:ALLOWED_USER_IDS="111111111,222222222"
python bot.py
```
Mac / Linux:
```
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export ALLOWED_USER_IDS="111111111,222222222"
python3 bot.py
```
Leave the window open. Closing it or turning off the computer stops the bot.
For 24/7 use, run it on an always-on computer or a small server.

## 5. How the team uses it
Open a private chat with the bot. Send the Zoom chat `.txt` file with this as the **caption**:
```
Group: Basics J
Excellence: Name 1, Name 2
Good Start: Name 3
Improvement: Name 4
Participation: top 10
```
- Any line can be left out. English names only.
- Zoom names with emoji are cleaned automatically ("Sara 🍉" becomes "Sara"). If a chat name has no English
  letters at all (an emoji-only name, Arabic, or a nickname like "iPhone"), that student is skipped and the check list
  says so. Give the real name with a line like `Rename: iPhone = Ali Hassan` and send it again.
- You can also send the text first and the file right after, without a caption.
- The bot replies with the check list, one PDF per student, and a zip with everything.
- If the bot says it ignored a line, fix the line and send again. It never guesses where a line belongs.

## Good to know
- **Read the check list** before forwarding certificates. It shows spelling fixes, names not found in the chat, and ties.
- **Font:** Participation certificates use a close match until `fonts/Gagalin-Regular.ttf` is added to the folder.
- **Not tested against Telegram itself.** The whole flow was tested with simulated messages, but the first real run with your token is the real test. If something fails, the bot replies with the reason.
- Keep the token out of shared files and chats. If it leaks, ask @BotFather to revoke it with `/revoke`.
