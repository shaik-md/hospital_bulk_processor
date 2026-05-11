import csv
import io
import uuid
import time
import asyncio
import logging
from typing import Any, Optional

import httpx

from src.constants import (REQUIRED_HEADERS, MAX_HOSPITALS, REQUEST_TIMEOUT, HTTP_USER_AGENT)

logger = logging.getLogger(__name__)


class HospitalService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _create_hospital(self, client: httpx.AsyncClient, row_index: int, row: dict[str, str], batch_id: str
                               ) -> dict[str, Any]:
        """
        POST a single hospital to the upstream API.

        Always returns a result dict — never raises — so asyncio.gather
        can collect all outcomes even when individual rows fail.

        Returns:
            {"success": True,  "data": {...}}  on HTTP 200/201
            {"success": False, "data": {...}}  on any error, with a "reason" key
        """
        # Initialised here so the final return block always has a value,
        # even if an unexpected exception bypasses all except branches.
        reason: str = "Unknown error"

        payload: dict[str, Any] = {
            "name": row["name"],
            "address": row["address"],
            "creation_batch_id": batch_id,
        }
        # Phone is optional — omit entirely rather than sending an empty string,
        if row.get("phone", "").strip():
            payload["phone"] = row["phone"].strip()

        try:
            response = await client.post(
                f"{self.base_url}/hospitals/",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code in (200, 201):
                data = response.json()
                hospital_id = data.get("id")

                # Validate the upstream response contains a usable integer id.
                if not isinstance(hospital_id, int):
                    logger.warning(
                        "Unexpected hospital id type from upstream: %r (batch=%s row=%d)",
                        hospital_id, batch_id, row_index,
                    )

                return {
                    "success": True,
                    "data": {
                        "row": row_index,
                        "hospital_id": hospital_id,
                        "name": payload["name"],
                        "status": "created",
                    },
                }

            reason = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.error(
                "Hospital creation failed: batch=%s row=%d reason=%s",
                batch_id, row_index, reason,
            )

        except httpx.TimeoutException:
            reason = "Request timed out"
            logger.error("Hospital creation timed out: batch=%s row=%d", batch_id, row_index)

        except httpx.RequestError as exc:
            reason = f"Network error: {exc}"
            logger.error(
                "Hospital creation network error: batch=%s row=%d reason=%s",
                batch_id, row_index, reason,
            )

        except Exception as exc:
            reason = f"Unexpected error: {exc}"
            logger.exception(
                "Hospital creation unexpected exception: batch=%s row=%d",
                batch_id, row_index,
            )

        return {
            "success": False,
            "data": {
                "row": row_index,
                "hospital_id": None,
                "name": payload["name"],
                "status": "failed",
                "reason": reason,
            },
        }

    async def _rollback_batch(self, client: httpx.AsyncClient, batch_id: str) -> None:
        """
        Delete all hospitals in a partially-created batch.

        Called when some hospital creations succeed and others fail to avoid
        leaving inactive orphaned records in the upstream system.
        Logs on failure but never raises — rollback failure is non-fatal.
        """
        try:
            response = await client.delete(
                f"{self.base_url}/hospitals/batch/{batch_id}",
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code in (200, 204):
                logger.info("Batch rolled back successfully: batch=%s", batch_id)
            else:
                logger.error(
                    "Batch rollback returned unexpected status: batch=%s status=%d",
                    batch_id, response.status_code,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Batch rollback failed — manual cleanup may be needed: batch=%s",
                batch_id,
            )

    @staticmethod
    def _parse_and_validate_csv(content: str) -> list[dict[str, str]]:
        """
        Parse a raw CSV string into a list of normalised row dicts.

        Raises ValueError on any structural or row-level problem so the
        caller can return a 400 immediately without touching the upstream API.
        """
        reader = csv.DictReader(io.StringIO(content))

        if not reader.fieldnames:
            raise ValueError("CSV file has no headers.")

        normalised_headers = {h.strip().lower() for h in reader.fieldnames}
        missing = REQUIRED_HEADERS - normalised_headers
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}."
            )

        rows = [
            {k.strip().lower(): v.strip() for k, v in row.items()}
            for row in reader
            if any(v.strip() for v in row.values())  # skip fully blank rows
        ]

        if not rows:
            raise ValueError("CSV file contains no data rows.")

        if len(rows) > MAX_HOSPITALS:
            raise ValueError(
                f"CSV exceeds the {MAX_HOSPITALS}-hospital limit. Found: {len(rows)}."
            )

        for i, row in enumerate(rows, start=1):
            if not row.get("name"):
                raise ValueError(f"Row {i}: 'name' must not be empty.")
            if not row.get("address"):
                raise ValueError(f"Row {i}: 'address' must not be empty.")

        return rows

    @staticmethod
    def validate_csv(content: str) -> dict[str, Any]:
        """
        Validate a raw CSV string and return a full report.

        Unlike _parse_and_validate_csv, this method never raises — it collects
        every error across every row so the caller can fix them all at once
        without repeated submit-fix-resubmit cycles.

        Returns:
            valid        — True only when the file is ready to be processed as-is
            total_rows   — non-blank data rows found
            valid_rows   — count of rows with no errors
            invalid_rows — count of rows with at least one error
            errors       — [{row, field, issue}] for every problem found
            preview      — parsed representation of valid rows
        """
        errors: list[dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(content))

        if not reader.fieldnames:
            return {
                "valid": False, "total_rows": 0, "valid_rows": 0, "invalid_rows": 0,
                "errors": [{"row": None, "field": "headers", "issue": "CSV has no header row."}],
                "preview": [],
            }

        normalised_headers = {h.strip().lower() for h in reader.fieldnames}
        missing_headers = REQUIRED_HEADERS - normalised_headers
        if missing_headers:
            return {
                "valid": False, "total_rows": 0, "valid_rows": 0, "invalid_rows": 0,
                "errors": [{
                    "row": None,
                    "field": "headers",
                    "issue": f"Missing required column(s): {', '.join(sorted(missing_headers))}.",
                }],
                "preview": [],
            }

        all_rows = [
            {k.strip().lower(): v.strip() for k, v in row.items()}
            for row in reader
        ]
        non_blank_rows = [r for r in all_rows if any(v for v in r.values())]
        total_rows = len(non_blank_rows)

        if total_rows == 0:
            return {
                "valid": False, "total_rows": 0, "valid_rows": 0, "invalid_rows": 0,
                "errors": [{"row": None, "field": None, "issue": "CSV contains no data rows."}],
                "preview": [],
            }

        if total_rows > MAX_HOSPITALS:
            errors.append({
                "row": None,
                "field": None,
                "issue": (
                    f"CSV exceeds the {MAX_HOSPITALS}-hospital limit. "
                    f"Found {total_rows} rows — remove {total_rows - MAX_HOSPITALS} row(s)."
                ),
            })

        invalid_row_indices: set[int] = set()

        for i, row in enumerate(non_blank_rows, start=1):
            if not row.get("name"):
                errors.append({"row": i, "field": "name", "issue": "'name' must not be empty."})
                invalid_row_indices.add(i)
            if not row.get("address"):
                errors.append({"row": i, "field": "address", "issue": "'address' must not be empty."})
                invalid_row_indices.add(i)

        preview: list[dict[str, Any]] = []
        for i, row in enumerate(non_blank_rows, start=1):
            if i not in invalid_row_indices and i <= MAX_HOSPITALS:
                entry: dict[str, Any] = {"row": i, "name": row["name"], "address": row["address"]}
                if row.get("phone"):
                    entry["phone"] = row["phone"]
                preview.append(entry)

        return {
            "valid": len(errors) == 0,
            "total_rows": total_rows,
            "valid_rows": len(preview),
            "invalid_rows": len(invalid_row_indices),
            "errors": errors,
            "preview": preview,
        }

    async def process_bulk_csv(self, file_content: str, batch_id: Optional[str] = None) -> dict[str, Any]:
        """
        Parse a CSV string and bulk-create hospitals via the upstream API.

        Args:
            file_content: Raw UTF-8 CSV string.
            batch_id:     Optional caller-supplied UUID for idempotent retries.
                          If provided, the upstream will skip hospitals that
                          already exist under this batch_id.

        Returns:
            A dict matching the BulkResponse schema with per-hospital results.

        Raises:
            ValueError: If the CSV fails structural or row-level validation.
        """
        start_time = time.perf_counter()
        batch_id = batch_id or str(uuid.uuid4())

        rows = self._parse_and_validate_csv(file_content)
        total_rows = len(rows)

        logger.info(
            "Bulk processing started: batch=%s rows=%d",
            batch_id, total_rows,
        )

        results: list[dict[str, Any]] = []
        processed_count = 0
        failed_count = 0

        # Performance note: a single AsyncClient is created for the entire
        # bulk operation so all concurrent hospital POSTs share one connection
        # pool. This is the correct scope for Flask WSGI + flask[async]:
        # asgiref creates a new event loop per async request, so the client
        # must be created inside that loop, not shared across requests.
        async with httpx.AsyncClient(
            headers={"User-Agent": HTTP_USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        ) as client:

            # Concurrently create all hospitals — the primary performance gain.
            # return_exceptions=True prevents one failure from cancelling all tasks.
            tasks = [
                self._create_hospital(client, i, row, batch_id)
                for i, row in enumerate(rows, start=1)
            ]
            creation_results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in creation_results:
                if isinstance(res, Exception):
                    failed_count += 1
                    logger.error(
                        "Unexpected exception escaped gather: batch=%s error=%s",
                        batch_id, res,
                    )
                    continue

                results.append(res["data"])
                if res["success"]:
                    processed_count += 1
                else:
                    failed_count += 1

            batch_activated = False

            if failed_count == 0 and processed_count > 0:
                try:
                    activate_res = await client.patch(
                        f"{self.base_url}/hospitals/batch/{batch_id}/activate",
                        timeout=REQUEST_TIMEOUT,
                    )
                    if activate_res.status_code == 200:
                        batch_activated = True
                        for item in results:
                            item["status"] = "created_and_activated"
                        logger.info("Batch activated: batch=%s", batch_id)
                    else:
                        logger.error(
                            "Batch activation failed: batch=%s status=%d body=%s",
                            batch_id,
                            activate_res.status_code,
                            activate_res.text[:200],
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("Batch activation exception: batch=%s", batch_id)

            elif failed_count > 0 and processed_count > 0:
                # Partial failure — roll back to avoid orphaned inactive records.
                logger.warning(
                    "Partial failure detected — rolling back batch: batch=%s "
                    "processed=%d failed=%d",
                    batch_id, processed_count, failed_count,
                )
                await self._rollback_batch(client, batch_id)

        elapsed = round(time.perf_counter() - start_time, 2)
        logger.info(
            "Bulk processing complete: batch=%s processed=%d failed=%d "
            "activated=%s time=%.2fs",
            batch_id, processed_count, failed_count, batch_activated, elapsed,
        )

        return {
            "batch_id": batch_id,
            "total_hospitals": total_rows,
            "processed_hospitals": processed_count,
            "failed_hospitals": failed_count,
            "processing_time_seconds": elapsed,
            "batch_activated": batch_activated,
            "hospitals": results,
        }
