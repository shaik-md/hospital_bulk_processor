import pytest
from src.services import HospitalService


def test_parse_valid_csv():
    csv_data = "name,address\nTest Hospital,123 Test St\n"
    rows = HospitalService._parse_and_validate_csv(csv_data)
    assert len(rows) == 1
    assert rows[0]["name"] == "Test Hospital"
    assert rows[0]["address"] == "123 Test St"


def test_parse_missing_headers():
    csv_data = "name,phone\nTest Hospital,555-1234\n"
    with pytest.raises(ValueError, match="missing required columns"):
        HospitalService._parse_and_validate_csv(csv_data)


def test_parse_exceeds_limit():
    # Create 21 rows
    csv_data = "name,address\n" + "\n".join([f"Hosp {i},Addr {i}" for i in range(21)])
    with pytest.raises(ValueError, match="exceeds the 20-hospital limit"):
        HospitalService._parse_and_validate_csv(csv_data)


def test_validate_csv_report():
    # Mix of valid and invalid rows
    csv_data = "name,address\nValid Hosp,123 St\n,Missing Name\nValid Two,456 St"
    report = HospitalService.validate_csv(csv_data)

    assert report["valid"] is False
    assert report["total_rows"] == 3
    assert report["valid_rows"] == 2
    assert report["invalid_rows"] == 1
    assert len(report["errors"]) == 1
    assert report["errors"][0]["issue"] == "'name' must not be empty."
