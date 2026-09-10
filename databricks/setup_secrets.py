"""
One-time setup: create the meczyki secret scope and store the Lakebase
database URL. Run locally with the Databricks CLI authenticated — never
commit the secret value.

Usage:
    python setup_secrets.py
"""
import getpass

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace

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