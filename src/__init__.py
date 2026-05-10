"""
src/__init__.py

Application factory for the Paribus Hospital Bulk Processor.

All blueprints, extensions, and error handlers are registered here so the
app can be constructed with different configs (production, testing, etc.)
without relying on global state.
"""

import logging
import logging.config
from typing import Optional

from flask import Flask, jsonify

from src.routes import bp as hospitals_bp


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

    app.config.from_mapping(
        TESTING=False,
    )

    if config:
        app.config.update(config)

    # ── logging ───────────────────────────────────────────────────────────────
    _configure_logging()

    # ── blueprints ────────────────────────────────────────────────────────────
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
