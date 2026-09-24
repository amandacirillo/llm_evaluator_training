"""Gunicorn entry point for production."""
from demo.server.app import create_app

app = create_app()
