from typing import Optional

from flask import request, jsonify
from werkzeug.utils import secure_filename

from src.constants import MAX_UPLOAD_BYTES


def read_csv_upload() -> tuple[Optional[str], Optional[tuple]]:
    """
    Shared file-reading logic for routes that accept a CSV upload.

    Validates presence, extension, encoding, size, and emptiness before
    returning the raw file content. All checks happen before the file is
    fully read into memory where possible.

    Returns:
        (raw_content, None)       on success
        (None, error_response)    on any validation failure
    """
    if "file" not in request.files:
        return None, (jsonify({"error": "No file part in request"}), 400)

    upload = request.files["file"]

    if not upload.filename:
        return None, (jsonify({"error": "No file selected"}), 400)

    # Sanitise the filename to prevent path traversal before any further use
    safe_name = secure_filename(upload.filename)
    if not safe_name.lower().endswith(".csv"):
        return None, (jsonify({"error": "Only CSV files are accepted"}), 415)

    # Check size before reading the whole file into memory.
    # seek(0, 2) moves to end of file; tell() returns the byte position.
    upload.seek(0, 2)
    file_size = upload.tell()
    upload.seek(0)  # rewind so .read() gets the full content

    if file_size > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        return None, (jsonify({"error": f"File too large. Maximum allowed size is {mb} MB."}), 413)

    try:
        raw_content = upload.read().decode("utf-8")
    except UnicodeDecodeError:
        return None, (jsonify({"error": "File must be UTF-8 encoded"}), 400)

    if not raw_content.strip():
        return None, (jsonify({"error": "Uploaded file is empty"}), 400)

    return raw_content, None
