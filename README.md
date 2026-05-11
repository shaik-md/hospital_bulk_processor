# Paribus Hospital Bulk Processor

A high-performance, asynchronous Python backend designed to handle bulk hospital creation via CSV uploads. Built with Flask and HTTPX, this service acts as a robust middleware, processing concurrent API requests while ensuring strict data validation and graceful error recovery.

## 🚀 Live Demo & Documentation

* **Live Deployment (Render):** [https://hospital-bulk-processor-1.onrender.com/](https://hospital-bulk-processor-1.onrender.com/)
* **Interactive API Docs (Swagger UI):** [https://hospital-bulk-processor-1.onrender.com/api/docs](https://hospital-bulk-processor-1.onrender.com/api/docs)

> **Note on Deployment:** This application is hosted on Render's free tier. If the service has been inactive for 15 minutes, the very first request may take ~50 seconds to complete as the instance wakes up. Subsequent requests will be lightning-fast.

---

## 🏗️ Architecture & Key Features

* **Asynchronous Processing:** Utilizes `asyncio` and `httpx` to process up to 20 hospital creations concurrently, significantly reducing overall batch processing time compared to synchronous loops.
* **Stateless Idempotent Retries:** Implements a highly resilient resume mechanism using HTTP 207 (Multi-Status) and `batch_id` idempotency. Partial network failures are suspended rather than rolled back, allowing users to re-upload the same CSV to seamlessly resume processing without requiring a local database or Redis instance.
* **Application Factory Pattern:** Structured using Flask's application factory (`src/__init__.py`) for clean separation of concerns, modular routing, and simplified testing environments.
* **Strict Validation:** Includes a dry-run `/validate` endpoint that parses the CSV and returns a comprehensive report of all row-level errors in a single pass, preventing partial-write scenarios caused by bad data.
* **100% Test Coverage:** Comprehensive test suite utilizing `pytest` and `respx` with a custom catch-all callback routing pattern to guarantee robust, stateful network mocking independent of internal HTTP library URL normalization.

---

## 🛠️ Tech Stack

* **Framework:** Python 3.9+, Flask
* **Async HTTP Client:** HTTPX
* **Testing:** Pytest, Pytest-Asyncio, Pytest-Cov, RESPX
* **Documentation:** OpenAPI 3.0 (Swagger UI)
* **Production Server:** Gunicorn

---

## 💻 Local Development Setup

### 1. Prerequisites
Ensure you have Python 3.9+ installed on your machine.

### 2. Clone the Repository
```bash
git clone [https://github.com/shaik-md/hospital_bulk_processor.git](https://github.com/shaik-md/hospital_bulk_processor.git)
cd hospital_bulk_processor
