#!/usr/bin/env python3
"""
Certificate generator for Mr. Younes Ghareeb's sessions.

Input : Zoom chat .txt + names for Excellence / Good Start / Improvement
        + how many Participation certificates (top N by message count) + group name
Output: one PDF per student (name + group name written on the Canva template),
        a summary CSV and a check report.

Usage:
  python make_certificates.py --chat chat.txt --group "Basics J" \
      --excellence "Name 1, Name 2" --good-start "Name 3" --improvement "Name 4" \
      --participation-n 10 --out output/session_name

  python make_certificates.py --chat chat.txt --list-counts      # just show the ranking
"""
import argparse
import csv
import difflib
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
FONTS = HERE / "fonts"

# --------------------------------------------------------------------------
# Template layout (measured from the Canva PDFs; page 2 of each file is blank)
# cx = centre x, y = text baseline, maxw = widest the text may get before it shrinks
# --------------------------------------------------------------------------
SPECS = {
    "excellence": {
        "label": "Excellence",
        "template": "excellence.pdf",
        "name": dict(font="TeXGyreTermes-Bold.otf", size=72.3, color=0x9B724E,
                     cx=421.1, y=315.8, maxw=590, case="title"),
        "group": dict(font="PinyonScript.ttf", size=34.4, color=0x92826F,
                      cx=660.15, y=474.9, maxw=170, case="title"),
    },
    "good_start": {
        "label": "GoodStart",
        "template": "good_start.pdf",
        "name": dict(font="LeagueSpartan-Bold.ttf", size=76.5, color=0x101010,
                     cx=600.0, y=424.8, maxw=900, case="title"),
        "group": dict(font="Montserrat-Bold.ttf", size=19.8, color=0x121212,
                      cx=844.8, y=662.8, maxw=190, case="upper"),
    },
    "improvement": {
        "label": "Improvement",
        "template": "improvement.pdf",
        "name": dict(font="Arimo-Bold.ttf", size=38.8, color=0x1B102F,
                     cx=416.15, y=282.1, maxw=330, case="title"),
        "group": dict(font="JosefinSans-Regular.ttf", size=11.8, color=0x2B2B2B,
                      cx=584.25, y=443.7, maxw=165, case="upper"),
    },
    "participation": {
        "label": "Participation",
        "template": "participation.pdf",
        # The template uses the font "Gagalin". If fonts/Gagalin-Regular.ttf exists it is used,
        # otherwise a bold sans fallback in the same blue is used.
        "name": dict(font="Gagalin-Regular.ttf", fallback="Arimo-Bold.ttf", fallback_size=54.0,
                     size=62.5, color=0x003399, cx=421.15, y=322.9, maxw=560, case="upper"),
        "group": dict(font="Arimo-Bold.ttf", size=16.5, color=0x332C2B,
                      cx=584.85, y=484.3, maxw=175, case="upper"),
    },
}
# Which page of each Canva PDF is used as the blank certificate.
# Page 2 is blank in every file except Good Start, whose page 2 has an old group name ("BASICS H")
# baked into the background picture - so there page 1 is used and its sample name + group are removed.
PAGE_INDEX = {"excellence": 1, "good_start": 0, "improvement": 1, "participation": 1}
ERASE = {
    "good_start": [fitz.Rect(210, 350, 990, 455), fitz.Rect(795, 640, 895, 670)],
}

PRIORITY = ["excellence", "good_start", "improvement"]  # who keeps the student if listed twice


# --------------------------------------------------------------------------
# Chat parsing
# --------------------------------------------------------------------------
HEADER = re.compile(r"^\s*(\d{1,2}:\d{2}:\d{2})\s+From\s+(.+?)(?:\s+to\s+(.+?))?\s*:\s*(.*)$")


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


def norm(s):
    """lower-case, letters/digits only, single spaces"""
    return squash(re.sub(r"[^a-z0-9؀-ۿ ]", " ", s.lower()))


def cap_word(w):
    if w.islower() or w.isupper():
        return w[:1].upper() + w[1:].lower()
    return w  # keep mixed case such as McDonald


def title_name(s):
    return " ".join("-".join(cap_word(p) for p in w.split("-")) for w in squash(s).split(" "))


DISPLAY_NOTES = {}  # chat key -> note about a display name that had to be cleaned


