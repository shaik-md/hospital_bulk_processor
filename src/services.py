import csv
import io
import uuid
import time
import asyncio
import logging
from typing import Any

import httpx

from src.constants import REQUIRED_HEADERS, MAX_HOSPITALS

logger = logging.getLogger(__name__)


class HospitalService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _create_hospital(self, client: httpx.AsyncClient, row_index: int, row: dict[str, str], batch_id: str
                               ) -> dict[str, Any]:
        """
        POST a single hospital to the upstream API.
        Always returns a result dict — never raises.
        Keys: success (bool), data (dict with row details).
        """
        payload: dict[str, Any] = {
            "name": row["name"],
            "address": row["address"],
            "creation_batch_id": batch_id,
        }
        if row.get("phone", "").strip():
            payload["phone"] = row["phone"].strip()

        try:
            response = await client.post(
                f"{self.base_url}/hospitals/",
                json=payload,
                timeout=10.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                return {
                    "success": True,
                    "data": {
                        "row": row_index,
                        "hospital_id": data.get("id"),
                        "name": payload["name"],
                        "status": "created",
                    },
                }
            reason = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.error("Row %d failed: %s", row_index, reason)
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
        except httpx.TimeoutException:
            reason = "Request timed out"
            logger.error("Row %d timed out", row_index)
        except Exception as e:  # noqa: BLE001
            reason = str(e)
            logger.exception("Row %d raised an unexpected exception", row_index)

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

    @staticmethod
    def _parse_and_validate_csv(content: str) -> list[dict[str, str]]:
        """
        Parse raw CSV string into a list of normalised row dicts.
        Raises ValueError on structural problems.
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

        # Row-level validation
        for i, row in enumerate(rows, start=1):
            if not row.get("name"):
                raise ValueError(f"Row {i}: 'name' must not be empty.")
            if not row.get("address"):
                raise ValueError(f"Row {i}: 'address' must not be empty.")

        return rows

    @staticmethod
    def validate_csv(content: str) -> dict[str, Any]:
        """
        Validate a raw CSV string and return a full report without hitting
        the upstream API or creating anything.

        Unlike _parse_and_validate_csv, this method never raises — it collects
        every error across every row so the caller can fix them all at once.

        Returns a dict with:
            valid           — True only if the file is ready to be processed as-is
            total_rows      — number of non-blank data rows found
            valid_rows      — rows with no errors
            invalid_rows    — rows with at least one error
            errors          — list of {row, field, issue} for every problem found
            preview         — list of valid rows showing how they would be parsed
        """
        errors: list[dict[str, Any]] = []

        # ------------------------------------------------------------------ #
        # 1. Structural checks — stop early if the file itself is unparseable #
        # ------------------------------------------------------------------ #
        reader = csv.DictReader(io.StringIO(content))

        if not reader.fieldnames:
            return {
                "valid": False,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "errors": [{"row": None, "field": "headers", "issue": "CSV has no header row."}],
                "preview": [],
            }

        normalised_headers = {h.strip().lower() for h in reader.fieldnames}
        missing_headers = REQUIRED_HEADERS - normalised_headers
        if missing_headers:
            return {
                "valid": False,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "errors": [
                    {
                        "row": None,
                        "field": "headers",
                        "issue": f"Missing required column(s): {', '.join(sorted(missing_headers))}.",
                    }
                ],
                "preview": [],
            }

        # Normalise all keys once
        all_rows = [
            {k.strip().lower(): v.strip() for k, v in row.items()}
            for row in reader
        ]
        # Exclude fully blank rows (blank lines at end of file, etc.)
        non_blank_rows = [r for r in all_rows if any(v for v in r.values())]
        total_rows = len(non_blank_rows)

        if total_rows == 0:
            return {
                "valid": False,
                "total_rows": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "errors": [{"row": None, "field": None, "issue": "CSV contains no data rows."}],
                "preview": [],
            }

        if total_rows > MAX_HOSPITALS:
            errors.append({
                "row": None,
                "field": None,
                "issue": (
                    f"CSV exceeds the {MAX_HOSPITALS}-hospital limit. "
                    f"Found {total_rows} rows. Remove {total_rows - MAX_HOSPITALS} row(s)."
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

        preview = []
        for i, row in enumerate(non_blank_rows, start=1):
            if i not in invalid_row_indices and i <= MAX_HOSPITALS:
                entry: dict[str, Any] = {"row": i, "name": row["name"], "address": row["address"]}
                if row.get("phone"):
                    entry["phone"] = row["phone"]
                preview.append(entry)

        valid_row_count = len(preview)
        invalid_row_count = len(invalid_row_indices)

        return {
            "valid": len(errors) == 0,
            "total_rows": total_rows,
            "valid_rows": valid_row_count,
            "invalid_rows": invalid_row_count,
            "errors": errors,
            "preview": preview,
        }

    async def process_bulk_csv(self, file_content: str) -> dict[str, Any]:
        start_time = time.perf_counter()
        batch_id = str(uuid.uuid4())

        rows = self._parse_and_validate_csv(file_content)
        total_rows = len(rows)

        results: list[dict[str, Any]] = []
        processed_count = 0
        failed_count = 0

        async with httpx.AsyncClient(
            headers={"User-Agent": "HospitalBulkProcessor/1.0"}
        ) as client:
            tasks = [
                self._create_hospital(client, i, row, batch_id)
                for i, row in enumerate(rows, start=1)
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in raw_results:
                if isinstance(res, Exception):
                    failed_count += 1
                    logger.error("Unexpected exception from gather: %s", res)
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
                        timeout=10.0,
                    )
                    if activate_res.status_code == 200:
                        batch_activated = True
                        for item in results:
                            item["status"] = "created_and_activated"
                    else:
                        logger.error(
                            "Batch activation returned HTTP %d: %s",
                            activate_res.status_code,
                            activate_res.text[:200],
                        )
                except Exception:
                    logger.exception("Batch activation failed for batch %s", batch_id)

        return {
            "batch_id": batch_id,
            "total_hospitals": total_rows,
            "processed_hospitals": processed_count,
            "failed_hospitals": failed_count,
            "processing_time_seconds": round(time.perf_counter() - start_time, 2),
            "batch_activated": batch_activated,
            "hospitals": results,
        }
