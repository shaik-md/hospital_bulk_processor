"""Application factory for the Paribus Hospital Bulk Processor.

All blueprints, extensions, and error handlers are registered here so the
app can be constructed with different configs (production, testing, etc.)
without relying on global state.

Performance note — httpx.AsyncClient lifecycle:
    Flask WSGI + flask[async] (asgiref) creates a new event loop per async
    request. Sharing a single AsyncClient across requests would bind it to
    the first request's event loop and cause "Future attached to a different
    loop" errors on subsequent requests. The correct pattern is a per-request
    client inside an `async with` block, which is what services.py does.
    Connection-level performance is still gained within a single bulk request
    because all 20 hospital POSTs share one client and its connection pool.
"""

import logging
import logging.config
import os
from typing import Optional

from flask import Flask, jsonify


def create_app(config: Optional[dict] = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config: Optional dict of config overrides — used by the test suite
                to pass {'TESTING': True} without touching the environment.

    Returns:
        A fully configured Flask application instance.
    """
    app = Flask(__name__)

    # ── load config ───────────────────────────────────────────────────────────
    # Raise immediately if the required env var is missing so misconfigured
    # deployments fail at startup, not silently at request time.
    app.config.from_mapping(
        TESTING=False,
        HOSPITAL_API_URL=_require_env("HOSPITAL_API_URL"),
    )

    if config:
        app.config.update(config)

    # ── logging ───────────────────────────────────────────────────────────────
    _configure_logging()

    # ── blueprints ────────────────────────────────────────────────────────────
    # Import here to avoid circular imports at module load time.
    from src.routes import hospitals_bp  # noqa: PLC0415
    app.register_blueprint(hospitals_bp)

    # ── global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return jsonify({"error": "Method not allowed"}), 405

    # ── health check ──────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app


def _require_env(key: str) -> str:
    """
    Return the value of an environment variable or raise at startup.
    Prevents silent fallback to production URLs in misconfigured environments.
    """
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            "Check your .env file or deployment config."
        )
    return value


def _configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "level": "INFO",
                "handlers": ["console"],
            },
        }
    )
