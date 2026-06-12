import pandas as pd

from samhsa_dirs.release import materialize_service_status


def test_materialize_service_status_keeps_not_asked_distinct():
    facilities = pd.DataFrame(
        [
            {"listing_id": "L1", "directory_year": 2020, "survey_year": 2019},
            {"listing_id": "L2", "directory_year": 2021, "survey_year": 2020},
        ]
    )
    offered = pd.DataFrame([{"listing_id": "L1", "code": "OP"}])
    availability = pd.DataFrame(
        [
            {
                "directory_year": 2020,
                "survey_year": 2019,
                "code": "OP",
                "category": "Setting",
                "label": "Outpatient",
                "asked": True,
            },
            {
                "directory_year": 2021,
                "survey_year": 2020,
                "code": "OP",
                "category": "Setting",
                "label": "Outpatient",
                "asked": True,
            },
            {
                "directory_year": 2021,
                "survey_year": 2020,
                "code": "TELE",
                "category": "Service",
                "label": "Telehealth",
                "asked": True,
            },
        ]
    )
    status = materialize_service_status(facilities, offered, availability)
    observed = {
        (row.listing_id, row.code): row.status for row in status.itertuples(index=False)
    }
    assert observed[("L1", "OP")] == "offered"
    assert observed[("L2", "OP")] == "not_offered"
    assert observed[("L1", "TELE")] == "not_asked"
