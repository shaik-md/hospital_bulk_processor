from typing import Optional

from flask import request, jsonify


def _read_csv_upload() -> tuple[Optional[str], tuple]:
    """
    Shared file-reading logic for routes that accept a CSV upload.
    Returns (raw_content, error_response) — exactly one will be None.
    """
    if "file" not in request.files:
        return None, (jsonify({"error": "No file part in request"}), 400)

    upload = request.files["file"]

    if not upload.filename:
        return None, (jsonify({"error": "No file selected"}), 400)

    if not upload.filename.lower().endswith(".csv"):
        return None, (jsonify({"error": "Only CSV files are accepted"}), 415)

    try:
        raw_content = upload.read().decode("utf-8")
    except UnicodeDecodeError:
        return None, (jsonify({"error": "File must be UTF-8 encoded"}), 400)

    if not raw_content.strip():
        return None, (jsonify({"error": "Uploaded file is empty"}), 400)

    return raw_content, None
