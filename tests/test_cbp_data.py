from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from samhsa_dirs.cbp_data import read_cbp_county_archive, summarize_cbp_comparison


def write_archive(path, rows):
    csv = pd.DataFrame(rows).to_csv(index=False)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("county.csv", csv)


def source_rows():
    return [
        {"fipstate": "41", "fipscty": "001", "naics": "------", "est": 100},
        {"fipstate": "41", "fipscty": "001", "naics": "621420", "est": 4},
    ]


def test_pre_2017_absent_target_cell_is_exact_zero(tmp_path):
    path = tmp_path / "cbp16co.zip"
    write_archive(path, source_rows())

    cells = read_cbp_county_archive(path, 2016)
    residential = cells.loc[cells["naics"].eq("623220")].iloc[0]

    assert residential["establishments"] == 0
    assert residential["publication_status"] == "zero"


def test_post_2016_absent_target_cell_is_omitted_not_zero(tmp_path):
    path = tmp_path / "cbp17co.zip"
    write_archive(path, source_rows())

    cells = read_cbp_county_archive(path, 2017)
    residential = cells.loc[cells["naics"].eq("623220")].iloc[0]

    assert pd.isna(residential["establishments"])
    assert residential["publication_status"] == "omitted_or_zero"


def test_summary_leaves_unavailable_cbp_year_blank():
    comparison = pd.DataFrame(
        [
            {
                "year": 2024,
                "samhsa_count": 7,
                "cbp_count": pd.NA,
                "lower_bound": pd.NA,
                "upper_bound": pd.NA,
                "common_support": False,
                "publication_status": pd.NA,
            }
        ]
    )

    row = summarize_cbp_comparison(comparison).iloc[0]

    assert row["samhsa_count"] == 7
    assert pd.isna(row["cbp_published_count"])
    assert pd.isna(row["cbp_lower_bound"])
    assert pd.isna(row["cbp_upper_bound"])
    assert pd.isna(row["county_coverage_rate"])
