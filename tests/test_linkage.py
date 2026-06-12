import pandas as pd

from samhsa_dirs.linkage import link_facilities


def test_exact_records_link_across_years():
    facilities = pd.DataFrame(
        [
            {
                "listing_id": "L1",
                "survey_year": 2019,
                "state": "OR",
                "zip": "97401",
                "name1": "Example Recovery Center",
                "address1": "100 Main Street",
            },
            {
                "listing_id": "L2",
                "survey_year": 2020,
                "state": "OR",
                "zip": "97401",
                "name1": "Example Recovery Center",
                "address1": "100 Main St.",
            },
        ]
    )
    linked = link_facilities(facilities)
    assert linked["facility_id"].nunique() == 1

