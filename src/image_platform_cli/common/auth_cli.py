import argparse
from collections.abc import Callable

from .service import AuthService


def run_auth_command(
    args: argparse.Namespace,
    service: AuthService,
    default_scopes: tuple[str, ...],
    announce: Callable[[str, str], None],
) -> int:
    if args.command == "login":
        login_credential = service.login(tuple(args.scope or default_scopes), announce)
        print(
            f"Logged in as {login_credential.subject} for organization "
            f"{login_credential.organization_id}."
        )
        return 0
    if args.command == "status":
        status_credential = service.status()
        if status_credential is None:
            print("Not logged in.")
            return 1
        print(f"User: {status_credential.subject}")
        print(f"Organization: {status_credential.organization_id}")
        print(f"Scopes: {' '.join(status_credential.scopes)}")
        return 0
    print("Logged out." if service.logout() else "Not logged in.")
    return 0
