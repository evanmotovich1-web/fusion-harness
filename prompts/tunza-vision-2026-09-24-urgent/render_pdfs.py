#!/usr/bin/env python3
"""Foreground ReportLab render of the three audited urgent pages. Selectable text."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    KeepTogether,
)

ROOT = Path(__file__).resolve().parent
INK = HexColor("#1c1916")
MUTED = HexColor("#5c564c")
RULE = HexColor("#ddd4c4")
BRAND = HexColor("#4a120f")
LINK = HexColor("#1a4f8b")
CREAM = HexColor("#f4efe6")
PAGE = letter
WIDTH, HEIGHT = PAGE


WHO_URL = "https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf"
CHP_URL = "https://www.health.go.ke/node/2374"
PHRASE_LINKS = (
    ("WHO Kenya 2025, printed page 60", WHO_URL),
    ("the WHO Kenya 2025 report", WHO_URL),
    ("WHO Kenya 2025", WHO_URL),
    ("more than 107,000 Community Health Promoters", CHP_URL),
)


def linkify(text: str) -> str:
    text = html.escape(text, quote=False)
    text = text.replace("`", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    def _link(m: re.Match) -> str:
        raw = m.group(1)
        url = raw.rstrip(".,);:")
        suffix = raw[len(url) :]
        return (
            f'<link href="{url}"><font color="#1a4f8b"><u>{url}</u></font></link>'
            + suffix
        )

    text = re.sub(r"(https://[^\s<>\]]+)", _link, text)
    for phrase, url in PHRASE_LINKS:
        if phrase in text:
            text = text.replace(
                phrase,
                f'<link href="{url}"><font color="#1a4f8b"><u>{phrase}</u></font></link>',
                1,
            )
    return text


def styles_for(scale: float) -> dict[str, ParagraphStyle]:
    body_size = 9.4 * scale
    return {
        "kicker": ParagraphStyle(
            "kicker",
            fontName="Times-Italic",
            fontSize=8.2 * scale,
            leading=11 * scale,
            textColor=MUTED,
            spaceAfter=6 * scale,
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="Times-Bold",
            fontSize=16 * scale,
            leading=19 * scale,
            textColor=INK,
            spaceBefore=0,
            spaceAfter=8 * scale,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="Times-Bold",
            fontSize=10.4 * scale,
            leading=13 * scale,
            textColor=BRAND,
            spaceBefore=8 * scale,
            spaceAfter=3 * scale,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Times-Roman",
            fontSize=body_size,
            leading=body_size * 1.32,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=5 * scale,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName="Times-Roman",
            fontSize=body_size,
            leading=body_size * 1.28,
            textColor=INK,
            leftIndent=12,
            alignment=TA_LEFT,
            spaceAfter=2 * scale,
        ),
        "term": ParagraphStyle(
            "term",
            fontName="Times-Roman",
            fontSize=body_size,
            leading=body_size * 1.45,
            textColor=INK,
            spaceAfter=1 * scale,
        ),
        "sources": ParagraphStyle(
            "sources",
            fontName="Times-Roman",
            fontSize=7.6 * scale,
            leading=9.6 * scale,
            textColor=MUTED,
            spaceAfter=2 * scale,
        ),
        "footer_note": ParagraphStyle(
            "footer_note",
            fontName="Times-Italic",
            fontSize=7.6 * scale,
            leading=9.6 * scale,
            textColor=MUTED,
            spaceBefore=6 * scale,
        ),
        "banner_left": ParagraphStyle(
            "banner_left",
            fontName="Times-Bold",
            fontSize=9,
            leading=11,
            textColor=white,
        ),
        "banner_right": ParagraphStyle(
            "banner_right",
            fontName="Times-Roman",
            fontSize=7,
            leading=9,
            textColor=white,
            alignment=TA_RIGHT,
        ),
    }


def parse_markdown(md: str, st: dict[str, ParagraphStyle]) -> list:
    lines = md.splitlines()
    flow = []
    i = 0
    in_sources = False
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip():
            i += 1
            continue
        if line.strip() == "---":
            i += 1
            continue
        if line.startswith("# "):
            flow.append(Paragraph(linkify(line[2:].strip()), st["h1"]))
            i += 1
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            in_sources = title.lower() == "sources"
            flow.append(Paragraph(linkify(title), st["h2"]))
            i += 1
            continue
        if line.startswith("- "):
            bullets = []
            while i < len(lines) and lines[i].startswith("- "):
                item = lines[i][2:].strip()
                style = st["sources"] if in_sources else st["bullet"]
                bullets.append(Paragraph("• " + linkify(item), style))
                i += 1
            flow.extend(bullets)
            continue
        # term blanks: "Instrument:" with nothing after
        if re.match(r"^(Instrument|Amount|Discount or rate|What the earliest partner may join|What they do not get):$", line):
            flow.append(Paragraph(linkify(line + " ________"), st["term"]))
            i += 1
            continue
        # gather paragraph
        buf = [line.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i].rstrip()
            if not nxt.strip() or nxt.startswith("#") or nxt.startswith("- ") or nxt.strip() == "---":
                break
            if nxt.startswith("## "):
                break
            buf.append(nxt.strip())
            i += 1
        para = " ".join(buf)
        style = st["sources"] if in_sources else st["body"]
        if para.lower().startswith("reader:") or para.lower().startswith("this is for") or para.startswith("Terms are not set"):
            style = st["kicker"] if not para.startswith("Terms are not set") else st["body"]
        if para.startswith("Terms are not set"):
            style = ParagraphStyle(
                "unsent",
                parent=st["body"],
                fontName="Times-Bold",
                alignment=TA_LEFT,
                spaceAfter=4,
            )
        if para.startswith("Do not send this."):
            style = st["footer_note"]
        flow.append(Paragraph(linkify(para), style))
    return flow


def draw_chrome(canvas, doc, subtitle: str):
    canvas.saveState()
    canvas.setFillColor(CREAM)
    canvas.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(BRAND)
    canvas.rect(0, HEIGHT - 28, WIDTH, 28, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Times-Bold", 9)
    canvas.drawString(0.7 * inch, HEIGHT - 18, "TUNZA")
    canvas.setFont("Times-Roman", 7.5)
    canvas.drawRightString(WIDTH - 0.7 * inch, HEIGHT - 18, subtitle)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(0.7 * inch, 0.52 * inch, WIDTH - 0.7 * inch, 0.52 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Times-Italic", 7)
    canvas.drawString(
        0.7 * inch,
        0.36 * inch,
        "Discussion draft. Not a clinical-performance claim. Not a substitute for emergency care.",
    )
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(WIDTH - 0.7 * inch, 0.36 * inch, str(doc.page))
    canvas.restoreState()


def build_pdf(src: Path, dst: Path, subtitle: str, scale: float, top_margin: float) -> int:
    st = styles_for(scale)
    md = src.read_text(encoding="utf-8")
    story = parse_markdown(md, st)
    doc = SimpleDocTemplate(
        str(dst),
        pagesize=PAGE,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=top_margin,
        bottomMargin=0.68 * inch,
        title=src.stem.replace("-", " "),
        author="Tunza Labs",
        subject="Discussion draft — not a clinical-performance claim",
    )

    def chrome(c, d):
        draw_chrome(c, d, subtitle)

    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    raw = dst.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?!s)", raw))


def fit(src: Path, dst: Path, subtitle: str, max_pages: int, start_scale: float) -> tuple[int, float]:
    scale = start_scale
    top = 0.62 * inch
    pages = 99
    for _ in range(12):
        pages = build_pdf(src, dst, subtitle, scale, top)
        if pages <= max_pages:
            return pages, scale
        scale *= 0.94
        top = max(0.52 * inch, top - 2)
    return pages, scale


def main() -> int:
    jobs = [
        (ROOT / "friend.md", ROOT / "Tunza-friend.pdf", "FRIEND  |  DISCUSSION DRAFT  |  SEPT 2026", 2, 1.0),
        (ROOT / "general.md", ROOT / "Tunza-general.pdf", "GENERAL  |  DISCUSSION DRAFT  |  SEPT 2026", 1, 0.98),
        (ROOT / "investor-unsent.md", ROOT / "Tunza-investor-unsent.pdf", "INVESTOR  |  UNSENT  |  SEPT 2026", 2, 1.02),
    ]
    for src, dst, sub, max_pages, scale0 in jobs:
        pages, scale = fit(src, dst, sub, max_pages, scale0)
        print(f"{dst.name} pages={pages} scale={scale:.3f} bytes={dst.stat().st_size} max={max_pages} ok={pages <= max_pages}")
        if pages > max_pages:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