def clean_display(raw):
    """Name as it should be printed: English letters only (Zoom names often contain emoji).
    Returns (name, note). If nothing usable is left the original is returned with a warning note."""
    cleaned = squash(re.sub(r"[^A-Za-z\u00C0-\u024F\s'.\-]", " ", raw))
    if not re.search(r"[A-Za-z]", cleaned):
        return squash(raw), "has no English letters - type this student's name yourself"
    if cleaned != squash(raw):
        return cleaned, f"symbols/emoji removed from the chat name '{squash(raw)}'"
    return cleaned, ""


def parse_chat(path):
    msgs, cur = [], None
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            m = HEADER.match(line)
            if m:
                cur = {"time": m.group(1), "sender": squash(m.group(2)),
                       "to": (m.group(3) or "Everyone").strip(), "text": []}
                if m.group(4).strip():
                    cur["text"].append(m.group(4).strip())
                msgs.append(cur)
            elif cur is not None and line.strip():
                cur["text"].append(line.strip())
    return msgs


def classify(to, teacher_tokens):
    t = to.lower()
    if t.startswith("everyone") or t.startswith("all "):
        return "everyone"
    if all(tok in t for tok in teacher_tokens):
        return "teacher"
    return "other"


def count_messages(msgs, teacher, mode, exclude):
    teacher_tokens = norm(teacher).split()
    excl = [norm(e) for e in exclude if e.strip()]
    counts, spell = Counter(), defaultdict(Counter)
    seen_senders = Counter()
    for m in msgs:
        key = norm(m["sender"]) or squash(m["sender"]).lower()
        if not key:
            continue
        seen_senders[key] += 1
        spell[key][squash(m["sender"])] += 1
        if all(tok in key for tok in teacher_tokens):  # the teacher himself
            continue
        if any(e and (e == key or e in key) for e in excl):
            continue
        kind = classify(m["to"], teacher_tokens)
        if kind == "teacher" or (kind == "everyone" and mode == "both"):
            counts[key] += 1
    display = {}
    DISPLAY_NOTES.clear()
    for k, v in spell.items():
        name, note = clean_display(v.most_common(1)[0][0])
        display[k] = title_name(name)
        if note:
            DISPLAY_NOTES[k] = note
    return counts, display


# --------------------------------------------------------------------------
# Name checking against the chat
# --------------------------------------------------------------------------
def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_score(given, chat_key):
    g, c = given.split(), chat_key.split()
    full = ratio(given, chat_key)
    if not g or not c:
        return 0.0
    # how well every chat token is found inside the given name
    tok = sum(max(ratio(a, b) for b in g) for a in c) / len(c)
    # chat has the first name only (e.g. "sara") but the teacher wrote the full name
    if len(c) <= len(g):
        return max(full, tok * 0.97)
    # teacher wrote only the first name, chat has more
    tok2 = sum(max(ratio(a, b) for b in c) for a in g) / len(g)
    return max(full, tok2 * 0.9)


def resolve_name(given, display, eligible_keys):
    """Return (final_name, matched_key, status, note)."""
    g_raw = squash(given)
    g = norm(g_raw)
    if not g:
        return None
    if re.search(r"[^\x00-\x7f]", g_raw):
        note_nonascii = " (contains non-English letters - English names only)"
    else:
        note_nonascii = ""
    scored = sorted(((match_score(g, k), k) for k in eligible_keys), reverse=True)
    if not scored or scored[0][0] < 0.7:
        return (title_name(g_raw), None, "NOT_FOUND",
                "not found in the chat - written exactly as you typed it, please check" + note_nonascii)
    best, key = scored[0]
    ambiguous = len(scored) > 1 and scored[1][0] >= 0.75 and best - scored[1][0] < 0.06
    chat_name = display[key]
    gt, ct = g.split(), key.split()
    if len(gt) < len(ct):
        final = chat_name  # the chat has the fuller name
    else:
        out = []
        for tok, orig in zip(gt, g_raw.split()):
            cand = max(ct, key=lambda c: ratio(tok, c))
            out.append(cap_word(cand) if ratio(tok, cand) >= 0.75 else cap_word(orig))
        final = " ".join(out)
    changed = norm(final) != g
    if ambiguous:
        status, note = "CHECK", f"could be '{chat_name}' or '{display[scored[1][1]]}'"
    elif best < 0.8:
        status, note = "CHECK", f"closest chat name is '{chat_name}' - please confirm"
    elif changed:
        status, note = "FIXED", f"typed '{g_raw}' -> written '{final}' (chat name '{chat_name}')"
    else:
        status, note = "OK", ""
    return (final, key, status, note + note_nonascii)


