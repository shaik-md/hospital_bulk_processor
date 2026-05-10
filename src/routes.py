import logging
import os
from typing import Optional

from flask import Blueprint, request, jsonify

from src.services import HospitalService
from src.utils import _read_csv_upload

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("HOSPITAL_API_URL", "https://hospital-directory.onrender.com")

# Instantiate once at module level — not per request
hospital_service = HospitalService(BASE_URL)

bp = Blueprint("hospitals", __name__)


@bp.route("/hospitals/bulk", methods=["POST"])
async def bulk_create_hospitals():
    raw_content, error_response = _read_csv_upload()
    if error_response is not None:
        return error_response

    try:
        result = await hospital_service.process_bulk_csv(raw_content)
        return jsonify(result), 201
    except ValueError as e:
        # Raised by service for validation errors (bad headers, row count, etc.)
        logger.warning("CSV validation failed: %s", e)
        return jsonify({"error": str(e)}), 400
    except Exception:
        logger.exception("Unexpected error during bulk hospital creation")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/hospitals/bulk/validate", methods=["POST"])
def validate_bulk_csv():
    """
    Validate a CSV file without creating any hospitals.

    Accepts the same multipart/form-data CSV upload as POST /hospitals/bulk.
    Returns a full validation report — all errors across all rows — so the
    caller can correct everything before submitting for real.

    Response shape:
        valid           — true only if the file is ready to process as-is
        total_rows      — non-blank data rows found
        valid_rows      — rows with no errors
        invalid_rows    — rows that have at least one error
        errors          — [{row, field, issue}] for every problem found
        preview         — parsed representation of valid rows
    """
    raw_content, error_response = _read_csv_upload()
    if error_response is not None:
        return error_response

    report = HospitalService.validate_csv(raw_content)
    status = 200 if report["valid"] else 422
    return jsonify(report), status
