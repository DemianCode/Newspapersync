"""PDF builder — renders the newspaper template with WeasyPrint.

Outputs a PDF to /app/output/newspaper-YYYY-MM-DD.pdf.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path("/app/app/templates")
_OUTPUT_DIR = Path("/app/output")

_PAPER_SIZES = {
    "A5": "@page { size: A5 portrait; margin: 12mm 14mm; }",
    "A4": "@page { size: A4 portrait; margin: 18mm 20mm; }",
}


def build(context: dict, edition_id: str | None = None) -> Path:
    """Render newspaper HTML and convert to PDF. Returns the output path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    if edition_id:
        output_path = _OUTPUT_DIR / f"newspaper-{edition_id}-{date_str}.pdf"
    else:
        output_path = _OUTPUT_DIR / f"newspaper-{date_str}.pdf"

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("newspaper.html")
    html_content = template.render(**context)

    paper_size = context.get("config", {}).get("paper_size", "A5")
    page_css = CSS(string=_PAPER_SIZES.get(paper_size, _PAPER_SIZES["A5"]))

    HTML(string=html_content, base_url=str(_TEMPLATE_DIR)).write_pdf(
        str(output_path),
        stylesheets=[page_css],
    )

    logger.info("PDF written: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
