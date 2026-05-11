
# ── CSV processing constraints ────────────────────────────────────────────────
REQUIRED_HEADERS = {"name", "address"}
MAX_HOSPITALS: int = 20
MAX_UPLOAD_BYTES: int = 1 * 1024 * 1024  # 1 MB — well above any valid 20-row CSV

# ── upstream API ──────────────────────────────────────────────────────────────
REQUEST_TIMEOUT: float = 10
HTTP_USER_AGENT: str = "HospitalBulkProcessor/1.0"
