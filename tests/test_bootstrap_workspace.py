import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/bootstrap_workspace.py"
spec = importlib.util.spec_from_file_location("bootstrap_workspace_cli", MODULE_PATH)
bootstrap_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_cli)


class BootstrapConnectionTests(unittest.TestCase):
    def test_cli_leaves_transaction_management_to_bootstrap_and_closes_connection(self):
        class Connection:
            info = SimpleNamespace(ssl_in_use=True)
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
            patch.object(bootstrap_cli, "load_dotenv") as dotenv,
            patch.dict(
                bootstrap_cli.os.environ,
                {"SUPABASE_DB_URL": "postgresql://db.invalid/app"},
            ),
            patch.object(bootstrap_cli.psycopg2, "connect", return_value=connection),
            patch.object(bootstrap_cli, "bootstrap", side_effect=run_bootstrap),
            patch(
                "sys.argv", ["bootstrap_workspace.py", "--email", "owner@example.com"]
            ),
            patch("builtins.print"),
        ):
            bootstrap_cli.main()

        self.assertTrue(connection.closed)
        self.assertEqual(dotenv.call_args.kwargs, {"override": False})


class BootstrapTLSVerificationTests(unittest.TestCase):
    def test_connect_forces_verified_tls_over_url_and_environment(self):
        connection = SimpleNamespace(info=SimpleNamespace(ssl_in_use=True))
        with (
            patch.dict(
                bootstrap_cli.os.environ,
                {
                    "PGSSLMODE": "disable",
                    "SUPABASE_DB_SSLROOTCERT": "/trusted/ca.crt",
                },
                clear=True,
            ),
            patch.object(
                bootstrap_cli.psycopg2, "connect", return_value=connection
            ) as connect,
        ):
            self.assertIs(
                bootstrap_cli.connect_secure_database(
                    "postgresql://db.invalid/app?sslmode=disable"
                ),
                connection,
            )
        connect.assert_called_once_with(
            "postgresql://db.invalid/app?sslmode=disable",
            connect_timeout=8,
            sslmode="verify-full",
            gssencmode="disable",
            sslrootcert="/trusted/ca.crt",
        )

    def test_unix_or_missing_host_rejected_before_connect(self):
        for url in (
            "dbname=app",
            "host=/tmp dbname=app",
            "host=@abstract dbname=app",
            "host=db.invalid,/tmp dbname=app",
        ):
            with (
                self.subTest(url=url),
                patch.dict(bootstrap_cli.os.environ, {}, clear=True),
                patch.object(bootstrap_cli.psycopg2, "connect") as connect,
            ):
                with self.assertRaises(bootstrap_cli.BootstrapValidationError):
                    bootstrap_cli.connect_secure_database(url)
                connect.assert_not_called()

    def test_default_trust_configuration_is_left_to_libpq(self):
        connection = SimpleNamespace(info=SimpleNamespace(ssl_in_use=True))
        with (
            patch.dict(bootstrap_cli.os.environ, {}, clear=True),
            patch.object(
                bootstrap_cli.psycopg2, "connect", return_value=connection
            ) as connect,
        ):
            bootstrap_cli.connect_secure_database("postgresql://db.invalid/app")
        self.assertNotIn("sslrootcert", connect.call_args.kwargs)
        self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")

    def test_insecure_connection_closed_before_bootstrap(self):
        from unittest.mock import Mock

        connection = Mock(info=SimpleNamespace(ssl_in_use=False))
        with (
            patch.object(bootstrap_cli, "load_dotenv"),
            patch.dict(
                bootstrap_cli.os.environ,
                {"SUPABASE_DB_URL": "postgresql://db.invalid/app"},
            ),
            patch.object(bootstrap_cli.psycopg2, "connect", return_value=connection),
            patch.object(bootstrap_cli, "bootstrap") as bootstrap,
            patch(
                "sys.argv", ["bootstrap_workspace.py", "--email", "owner@example.com"]
            ),
            patch("sys.stderr.write") as output,
        ):
            with self.assertRaises(SystemExit) as raised:
                bootstrap_cli.main()
        self.assertEqual(raised.exception.code, 1)
        bootstrap.assert_not_called()
        connection.close.assert_called_once()
        self.assertIn(
            "requires TLS", "".join(call.args[0] for call in output.call_args_list)
        )

    def test_driver_and_url_parse_errors_never_print_raw_details(self):
        for error in (
            bootstrap_cli.psycopg2.OperationalError("private-dsn-sentinel"),
            ValueError("private-dsn-sentinel"),
        ):
            with (
                self.subTest(error=type(error).__name__),
                patch.object(bootstrap_cli, "load_dotenv"),
                patch.dict(
                    bootstrap_cli.os.environ,
                    {"SUPABASE_DB_URL": "postgresql://db.invalid/app"},
                ),
                patch.object(bootstrap_cli.psycopg2, "connect", side_effect=error),
                patch.object(bootstrap_cli, "bootstrap") as bootstrap,
                patch(
                    "sys.argv",
                    ["bootstrap_workspace.py", "--email", "owner@example.com"],
                ),
                patch("sys.stderr.write") as output,
            ):
                with self.assertRaises(SystemExit):
                    bootstrap_cli.main()
                bootstrap.assert_not_called()
                message = "".join(call.args[0] for call in output.call_args_list)
                self.assertNotIn("private-dsn-sentinel", message)
                self.assertIn("Database bootstrap failed", message)

    def test_bootstrap_failure_closes_connection_and_sanitizes_driver_error(self):
        from unittest.mock import Mock

        connection = Mock(info=SimpleNamespace(ssl_in_use=True))
        with (
            patch.object(bootstrap_cli, "load_dotenv"),
            patch.dict(
                bootstrap_cli.os.environ,
                {"SUPABASE_DB_URL": "postgresql://db.invalid/app"},
            ),
            patch.object(bootstrap_cli.psycopg2, "connect", return_value=connection),
            patch.object(
                bootstrap_cli,
                "bootstrap",
                side_effect=bootstrap_cli.psycopg2.Error("private-dsn-sentinel"),
            ),
            patch(
                "sys.argv", ["bootstrap_workspace.py", "--email", "owner@example.com"]
            ),
            patch("sys.stderr.write") as output,
        ):
            with self.assertRaises(SystemExit):
                bootstrap_cli.main()
        connection.close.assert_called_once()
        self.assertNotIn(
            "private-dsn-sentinel",
            "".join(call.args[0] for call in output.call_args_list),
        )

    def test_runtime_environment_wins_over_dotenv(self):
        from tempfile import TemporaryDirectory
        from dotenv import load_dotenv

        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.env"
            path.write_text(
                "SUPABASE_DB_URL=file-fixture\nSUPABASE_DB_SSLROOTCERT=/file/ca.crt\n"
            )
            with patch.dict(
                bootstrap_cli.os.environ,
                {
                    "SUPABASE_DB_URL": "runtime-fixture",
                    "SUPABASE_DB_SSLROOTCERT": "/runtime/ca.crt",
                },
                clear=True,
            ):
                load_dotenv(path, override=False)
                self.assertEqual(
                    bootstrap_cli.os.environ["SUPABASE_DB_URL"], "runtime-fixture"
                )
                self.assertEqual(
                    bootstrap_cli.os.environ["SUPABASE_DB_SSLROOTCERT"],
                    "/runtime/ca.crt",
                )


if __name__ == "__main__":
    unittest.main()