def apply_renames(spec, display):
    """--rename "chat name=English Name; other=Name": fixes nicknames / emoji names. Returns notes."""
    notes = []
    for part in re.split(r"[;\n]+", spec or ""):
        if "=" not in part:
            continue
        chat, real = (x.strip() for x in part.split("=", 1))
        k = norm(chat) or squash(chat).lower()
        if k in display and real:
            display[k] = title_name(real)
            DISPLAY_NOTES.pop(k, None)
        else:
            notes.append(f"NOTE       rename '{chat}' did not match anyone in the chat")
    return notes


def split_names(text):
    if not text:
        return []
    if text.startswith("@") and Path(text[1:]).exists():
        text = Path(text[1:]).read_text(encoding="utf-8")
    parts = re.split(r"[\n,;]+", text)
    return [squash(p) for p in parts if squash(p)]


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def rgb(c):
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)


def place(page, text, spec, alias_cache, fonts_used):
    fontfile = FONTS / spec["font"]
    size = spec["size"]
    if not fontfile.exists() and spec.get("fallback"):
        fontfile = FONTS / spec["fallback"]
        size = spec.get("fallback_size", size)
        fonts_used.add(f"{spec['font']} not found -> used {spec['fallback']}")
    if spec["case"] == "upper":
        text = text.upper()
    font = fitz.Font(fontfile=str(fontfile))
    width = font.text_length(text, fontsize=size)
    if width > spec["maxw"]:
        size = size * spec["maxw"] / width
        width = spec["maxw"]
    alias = alias_cache.setdefault(str(fontfile), "F" + str(len(alias_cache) + 1))
    page.insert_font(fontname=alias, fontfile=str(fontfile))
    x = spec["cx"] - width / 2
    page.insert_text(fitz.Point(x, spec["y"]), text, fontname=alias, fontsize=size, color=rgb(spec["color"]))


def make_image(kind, student, group, out_path, fonts_used):
    spec = SPECS[kind]
    doc = fitz.open(str(TEMPLATES / spec["template"]))
    doc.select([PAGE_INDEX[kind]])
    page = doc[0]
    todo = [r for r in ERASE.get(kind, []) if page.get_text("text", clip=r).strip()]
    for r in todo:
        page.add_redact_annot(r, fill=False)
    if todo:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0))
    cache = {}
    place(page, student, spec["name"], cache, fonts_used)
    place(page, group, spec["group"], cache, fonts_used)
    
    # Render page to an image pixmap (DPI 300 for high quality)
    pix = page.get_pixmap(dpi=300)
    pix.save(str(out_path))
    doc.close()

