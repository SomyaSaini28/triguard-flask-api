"""WSGI entry point for the TriGuard Flask application."""

from api.application import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
