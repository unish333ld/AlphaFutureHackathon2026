"""One bounded, killable render process. stdout contains PDF bytes only."""

import json
import os
import resource
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    raw = sys.stdin.buffer.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("document input limit")
    document = json.loads(raw)
    rows = document["terms"]["schedule"]["rows"]
    if not 1 <= len(rows) <= 120:
        raise ValueError("schedule limit")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.template.loader import render_to_string
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    root = Path(os.environ.get("PDF_FONT_DIR", "/usr/share/fonts/truetype/dejavu"))
    fonts = {
        (root / "DejaVuSerif.ttf").as_uri(): (root / "DejaVuSerif.ttf").read_bytes(),
        (root / "DejaVuSerif-Bold.ttf").as_uri(): (root / "DejaVuSerif-Bold.ttf").read_bytes(),
    }

    class LocalFontsOnly(URLFetcher):
        def fetch(self, url, headers=None):
            if url not in fonts:
                raise ValueError("PDF resource denied")
            return URLFetcherResponse(url, fonts[url], {"Content-Type": "font/ttf"})

    def rub(value):
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("nonfinite amount")
        return format(number, ",.2f").replace(",", "\u00a0").replace(".", ",")

    view = {
        "doc": document,
        "date": datetime.fromisoformat(document["agreement_created_at"]).strftime("%d.%m.%Y"),
        "formed": datetime.fromisoformat(document["generated_at"]).strftime("%d.%m.%Y %H:%M UTC"),
        "amount": rub(document["terms"]["amount"]),
        "annual_rate": format(Decimal(document["terms"]["annual_rate"]).normalize(), "f").replace(
            ".", ","
        ),
        "monthly_payment": rub(document["terms"]["monthly_payment"]),
        "cost": {
            key: rub(value)
            for key, value in document["cost"].items()
            if key
            in {
                "net_disbursement",
                "principal",
                "interest_total",
                "fees_total",
                "services_total",
                "total_repayment",
                "total_cost",
                "last_payment",
                "max_payment",
            }
            and value is not None
        },
        "rows": [
            {
                "month": row["month"],
                **{key: rub(row[key]) for key in ("payment", "principal", "interest", "balance")},
            }
            for row in rows
        ],
    }
    fetcher = LocalFontsOnly()
    font_config = FontConfiguration()
    css = render_to_string(
        "agreements/contract.css", {"regular_font": next(iter(fonts)), "bold_font": list(fonts)[1]}
    )
    html = render_to_string("agreements/contract.html", view)
    pdf = HTML(string=html, url_fetcher=fetcher).write_pdf(
        stylesheets=[CSS(string=css, url_fetcher=fetcher, font_config=font_config)],
        font_config=font_config,
    )
    if len(pdf) > 4 * 1024 * 1024:
        raise ValueError("PDF output limit")
    sys.stdout.buffer.write(pdf)


if __name__ == "__main__":
    main()
