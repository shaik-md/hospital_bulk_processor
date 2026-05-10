"""
WSGI entry point.

Gunicorn is pointed at this file (`wsgi:app`) rather than at app.py or the
src/ package directly. This sidesteps the naming collision between app.py
and the src/ package that would occur if the package were still named "app".

Usage:
    gunicorn wsgi:app                         # production (via Dockerfile / Render)
    flask --app wsgi:app run --debug          # local development alternative
"""

from src import create_app

app = create_app()