def safe(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "student"


# --------------------------------------------------------------------------
def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Make session certificates from a Zoom chat")
    ap.add_argument("--chat", required=True, help="Zoom chat .txt file")
    ap.add_argument("--group", default="", help='group name written on every certificate, e.g. "Basics J"')
    ap.add_argument("--excellence", default="", help="names, separated by commas or new lines (or @file.txt)")
    ap.add_argument("--good-start", default="", dest="good_start")
    ap.add_argument("--improvement", default="")
    ap.add_argument("--participation-n", type=int, default=0, help="top N by message count (ties at the cutoff are all included)")
    ap.add_argument("--count-mode", choices=["both", "younes"], default="both",
                    help="both = DMs to Younes + messages to Everyone (default); younes = DMs to Younes only")
    ap.add_argument("--teacher", default="Younes Ghareeb")
    ap.add_argument("--exclude", default="", help="extra names to leave out of the participation count (comma separated)")
    ap.add_argument("--rename", default="",
                    help='fix chat names that are nicknames/emoji: "chat name=English Name; other=Name"')
    ap.add_argument("--out", default="output/certificates")
    ap.add_argument("--list-counts", action="store_true", help="print the message ranking and stop")
    a = ap.parse_args()

    msgs = parse_chat(a.chat)
    if not msgs:
        sys.exit("Could not read any messages from the chat file - is this a Zoom chat export?")
    counts, display = count_messages(msgs, a.teacher, a.count_mode, split_names(a.exclude))
    ranking = counts.most_common()

    print(f"Read {len(msgs)} messages. Message counts ({a.count_mode}):")
    for i, (k, n) in enumerate(ranking, 1):
        print(f"  {i:>2}. {display[k]:<28} {n}")
    if a.list_counts:
        return
    if not a.group.strip():
        sys.exit("Please give the group name with --group")

    # eligible names for spelling checks = everyone who appears as a sender (except the teacher)
    tt = norm(a.teacher).split()
    eligible = [k for k in display if not all(t in k for t in tt)]

    report, rows, used_keys = [], [], {}
    report += apply_renames(a.rename, display)
    selected = {"excellence": [], "good_start": [], "improvement": []}
    for kind in PRIORITY:
        for given in split_names(getattr(a, kind)):
            res = resolve_name(given, display, eligible)
            if res is None:
                continue
            final, key, status, note = res
            if key is not None and key in used_keys:
                report.append(f"DUPLICATE  '{given}' is already in {SPECS[used_keys[key]]['label']} -> skipped here (one certificate per student)")
                continue
            if key is not None:
                used_keys[key] = kind
            selected[kind].append((final, key, status, note, given))
            if status != "OK":
                report.append(f"{status:<9}  {SPECS[kind]['label']}: {note}")

    # participation: top N of the rest, ties at the cutoff included
    part = []
    if a.participation_n > 0:
        pool = [(k, n) for k, n in ranking if k not in used_keys]
        if pool:
            if len(pool) > a.participation_n:
                cutoff = pool[a.participation_n - 1][1]
                chosen = [(k, n) for k, n in pool if n >= cutoff]
            else:
                chosen = pool
                if len(pool) < a.participation_n:
                    report.append(f"NOTE       only {len(pool)} students left for Participation (you asked for {a.participation_n}) - all of them included")
            if len(chosen) > a.participation_n and len(pool) > a.participation_n:
                tied = [display[k] for k, n in chosen if n == chosen[-1][1]]
                report.append(f"TIE        cutoff tie at {chosen[-1][1]} messages -> all included: {', '.join(tied)} "
                              f"({len(chosen)} Participation certificates instead of {a.participation_n})")
            part = []
            for k, n in chosen:
                note = DISPLAY_NOTES.get(k, "")
                status = "OK" if not note else ("SKIPPED" if "no English" in note else "FIXED")
                if status == "SKIPPED":
                    report.append(f"SKIPPED    Participation: chat name '{display[k]}' has no English letters "
                                  f"({counts[k]} messages), no certificate made. "
                                  f"Give the English name with:  Rename: {display[k]} = English Name")
                elif note:
                    report.append(f"{status:<9}  Participation: {display[k]}: {note}")
                part.append((display[k], k, status, note, display[k]))
        else:
            report.append("NOTE       nobody left for Participation after the other lists")
    selected["participation"] = part

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fonts_used, made = set(), []
    for kind in ["excellence", "good_start", "improvement", "participation"]:
        for final, key, status, note, given in selected[kind]:
            if status == "SKIPPED":
                rows.append([SPECS[kind]["label"], "", display.get(key, ""), counts.get(key, 0),
                             "SKIPPED", note, ""])
                continue
            tag = "" if status in ("OK", "FIXED") else "_CHECK-NAME"
            fname = f"{SPECS[kind]['label']}_{safe(final)}{tag}.png"
            sub = out_dir / SPECS[kind]["label"]
            sub.mkdir(exist_ok=True)
            n = 2
            while (sub / fname).exists():
                fname = f"{SPECS[kind]['label']}_{safe(final)}{tag}_{n}.png"
                n += 1
            make_image(kind, final, a.group.strip(), sub / fname, fonts_used)
            made.append(sub / fname)
            rows.append([SPECS[kind]["label"], final, display.get(key, "") if key else "",
                         counts.get(key, 0) if key else "", status, note, str((sub / fname).relative_to(out_dir))])

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["certificate", "name_on_certificate", "chat_name", "messages", "name_check", "note", "file"])
        w.writerows(rows)

    lines = [f"Group: {a.group.strip()}", f"Counting mode: {a.count_mode}", ""]
    for kind in ["excellence", "good_start", "improvement", "participation"]:
        names = [x[0] for x in selected[kind] if x[2] != "SKIPPED"]
        lines.append(f"{SPECS[kind]['label']} ({len(names)}): {', '.join(names) if names else '-'}")
    lines += ["", "CHECK LIST" if report else "CHECK LIST: nothing to check"] + report
    for f in sorted(fonts_used):
        lines.append("FONT       " + f)
    (out_dir / "check_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zpath = out_dir.with_suffix(".zip") if out_dir.suffix == "" else out_dir.parent / (out_dir.name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in made + [out_dir / "summary.csv", out_dir / "check_report.txt"]:
            z.write(p, p.relative_to(out_dir))

    print("\n" + "\n".join(lines))
    print(f"\n{len(made)} certificates -> {out_dir}  (zip: {zpath})")


if __name__ == "__main__":
    main()
