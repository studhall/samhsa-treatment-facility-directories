import pandas as pd

from samhsa_dirs.cbp import build_cbp_comparison


def test_post_2016_omitted_cbp_cell_is_bounded_not_zero_filled():
    samhsa = pd.DataFrame(
        [{"county_fips": "41001", "state_fips": "41", "year": 2017, "samhsa_count": 3}]
    )
    cbp = pd.DataFrame(
        [
            {
                "county_fips": "41001",
                "state_fips": "41",
                "year": 2017,
                "naics": "621420",
                "establishments": 4,
                "publication_status": "published",
            },
            {
                "county_fips": "41001",
                "state_fips": "41",
                "year": 2017,
                "naics": "623220",
                "establishments": pd.NA,
                "publication_status": "omitted",
            },
        ]
    )
    output = build_cbp_comparison(samhsa, cbp).iloc[0]
    assert pd.isna(output["cbp_count"])
    assert output["lower_bound"] == 4
    assert output["upper_bound"] == 6
    assert not bool(output["common_support"])
    assert bool(output["reporting_break"])
