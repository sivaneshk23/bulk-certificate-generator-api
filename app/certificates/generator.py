from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FontSet:
    regular: str
    bold: str
    tamil: str
    cjk: str
    tamil_supported: bool


_FONTS: FontSet | None = None


def _first_existing(*paths: str | Path | None) -> str | None:
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.is_file():
            return str(path)
    return None


def _discover_font(filename: str) -> str | None:
    candidates = [
        Path("/usr/share/fonts/truetype/noto") / filename,
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/local/share/fonts") / filename,
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename,
    ]
    return _first_existing(*candidates)


def _load_fonts() -> FontSet:
    global _FONTS
    if _FONTS is not None:
        return _FONTS

    regular_path = _first_existing(
        settings.font_regular_path,
        _discover_font("NotoSans-Regular.ttf"),
        _discover_font("DejaVuSans.ttf"),
    )
    bold_path = _first_existing(
        settings.font_bold_path,
        _discover_font("NotoSans-Bold.ttf"),
        _discover_font("DejaVuSans-Bold.ttf"),
    )
    tamil_path = _first_existing(
        settings.font_tamil_path,
        _discover_font("NotoSansTamil-Regular.ttf"),
        _discover_font("NotoSerifTamil-Regular.ttf"),
    )

    if not regular_path:
        logger.warning("No external regular Unicode font found; using built-in Helvetica.")
        regular_name = "Helvetica"
    else:
        if "BCG-Regular" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("BCG-Regular", regular_path))
        regular_name = "BCG-Regular"

    if not bold_path:
        logger.warning("No external bold Unicode font found; using built-in Helvetica-Bold.")
        bold_name = "Helvetica-Bold"
    else:
        if "BCG-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("BCG-Bold", bold_path))
        bold_name = "BCG-Bold"

    if tamil_path:
        if "BCG-Tamil" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("BCG-Tamil", tamil_path))
        tamil_name = "BCG-Tamil"
        tamil_supported = True
    else:
        tamil_name = regular_name
        tamil_supported = False
        logger.warning(
            "Tamil font not found. Tamil text will use the configured regular font. "
            "The Docker image installs Noto Sans Tamil automatically."
        )

    if "BCG-CJK" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    _FONTS = FontSet(
        regular=regular_name,
        bold=bold_name,
        tamil=tamil_name,
        cjk="STSong-Light",
        tamil_supported=tamil_supported,
    )
    return _FONTS


def _font_for_char(char: str, fonts: FontSet, *, bold: bool = False) -> str:
    codepoint = ord(char)
    if 0x0B80 <= codepoint <= 0x0BFF and fonts.tamil_supported:
        return fonts.tamil
    if (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0x3000 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    ):
        return fonts.cjk
    return fonts.bold if bold else fonts.regular


def _segments(text: str, fonts: FontSet, *, bold: bool = False) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    current_font: str | None = None
    current: list[str] = []
    for char in text:
        font = _font_for_char(char, fonts, bold=bold)
        if current and font != current_font:
            result.append((current_font or fonts.regular, "".join(current)))
            current = []
        current_font = font
        current.append(char)
    if current:
        result.append((current_font or fonts.regular, "".join(current)))
    return result


def _measure(text: str, fonts: FontSet, font_size: float, *, bold: bool = False) -> float:
    return sum(
        pdfmetrics.stringWidth(chunk, font, font_size)
        for font, chunk in _segments(text, fonts, bold=bold)
    )


def _wrap_text(
    text: str,
    fonts: FontSet,
    font_size: float,
    max_width: float,
    *,
    bold: bool = False,
    max_lines: int | None = None,
) -> list[str]:
    if not text:
        return [""]

    paragraphs = text.splitlines() or [""]
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if _measure(candidate, fonts, font_size, bold=bold) <= max_width or not current:
                current = candidate
                continue

            lines.append(current)
            current = word

            if _measure(current, fonts, font_size, bold=bold) > max_width:
                pieces: list[str] = []
                chunk = ""
                for char in current:
                    candidate_char = chunk + char
                    if chunk and _measure(candidate_char, fonts, font_size, bold=bold) > max_width:
                        pieces.append(chunk)
                        chunk = char
                    else:
                        chunk = candidate_char
                if chunk:
                    pieces.append(chunk)
                lines.extend(pieces[:-1])
                current = pieces[-1] if pieces else ""

        lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        kept = lines[: max_lines - 1]
        remainder = " ".join(lines[max_lines - 1 :])
        ellipsis = "…"
        if _measure(remainder, fonts, font_size, bold=bold) > max_width:
            while (
                remainder
                and _measure(remainder + ellipsis, fonts, font_size, bold=bold) > max_width
            ):
                remainder = remainder[:-1]
        kept.append((remainder + ellipsis) if remainder else ellipsis)
        lines = kept
    return lines


def _draw_centered_lines(
    c: canvas.Canvas,
    lines: list[str],
    *,
    center_x: float,
    center_y: float,
    fonts: FontSet,
    font_size: float,
    color: colors.Color,
    leading: float,
    bold: bool = False,
) -> float:
    total_height = leading * len(lines)
    baseline = center_y + total_height / 2 - leading
    c.setFillColor(color)
    for line in lines:
        width = _measure(line, fonts, font_size, bold=bold)
        x = center_x - width / 2
        for font_name, chunk in _segments(line, fonts, bold=bold):
            c.setFont(font_name, font_size)
            c.drawString(x, baseline, chunk)
            x += pdfmetrics.stringWidth(chunk, font_name, font_size)
        baseline -= leading
    return total_height


