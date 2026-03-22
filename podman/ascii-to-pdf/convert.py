#!/usr/bin/env python3
"""
ASCII to PDF Converter
Converts plain text / ASCII files to PDF using ReportLab.

Usage:
    python convert.py input.txt output.pdf
    python convert.py input.txt output.pdf --font-size 12 --margin 72
"""

import argparse
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import pt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert an ASCII/plain-text file to a PDF."
    )
    parser.add_argument("input",  help="Path to the input .txt / ASCII file")
    parser.add_argument("output", help="Path for the output .pdf file")
    parser.add_argument(
        "--page-size",
        choices=["A4", "letter"],
        default="A4",
        help="Page size (default: A4)",
    )
    parser.add_argument(
        "--font-size",
        type=float,
        default=10,
        help="Font size in points (default: 10)",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=72,
        help="Page margin in points (default: 72 = 1 inch)",
    )
    parser.add_argument(
        "--preserve-whitespace",
        action="store_true",
        default=True,
        help="Preserve whitespace / monospace layout (default: True)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional document title embedded in PDF metadata",
    )
    return parser.parse_args()


def build_pdf(
    input_path: str,
    output_path: str,
    page_size=A4,
    font_size: float = 10,
    margin: float = 72,
    preserve_whitespace: bool = True,
    title: str = None,
):
    # Read the source text
    src = Path(input_path)
    if not src.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    text = src.read_text(encoding="utf-8", errors="replace")

    # Build document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title or src.stem,
        author="ascii-to-pdf",
    )

    styles = getSampleStyleSheet()

    if preserve_whitespace:
        # Preformatted keeps spaces, tabs and line breaks intact (monospace)
        code_style = ParagraphStyle(
            "ASCIICode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=font_size,
            leading=font_size * 1.2,
            textColor=colors.black,
            alignment=TA_LEFT,
            wordWrap=None,
        )
        story = [Preformatted(text, code_style)]
    else:
        # Reflow paragraphs — blank lines become spacers
        body_style = ParagraphStyle(
            "ASCIIBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=font_size,
            leading=font_size * 1.4,
            textColor=colors.black,
            alignment=TA_LEFT,
        )
        story = []
        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                # Escape XML special characters for ReportLab
                safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(safe.replace("\n", "<br/>"), body_style))
                story.append(Spacer(1, font_size * 0.8))

    doc.build(story)
    print(f"PDF written to: {output_path}")


def main():
    args = parse_args()
    page_size = A4 if args.page_size == "A4" else letter

    build_pdf(
        input_path=args.input,
        output_path=args.output,
        page_size=page_size,
        font_size=args.font_size,
        margin=args.margin,
        preserve_whitespace=args.preserve_whitespace,
        title=args.title,
    )


if __name__ == "__main__":
    main()
