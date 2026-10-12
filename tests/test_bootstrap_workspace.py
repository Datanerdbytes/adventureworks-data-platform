import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/bootstrap_workspace.py"
spec = importlib.util.spec_from_file_location("bootstrap_workspace_cli", MODULE_PATH)
bootstrap_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_cli)


class BootstrapConnectionTests(unittest.TestCase):
    def test_cli_leaves_transaction_management_to_bootstrap_and_closes_connection(self):
        class Connection:
            active = False
            closed = False

            def __enter__(self):
                if self.active:
                    raise RuntimeError("Recursive transaction context")
                self.active = True
                return self

            def __exit__(self, *args):
                self.active = False

            def close(self):
                self.closed = True

        connection = Connection()

        def run_bootstrap(conn, email):
            with conn:
                self.assertEqual(email, "owner@example.com")
                return "workspace-id"

        with (
            patch.object(bootstrap_cli, "load_dotenv"),
            patch.dict(bootstrap_cli.os.environ, {"SUPABASE_DB_URL": "test-only"}),
            patch.object(bootstrap_cli.psycopg2, "connect", return_value=connection),
            patch.object(bootstrap_cli, "bootstrap", side_effect=run_bootstrap),
            patch(
                "sys.argv", ["bootstrap_workspace.py", "--email", "owner@example.com"]
            ),
            patch("builtins.print"),
        ):
            bootstrap_cli.main()

        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
