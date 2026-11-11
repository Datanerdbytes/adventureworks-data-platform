"""Validate the shipped analytics artifact, then start the Dash server.

The container image carries ``my-dash-app/data/analytics.duckdb``; it does not
call a remote warehouse or need Google credentials. Failing fast here keeps a
broken image from serving report pages that would only fail on first query.
"""

import os
from pathlib import Path
import sys

APP_DIRECTORY = Path(__file__).resolve().parents[1] / "my-dash-app"
DEFAULT_PORT = "8050"


def validate_analytics_artifact():
    """Raise RuntimeError unless the image contains a readable gold artifact."""
    if str(APP_DIRECTORY) not in sys.path:
        sys.path.insert(0, str(APP_DIRECTORY))
    from warehouse_client import validate_artifact

    try:
        return validate_artifact()
    except (FileNotFoundError, RuntimeError) as error:
        raise RuntimeError(f"Analytics artifact validation failed: {error}") from None


def server_command():
    """Return the Gunicorn command for the configured container port."""
    port = os.environ.get("PORT", DEFAULT_PORT)
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise RuntimeError("PORT must be an integer between 1 and 65535")
    return [
        "gunicorn",
        "--chdir",
        str(APP_DIRECTORY),
        "--bind",
        f"0.0.0.0:{port}",
        "--workers",
        "2",
        "--timeout",
        "120",
        "app:server",
    ]


def main():
    validate_analytics_artifact()
    command = server_command()
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
