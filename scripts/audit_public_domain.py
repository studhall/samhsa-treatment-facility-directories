from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pdfplumber

from samhsa_dirs.manifest import load_manifest

logging.disable(logging.CRITICAL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", required=True)
    parser.add_argument("--output", default="release/source_rights_audit.json")
    args = parser.parse_args()

    rows = []
    for config in load_manifest():
        path = Path(args.pdf_dir) / config.filename
        with pdfplumber.open(path) as pdf:
            pages_to_scan = min(max(config.start_page, 20), len(pdf.pages))
            page_text = [(page.extract_text() or "").upper() for page in pdf.pages[:pages_to_scan]]
        text = "\n".join(page_text)
        public_domain = "PUBLIC DOMAIN NOTICE" in text
        reproduction = "MAY BE REPRODUCED" in text or "REPRODUCED OR COPIED" in text
        fee_restriction = "DISTRIBUTED FOR A FEE" in text
        notice_page = next(
            (index for index, value in enumerate(page_text, start=1) if "PUBLIC DOMAIN" in value),
            None,
        )
        rows.append(
            {
                "directory_year": config.directory_year,
                "filename": config.filename,
                "public_domain_notice": public_domain,
                "reproduction_permission": reproduction,
                "fee_restriction_found": fee_restriction,
                "notice_pdf_page": notice_page,
                "archive_eligible": public_domain and reproduction,
                "manual_review_required": not (public_domain and reproduction),
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
