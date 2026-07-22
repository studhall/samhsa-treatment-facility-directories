from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from samhsa_dirs.manifest import load_manifest
from samhsa_dirs.xlsx import load_xlsx_manifest, verify_xlsx_manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_files(paths: list[Path], destination: Path) -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED, allowZip64=True) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)


def finalize_release(
    release_dir: Path,
    pdf_dir: Path,
    xlsx_dir: Path,
    audit_path: Path,
) -> None:
    release_dir.mkdir(parents=True, exist_ok=True)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    blocked = [row["directory_year"] for row in audit if not row["archive_eligible"]]
    if blocked:
        raise ValueError(f"Source-rights audit blocks PDF years: {blocked}")

    pdf_paths = []
    for config in load_manifest():
        source = pdf_dir / config.filename
        if not source.exists():
            raise FileNotFoundError(source)
        destination = release_dir / source.name
        shutil.copy2(source, destination)
        pdf_paths.append(destination)
    archive_files(pdf_paths, release_dir / "samhsa_directory_pdfs.zip")
    shutil.copy2(audit_path, release_dir / "source_rights_audit.json")
    (release_dir / "source_pdfs.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in pdf_paths),
        encoding="utf-8",
    )

    verification = verify_xlsx_manifest(xlsx_dir)
    failed = [row["directory_year"] for row in verification if not row["checksum_ok"]]
    if failed:
        raise ValueError(f"Spreadsheet checksum verification failed: {failed}")

    xlsx_paths = []
    for config in load_xlsx_manifest():
        source = xlsx_dir / config.filename
        destination = release_dir / source.name
        shutil.copy2(source, destination)
        xlsx_paths.append(destination)
    archive_files(xlsx_paths, release_dir / "samhsa_directory_xlsx_2022_2025.zip")

    assets = sorted(
        path
        for path in release_dir.iterdir()
        if path.is_file() and path.name != "checksums.sha256"
    )
    (release_dir / "checksums.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in assets),
        encoding="utf-8",
    )
    print(f"Finalized {len(assets)} assets in {release_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--xlsx-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    finalize_release(args.release_dir, args.pdf_dir, args.xlsx_dir, args.audit)


if __name__ == "__main__":
    main()
