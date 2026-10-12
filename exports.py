"""Pondside exports - the weekly PDF and the full backup bundle.

Everything lands in an exports/ folder next to the app. Nothing is uploaded;
nothing leaves the machine unless you move it yourself.

The weekly PDF is made for sharing with a therapist or keeping for you: what
helped comes first, the numbers after, and the same gentle voice as everything
else.
"""

import csv
import io
import json
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import data as pdata

HERE = Path(__file__).resolve().parent
EXPORTS_DIR = HERE / "exports"
FONTS = HERE / "assets" / "fonts" / "nunito"


def _fmt(seconds):
    """Human, kind durations - same rules as the app."""
    s = int(seconds)
    if s < 60:
        return f"{s} sec"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


def _ensure_dir(out_dir=None):
    d = Path(out_dir) if out_dir else EXPORTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def week_pdf(path=None, out_dir=None, days=7):
    """Build the one-page weekly review. Returns the PDF path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    d = _ensure_dir(out_dir)
    detail = pdata.week_detail(days, path=path)

    pdfmetrics.registerFont(TTFont("Nunito", str(FONTS / "nunito-v32-latin-regular.ttf")))
    pdfmetrics.registerFont(TTFont("Nunito-Bold", str(FONTS / "nunito-v32-latin-700.ttf")))
    pdfmetrics.registerFontFamily("Nunito", normal="Nunito", bold="Nunito-Bold")

    title_s = ParagraphStyle("t", fontName="Nunito-Bold", fontSize=22,
                             leading=28, textColor=HexColor("#2E2739"))
    sub_s = ParagraphStyle("s", fontName="Nunito", fontSize=11, leading=16,
                           textColor=HexColor("#6B6478"))
    h_s = ParagraphStyle("h", fontName="Nunito-Bold", fontSize=13.5,
                         leading=18, spaceBefore=16, spaceAfter=4,
                         textColor=HexColor("#8A6D1F"))
    b_s = ParagraphStyle("b", fontName="Nunito", fontSize=11, leading=16.5,
                         textColor=HexColor("#333333"), spaceAfter=2)
    end_s = ParagraphStyle("end", fontName="Nunito-Bold", fontSize=12,
                           leading=18, spaceBefore=18,
                           textColor=HexColor("#5A7A4A"))

    start = time.localtime(detail["since"])
    now = time.localtime()
    rng = f"{time.strftime('%b %d', start)} - {time.strftime('%b %d, %Y', now)}"
    out = d / f"pondside-week-{time.strftime('%Y-%m-%d')}.pdf"

    story = [Paragraph("Pondside - a gentle week", title_s),
             Paragraph(f"{rng} &nbsp;&middot;&nbsp; made with Peepers", sub_s),
             Spacer(1, 6),
             HRFlowable(width="100%", thickness=0.7,
                        color=HexColor("#D8D2C4"))]

    # what helped first
    helped = {}
    for (s0, s1, activity, h) in detail["sessions"]:
        if h in ("yes", "a bit"):
            helped[activity] = helped.get(activity, 0.0) + max(0.0, (s1 or s0) - s0)
    story.append(Paragraph("What helped", h_s))
    if helped:
        for activity, secs in sorted(helped.items(), key=lambda kv: -kv[1]):
            story.append(Paragraph(
                f"&bull; {escape(activity)} - {_fmt(secs)}", b_s))
    else:
        story.append(Paragraph(
            "Nothing was marked as helping this week. That is a fact, not a "
            "failure - the week is still yours.", b_s))

    # the quiet numbers
    story.append(Paragraph("The quiet numbers", h_s))
    moods = {}
    for (_ts, mood) in detail["checkins"]:
        moods[mood] = moods.get(mood, 0) + 1
    if moods:
        mood_line = ", ".join(f"{escape(m)} x{n}" for m, n in
                              sorted(moods.items(), key=lambda kv: -kv[1]))
        story.append(Paragraph(
            f"Check-ins: {len(detail['checkins'])} ({mood_line}).", b_s))
    else:
        story.append(Paragraph("No check-ins this week - that is okay.", b_s))
    story.append(Paragraph(f"Breaths taken: {detail['breaths']}.", b_s))
    total = sum(max(0.0, (s1 or s0) - s0) for (s0, s1, _a, _h) in detail["sessions"])
    story.append(Paragraph(
        f"Time tracked: {_fmt(total)} across {len(detail['sessions'])} "
        f"session{'s' if len(detail['sessions']) != 1 else ''}.", b_s))
    if detail["worries_parked"] or detail["worries_released"]:
        story.append(Paragraph(
            f"Worries parked with Peepers: {detail['worries_parked']}; "
            f"set down: {detail['worries_released']}.", b_s))

    # sessions list
    if detail["sessions"]:
        story.append(Paragraph("Sessions", h_s))
        for (s0, s1, activity, h) in detail["sessions"][-30:]:
            when = time.strftime("%a %b %d", time.localtime(s0))
            helptxt = f" - helped: {escape(h)}" if h else ""
            story.append(Paragraph(
                f"&bull; {when} - {escape(activity)} - "
                f"{_fmt((s1 or s0) - s0)}{helptxt}", b_s))

    # notes
    if detail["notes"]:
        story.append(Paragraph("Notes", h_s))
        for (ts, text) in detail["notes"][-8:]:
            when = time.strftime("%b %d", time.localtime(ts))
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:217] + "..."
            story.append(Paragraph(f"&bull; {when}: {escape(snippet)}", b_s))

    story.append(Paragraph("showing up is the whole trick.", end_s))

    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            title="Pondside - a gentle week",
                            author="Pondside")
    doc.build(story)
    return out


def backup_zip(path=None, out_dir=None):
    """Everything, in one zip: JSON + one CSV per table. Returns the zip path."""
    d = _ensure_dir(out_dir)
    out = d / f"pondside-backup-{time.strftime('%Y-%m-%d')}.zip"
    dump = pdata.dump_all(path=path)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("everything.json", json.dumps(dump, indent=2))
        for table in ("checkins", "breaths", "sessions", "notes", "worries"):
            rows = dump[table]
            buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            else:
                buf.write("(nothing here yet)\n")
            z.writestr(f"{table}.csv", buf.getvalue())
        z.writestr("README.txt",
                   "Pondside backup - your data, in your hands.\n"
                   "everything.json holds all tables; the CSVs are one "
                   "table each.\nMade with Peepers.\n")
    return out
