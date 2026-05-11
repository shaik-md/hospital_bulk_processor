import io


def test_bulk_upload_no_file(client):
    response = client.post("/hospitals/bulk")
    assert response.status_code == 400
    assert "No file part" in response.json["error"]


def test_bulk_upload_bad_extension(client):
    data = {"file": (io.BytesIO(b"test data"), "test.txt")}
    response = client.post("/hospitals/bulk", data=data, content_type="multipart/form-data")
    assert response.status_code == 415
    assert "Only CSV files" in response.json["error"]


def test_validate_endpoint_success(client, valid_csv_bytes):
    data = {"file": (io.BytesIO(valid_csv_bytes), "test.csv")}
    response = client.post("/hospitals/bulk/validate", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert response.json["valid"] is True
    assert response.json["total_rows"] == 2
