"""Materialize runtime-only Google credentials, then start the Dash server."""

import json
import os
from pathlib import Path
import tempfile


def configure_google_credentials():
    value = os.environ.pop("GOOGLE_CREDENTIALS_JSON", "")
    if not value:
        return
    try:
        credential = json.loads(value)
        if (
            not isinstance(credential, dict)
            or credential.get("type") != "service_account"
        ):
            raise ValueError
    except ValueError:
        raise RuntimeError("Invalid runtime Google credential configuration") from None
    # mkstemp creates a private 0600 file. Never write credentials into the image.
    descriptor, filename = tempfile.mkstemp(prefix="aw-google-", suffix=".json")
    with os.fdopen(descriptor, "w") as stream:
        json.dump(credential, stream)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = filename


if __name__ == "__main__":
    configure_google_credentials()
    app_directory = Path(__file__).resolve().parents[1] / "my-dash-app"
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "--chdir",
            str(app_directory),
            "--bind",
            "0.0.0.0:8050",
            "--workers",
            "2",
            "--timeout",
            "120",
            "app:server",
        ],
    )
