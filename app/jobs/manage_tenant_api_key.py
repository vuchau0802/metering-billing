import argparse
import sys
from collections.abc import Sequence

from app.db import SessionLocal
from app.services.api_keys import (
    ApiKeyAlreadyProvisionedError,
    ApiKeyTenantNotFoundError,
    provision_tenant_api_key,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision or rotate a tenant API key.",
    )
    parser.add_argument("tenant_id", type=int)
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Replace an existing tenant API key.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        with SessionLocal() as db:
            result = provision_tenant_api_key(
                db,
                tenant_id=arguments.tenant_id,
                rotate=arguments.rotate,
            )
    except (
        ApiKeyAlreadyProvisionedError,
        ApiKeyTenantNotFoundError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1

    action = "rotated" if result.rotated else "provisioned"
    print(f"Tenant {result.tenant_id} API key {action}.")
    print("Store this key securely; it will not be shown again:")
    print(result.api_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
