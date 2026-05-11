import logging
import os
from typing import Optional

from flask import Blueprint, request, jsonify

from src.services import HospitalService
from src.utils import read_csv_upload

logger = logging.getLogger(__name__)

# Shared singleton — safe because HospitalService holds no mutable instance
# state; only self.base_url is stored, which is set once and never changed.
# Instantiated here rather than per-request to avoid repeated object creation.
hospital_service = HospitalService(
    os.environ.get("HOSPITAL_API_URL", "https://hospital-directory.onrender.com")
)

hospitals_bp = Blueprint("hospitals", __name__)


@hospitals_bp.route("/hospitals/bulk", methods=["POST"])
async def bulk_create_hospitals():
    """
    Accept a CSV file and bulk-create hospitals via the upstream API.

    Workflow:
        1. Validate and read the uploaded CSV file.
        2. Parse and validate CSV rows (headers, row count, required fields).
        3. Concurrently POST each hospital to the upstream API.
        4. Activate the batch if all hospitals were created successfully.
        5. Roll back (delete batch) if any creation failed.

    Request:  multipart/form-data with a 'file' field (CSV).
              Optionally include 'batch_id' (UUID) for idempotent retries.
    Response: 201 with full processing result on success.
              400 if the CSV is invalid.
              500 on unexpected errors.
    """
    logger.info(
        "Bulk create request received: content_length=%s",
        request.content_length,
    )

    raw_content, error_response = read_csv_upload()
    if error_response is not None:
        return error_response

    # Allow callers to supply a batch_id for idempotent retries.
    # If the same batch_id is retried, already-created hospitals won't be marked active.
    batch_id: Optional[str] = request.form.get("batch_id") or None

    try:
        result = await hospital_service.process_bulk_csv(raw_content, batch_id=batch_id)
        return jsonify(result), 201
    except ValueError as e:
        logger.warning("CSV validation failed: %s", e)
        return jsonify({"error": str(e)}), 400
    except Exception:
        logger.exception("Unexpected error during bulk hospital creation")
        return jsonify({"error": "Internal server error"}), 500


@hospitals_bp.route("/hospitals/bulk/validate", methods=["POST"])
def validate_bulk_csv():
    """
    Validate a CSV file without creating any hospitals.

    Accepts the same multipart/form-data CSV upload as POST /hospitals/bulk.
    Returns a full validation report — all errors across all rows — so the
    caller can correct everything before submitting for real.

    Response shape:
        valid        — true only if the file is ready to process as-is
        total_rows   — non-blank data rows found
        valid_rows   — rows with no errors
        invalid_rows — rows that have at least one error
        errors       — [{row, field, issue}] for every problem found
        preview      — parsed representation of valid rows

    Returns 200 if valid, 422 if validation errors were found.
    """
    logger.info("CSV validate request received: content_length=%s", request.content_length)

    raw_content, error_response = read_csv_upload()
    if error_response is not None:
        return error_response

    try:
        report = HospitalService.validate_csv(raw_content)
    except Exception:
        logger.exception("Unexpected error during CSV validation")
        return jsonify({"error": "Internal server error"}), 500

    status = 200 if report["valid"] else 422
    return jsonify(report), status
