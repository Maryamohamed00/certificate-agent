# Certificate Agent: instructions for the team

Use this in a Claude chat that has the `certificate-agent` folder (templates, fonts and
`make_certificates.py`) attached. It makes the session certificates for Mr. Younes Ghareeb's group.

## What to send each session
1. The Zoom chat file (`meeting_saved_chat.txt`).
2. The **group name** (for example: Basics J).
3. The names for **Excellence**, **Good Start** and **Improvement**. Any of the three can be empty.
4. **N** for Participation (for example 5, 10 or 15). Use 0 or leave it out for no Participation certificates.

Example message:

> Group: Basics J
> Excellence: Mariam Aiman
> Good Start: Omar Hany, Remas
> Improvement: Suhaib
> Participation: top 10
> (chat file attached)

## What the agent does
1. Reads the chat. A message counts if it was sent to **Younes Ghareeb** (direct message) or to **Everyone**.
   Younes's own messages are never counted. Nobody else is excluded unless you say so.
2. Fixes the spelling of the Excellence / Good Start / Improvement names using the names in the chat.
   Names are capitalised properly ("hamza  ahmed" becomes "Hamza Ahmed").
3. Gives Participation to the top N students by message count.
   - A student already in Excellence, Good Start or Improvement is skipped, so nobody gets two certificates.
     The next student down the ranking takes the spot.
   - If two or more students are tied at the cutoff, **all of them get one**, so you may get more than N.
4. Writes the group name and student name onto the Canva templates and returns:
   - one PDF per student (grouped in a folder per certificate type)
   - `summary.csv` (who got what, message counts, name checks)
   - `check_report.txt`
   - one zip with everything

## Always read the check list before sending anything
| Label | Meaning | What to do |
|---|---|---|
| FIXED | Spelling corrected from the chat | Quick look, usually fine |
| CHECK | Closest chat name is a guess, or two chat names fit | Confirm the right student |
| NOT_FOUND | Name isn't in the chat, written exactly as typed | Check the spelling yourself. The file name ends in `_CHECK-NAME` |
| SKIPPED | Chat name has no English letters (emoji-only, Arabic, "iPhone"), so no certificate was made | Re-run with `--rename "chat name=English Name"` (Telegram: `Rename: chat name = English Name`) |
| DUPLICATE | Student was listed twice | Only the first certificate is made |
| TIE | Tie at the Participation cutoff | More than N certificates were made |

## How the agent runs it
```
python make_certificates.py --chat meeting_saved_chat.txt --group "Basics J" \
   --excellence "Name 1" --good-start "Name 2, Name 3" --improvement "Name 4" \
   --participation-n 10 --out output/session
```
- `--list-counts` only shows the message ranking (no certificates).
- `--count-mode younes` counts only direct messages to Younes (default counts Younes + Everyone).
- `--rename "iPhone=Ali Hassan; other=Name"` gives the English name for nicknames or emoji names.
- `--exclude "Name"` leaves someone out of the Participation count.

## Rules the agent must follow
- English names only.
- Never give one student more than one certificate.
- Never invent or guess a name. If a name isn't in the chat, say so.
- Do not change the Canva design. Only the student name and the group name are written.
- Reply with the files and a short summary of the check list, nothing long.

## One thing to know about fonts
The Participation template uses the font **Gagalin**, which isn't installed here. Until
`fonts/Gagalin-Regular.ttf` is added to the folder, the student name on Participation certificates
uses a similar bold blue font. Adding that one file makes it match Canva exactly, with no other change.

## Files in the folder
- `make_certificates.py`: the generator
- `templates/`: the 4 Canva PDFs (excellence, good_start, improvement, participation)
- `fonts/`: the fonts used on the certificates
- `INSTRUCTIONS.md`: this file
