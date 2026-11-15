"""WSGI entrypoint. Gunicorn imports the module-level `app` object.

Production: `gunicorn --config gunicorn.conf.py wsgi:app`
"""

from app import create_app

app = create_app()


if __name__ == "__main__":  # pragma: no cover - development only
    app.run(host="127.0.0.1", port=8000)
