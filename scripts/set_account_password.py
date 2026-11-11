"""Set a new password for an existing confirmed Supabase account.

Run from the repository root. This is an explicit operator command for the cases
where the email recovery path cannot run, for example while the project's
outbound email quota is exhausted. The password is read interactively and never
passed as an argument, printed, or written to a file. Without ``--apply`` it only
verifies the account state and changes nothing.
"""

import argparse
import getpass
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "my-dash-app"))

from user_admin import (  # noqa: E402 - sibling Dash module path is added above
    AdminError,
    _service_request,
)

MINIMUM_PASSWORD_LENGTH = 12


def find_account(email):
    """Return the one confirmed account that matches the address."""
    email = email.strip().casefold()
    if not email or "@" not in email:
        raise ValueError("Provide the email of an existing account.")
    target = None
    for page in range(1, 401):
        result = _service_request("GET", f"?page={page}&per_page=25")
        users = result.get("users")
        if not isinstance(users, list) or len(users) > 25:
            raise ValueError("Unexpected directory response; no account changed.")
        for user in users:
            if not isinstance(user, dict):
                raise ValueError("Unexpected account response; no account changed.")
            if str(user.get("email", "")).casefold() == email:
                if target is not None:
                    raise ValueError("Multiple matching accounts; no account changed.")
                target = user
        if len(users) < 25:
            break
    else:
        raise ValueError("Directory scan limit reached; no account changed.")
    if not target or not target.get("id"):
        raise ValueError("The account must already exist.")
    if not target.get("email_confirmed_at"):
        raise ValueError("The account must have a confirmed email.")
    return target


def governance_metadata(user):
    """Return the account role fields that a password change must not touch."""
    metadata = user.get("app_metadata") or {}
    if not isinstance(metadata, dict):
        return {}
    return {
        key: metadata.get(key)
        for key in ("qe_owner", "qe_role", "qe_suspended")
        if key in metadata
    }


def set_password(email, password):
    """Set the account password and report the preserved governance metadata."""
    if not isinstance(password, str) or len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Use at least {MINIMUM_PASSWORD_LENGTH} characters for the password."
        )
    account = find_account(email)
    before = governance_metadata(account)
    _service_request(
        "PUT",
        f"/{account['id']}",
        {"password": password, "email_confirm": True},
    )
    after = governance_metadata(find_account(email))
    if after != before:
        raise ValueError(
            "Governance metadata changed unexpectedly; verify the account."
        )
    return (
        f"Password updated for {account['email']}. "
        f"Governance metadata preserved: {after or 'none'}."
    )


def prompt_password():
    """Read the new password twice without echoing or storing it."""
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat new password: ")
    if first != second:
        raise ValueError("The passwords do not match.")
    if len(first) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Use at least {MINIMUM_PASSWORD_LENGTH} characters for the password."
        )
    return first


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    try:
        if args.apply:
            print(set_password(args.email, prompt_password()))
        else:
            account = find_account(args.email)
            print(
                f"Verified account found: {account['email']}. "
                f"Governance metadata: {governance_metadata(account) or 'none'}. "
                "Run with --apply to set a new password."
            )
    except (AdminError, ValueError) as error:
        parser.exit(1, f"{error}\n")
