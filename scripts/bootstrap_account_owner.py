"""Assign the initial protected owner to an existing verified Supabase account.

Run from the repository root. This is an explicit operator command, never startup
behavior; without --apply it only verifies the proposed account and owner state.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "my-dash-app"))

from user_admin import (  # noqa: E402 - sibling Dash module path is added above
    AdminError,
    _service_request,
)


def bootstrap(email, apply=False):
    email = email.strip().casefold()
    if not email or "@" not in email:
        raise ValueError("Provide the email of an existing verified account.")
    target = None
    owners = []
    for page in range(1, 401):
        result = _service_request("GET", f"?page={page}&per_page=25")
        users = result.get("users")
        if not isinstance(users, list) or len(users) > 25:
            raise ValueError("Unexpected directory response; no account changed.")
        for user in users:
            if not isinstance(user, dict):
                raise ValueError("Unexpected account response; no account changed.")
            metadata = user.get("app_metadata") or {}
            if isinstance(metadata, dict) and metadata.get("qe_owner") is True:
                owners.append(user.get("id"))
            if str(user.get("email", "")).casefold() == email:
                if target is not None:
                    raise ValueError("Multiple matching accounts; no account changed.")
                target = user
        if len(users) < 25:
            break
    else:
        raise ValueError("Directory scan limit reached; no account changed.")
    if not target or not target.get("id") or not target.get("email_confirmed_at"):
        raise ValueError("The account must already exist and have a confirmed email.")
    from user_admin import account_suspended

    if account_suspended(target):
        raise ValueError("The initial owner account must be active.")
    if owners and owners != [target["id"]]:
        raise ValueError(
            "A different initial owner already exists; no account changed."
        )
    if apply:
        _service_request(
            "PUT",
            f"/{target['id']}",
            {"app_metadata": {"qe_role": "admin", "qe_owner": True}},
        )
    return (
        "Initial owner configured."
        if apply
        else "Verified account found. Run with --apply to assign the initial owner."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    try:
        print(bootstrap(args.email, args.apply))
    except (AdminError, ValueError) as error:
        parser.exit(1, f"{error}\n")
