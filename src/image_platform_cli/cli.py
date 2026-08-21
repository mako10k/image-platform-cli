import argparse
import sys
import webbrowser
from collections.abc import Sequence
from pathlib import Path

import httpx

from .api import ImageApiClient, save_image
from .config import Config
from .credentials import KeyringCredentialStore
from .errors import CliError
from .oauth import DeviceFlowClient
from .service import AuthService
from .tokens import TokenValidator


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="image")
    groups = root.add_subparsers(dest="group", required=True)
    auth = groups.add_parser("auth")
    commands = auth.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login")
    login.add_argument("--scope", action="append", default=[])
    commands.add_parser("status")
    commands.add_parser("logout")
    generate = groups.add_parser("generate")
    generate.add_argument("prompt")
    generate.add_argument("--output", "-o", type=Path, required=True)
    generate.add_argument("--width", type=int, default=1024)
    generate.add_argument("--height", type=int, default=1024)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--optimize", action="store_true")
    generate.add_argument("--wait", type=int, default=30)
    generate.add_argument("--allow-long-wait", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = Config.staging()
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as http:
            service = AuthService(
                config,
                DeviceFlowClient(http, config.issuer, config.client_id),
                TokenValidator(http, config.issuer, config.audience),
                KeyringCredentialStore(),
            )
            if args.group == "generate":
                access_token = service.access_token(
                    frozenset({"images:generate", "campaigns:read", "artifacts:read"})
                )
                image = ImageApiClient(http, config.api_base_url).generate(
                    access_token,
                    prompt=args.prompt,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                    optimize=args.optimize,
                    wait_seconds=args.wait,
                    allow_long_wait=args.allow_long_wait,
                )
                save_image(image, args.output)
                print(f"Saved {image.width}x{image.height} PNG to {args.output}.")
                print(f"SHA-256: {image.sha256}")
                print(f"Seed: {image.seed}")
            elif args.command == "login":
                login_credential = service.login(
                    tuple(args.scope or ["images:generate", "campaigns:read", "artifacts:read"]),
                    _announce,
                )
                print(
                    f"Logged in as {login_credential.subject} for organization "
                    f"{login_credential.organization_id}."
                )
            elif args.command == "status":
                status_credential = service.status()
                if status_credential is None:
                    print("Not logged in.")
                    return 1
                print(f"User: {status_credential.subject}")
                print(f"Organization: {status_credential.organization_id}")
                print(f"Scopes: {' '.join(status_credential.scopes)}")
            elif args.command == "logout":
                print("Logged out." if service.logout() else "Not logged in.")
        return 0
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _announce(user_code: str, verification_uri_complete: str) -> None:
    print(f"Open this URL to authorize: {verification_uri_complete}")
    print(f"Code: {user_code}")
    webbrowser.open(verification_uri_complete, new=2)


if __name__ == "__main__":
    raise SystemExit(main())