def _draw_adaptive_text(
    c: canvas.Canvas,
    text: str,
    *,
    center_x: float,
    center_y: float,
    width: float,
    fonts: FontSet,
    max_size: int,
    min_size: int,
    color: colors.Color,
    bold: bool = False,
    max_lines: int = 2,
    leading_factor: float = 1.25,
) -> None:
    for size in range(max_size, min_size - 1, -1):
        leading = size * leading_factor
        lines = _wrap_text(text, fonts, size, width, bold=bold, max_lines=None)
        if len(lines) <= max_lines:
            _draw_centered_lines(
                c,
                lines,
                center_x=center_x,
                center_y=center_y,
                fonts=fonts,
                font_size=size,
                color=color,
                leading=leading,
                bold=bold,
            )
            return

    size = min_size
    lines = _wrap_text(text, fonts, size, width, bold=bold, max_lines=max_lines)
    _draw_centered_lines(
        c,
        lines,
        center_x=center_x,
        center_y=center_y,
        fonts=fonts,
        font_size=size,
        color=color,
        leading=size * leading_factor,
        bold=bold,
    )


def _draw_label_value(
    c: canvas.Canvas,
    label: str,
    value: str,
    *,
    center_x: float,
    center_y: float,
    width: float,
    fonts: FontSet,
) -> None:
    full = f"{label}: {value}"
    lines = _wrap_text(full, fonts, 11, width, max_lines=2)
    _draw_centered_lines(
        c,
        lines,
        center_x=center_x,
        center_y=center_y,
        fonts=fonts,
        font_size=11,
        color=colors.HexColor("#555555"),
        leading=14,
    )


def generate_certificate_pdf(
    output_path: Path,
    certificate_id: str,
    recipient_name: str,
    title: str,
    course_name: str,
    completion_date: date | None,
    issuer_name: str,
    issuer_designation: str | None,
) -> None:
    fonts = _load_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 15 * mm

    c.setStrokeColor(colors.HexColor("#1F4E79"))
    c.setLineWidth(2.2)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin, stroke=1, fill=0)
    c.setStrokeColor(colors.HexColor("#C9A227"))
    c.setLineWidth(0.8)
    c.rect(
        margin + 4 * mm,
        margin + 4 * mm,
        width - 2 * margin - 8 * mm,
        height - 2 * margin - 8 * mm,
        stroke=1,
        fill=0,
    )

    _draw_adaptive_text(
        c,
        title,
        center_x=width / 2,
        center_y=height - 40 * mm,
        width=width - 70 * mm,
        fonts=fonts,
        max_size=26,
        min_size=18,
        color=colors.HexColor("#1F4E79"),
        bold=True,
        max_lines=2,
    )
    _draw_adaptive_text(
        c,
        "This certificate is proudly presented to",
        center_x=width / 2,
        center_y=height - 55 * mm,
        width=width - 90 * mm,
        fonts=fonts,
        max_size=12,
        min_size=10,
        color=colors.HexColor("#555555"),
        max_lines=1,
    )
    _draw_adaptive_text(
        c,
        recipient_name,
        center_x=width / 2,
        center_y=height - 75 * mm,
        width=width - 70 * mm,
        fonts=fonts,
        max_size=28,
        min_size=16,
        color=colors.HexColor("#111111"),
        bold=True,
        max_lines=2,
        leading_factor=1.18,
    )
    _draw_adaptive_text(
        c,
        f"for successful completion of {course_name}",
        center_x=width / 2,
        center_y=height - 99 * mm,
        width=width - 75 * mm,
        fonts=fonts,
        max_size=14,
        min_size=10,
        color=colors.HexColor("#333333"),
        max_lines=2,
    )

    completion_text = completion_date.isoformat() if completion_date else ""
    _draw_label_value(
        c,
        "Completion date",
        completion_text,
        center_x=width / 2,
        center_y=47 * mm,
        width=70 * mm,
        fonts=fonts,
    )
    _draw_label_value(
        c,
        "Certificate ID",
        certificate_id,
        center_x=width / 2,
        center_y=37 * mm,
        width=90 * mm,
        fonts=fonts,
    )

    left_x = margin + 45 * mm
    right_x = width - margin - 45 * mm
    c.setStrokeColor(colors.HexColor("#777777"))
    c.setLineWidth(0.7)
    c.line(left_x - 28 * mm, 33 * mm, left_x + 28 * mm, 33 * mm)
    c.line(right_x - 28 * mm, 33 * mm, right_x + 28 * mm, 33 * mm)
    _draw_adaptive_text(
        c,
        issuer_name,
        center_x=left_x,
        center_y=26 * mm,
        width=70 * mm,
        fonts=fonts,
        max_size=11,
        min_size=8,
        color=colors.HexColor("#333333"),
        bold=True,
        max_lines=1,
    )
    _draw_adaptive_text(
        c,
        issuer_designation or "Issuer",
        center_x=right_x,
        center_y=26 * mm,
        width=70 * mm,
        fonts=fonts,
        max_size=11,
        min_size=8,
        color=colors.HexColor("#333333"),
        max_lines=1,
    )

    c.showPage()
    c.save()
