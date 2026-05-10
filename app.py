"""
app.py — local development entry point.

    flask --app app run --debug --port 8000

Production uses wsgi.py via gunicorn instead of this file.
"""

from src import create_app

app = create_app()