"""
One-time setup: create the meczyki secret scope and store the Lakebase
database URL. Run locally with the Databricks CLI authenticated — never
commit the secret value.

Usage:
    python setup_secrets.py
    python setup_secrets.py --run-as <principal>
"""
import argparse

import getpass

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace


def main():

    parser = argparse.ArgumentParser(
        description="Setup the meczyki Lakebase secret."
    )

    parser.add_argument(
        "--run-as",
        metavar="PRINCIPAL",
        default=None,
        help=(
            "Databricks principal (service principal or group) that the "
            "notebook job runs as; also granted READ on the scope."
        ),
    )

    args = parser.parse_args()

    w = WorkspaceClient()

    try:

        w.secrets.create_scope(
            scope="meczyki",
        )

        print("Created secret scope 'meczyki'.")

    except Exception as exc:

        print(f"Secret scope 'meczyki' already exists: {exc}")

    w.secrets.put_secret(
        scope="meczyki",
        key="lakebase_database_url",
        string_value=getpass.getpass(
            "Paste your Lakebase database URL: "
        ),
    )

    w.secrets.put_acl(
        scope="meczyki",
        principal="users",
        permission=workspace.AclPermission.READ,
    )

    if args.run_as:

        w.secrets.put_acl(
            scope="meczyki",
            principal=args.run_as,
            permission=workspace.AclPermission.READ,
        )

        print(
            f"Granted READ to '{args.run_as}'."
        )


if __name__ == "__main__":
    main()