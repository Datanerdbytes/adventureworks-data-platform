"""Offline staging/readback and lifecycle regression coverage."""

import gc
import io
import os
from contextlib import redirect_stdout
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import weakref
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
import sqlalchemy as sa

import elt_pipeline as pipeline
from elt_staging import arrow_type, write_parquet_batches


class Row:
    def __init__(self, mapping):
        self._mapping = mapping


class StreamingResult:
    def __init__(self, count, batch_size, values=None, fail_after=None):
        self.count = count
        self.batch_size = batch_size
        self.index = 0
        self.previous = []
        self.values = values
        self.fail_after = fail_after
        self.closed = False

    def fetchall(self):
        raise AssertionError("full buffering forbidden")

    def fetchmany(self, size):
        assert size == self.batch_size
        gc.collect()
        assert not any(ref() is not None for ref in self.previous)
        if self.fail_after is not None and self.index >= self.fail_after:
            raise ConnectionError("synthetic-secret")
        end = min(self.count, self.index + size)
        rows = [
            Row(self.values[i] if self.values is not None else {"id": i})
            for i in range(self.index, end)
        ]
        self.index = end
        self.previous = [weakref.ref(row) for row in rows]
        return rows

    def close(self):
        self.closed = True


class StagingTests(unittest.TestCase):
    def test_many_batches_release_previous_rows(self):
        result = StreamingResult(103, 7)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rows.parquet"
            self.assertEqual(
                write_parquet_batches(result, pa.schema([("id", pa.int64())]), path, 7),
                103,
            )
            self.assertEqual(
                pq.read_table(path).column("id").to_pylist(), list(range(103))
            )
            self.assertEqual(pq.ParquetFile(path).metadata.num_row_groups, 15)

    def test_typed_null_first_batch_and_decimal_compatibility(self):
        types = {
            "id": sa.Integer(),
            "flag": sa.Boolean(),
            "amount": sa.Numeric(20, 4),
            "real": sa.REAL(),
            "day": sa.Date(),
            "instant": sa.DateTime(timezone=True),
            "local": sa.DateTime(),
            "name": sa.String(),
            "binary": sa.LargeBinary(),
            "uuid": sa.Uuid(),
            "time": sa.Time(),
        }
        schema = pa.schema([(name, arrow_type(kind)) for name, kind in types.items()])
        later = {
            "id": 123,
            "flag": True,
            "amount": Decimal("123456.7891"),
            "real": 2.5,
            "day": date(2026, 10, 15),
            "instant": datetime(2026, 10, 15, tzinfo=timezone.utc),
            "local": datetime(2026, 10, 15, 12, 30),
            "name": "example",
            "binary": b"\x00\x01",
            "uuid": UUID("00000000-0000-0000-0000-000000000001"),
            "time": time(12, 34, 56),
        }
        rows = [dict.fromkeys(types), dict.fromkeys(types), later, dict.fromkeys(types)]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rows.parquet"
            write_parquet_batches(StreamingResult(4, 2, rows), schema, path, 2)
            table = pq.read_table(path)
            self.assertEqual(table.schema, schema)
            expected = [
                dict.fromkeys(types),
                dict.fromkeys(types),
                dict(later),
                dict.fromkeys(types),
            ]
            expected[2]["amount"] = float(later["amount"])
            expected[2]["uuid"] = str(later["uuid"])
            self.assertEqual(table.to_pylist(), expected)

    def test_unsupported_types_fail_before_inference(self):
        with self.assertRaises(ValueError):
            arrow_type(sa.JSON())


class PipelineStreamingTests(unittest.TestCase):
    def run_fake(
        self, result, upload=None, writer=None, client_failure=None, columns=None
    ):
        self.engine = MagicMock()
        self.connection = self.engine.connect.return_value
        self.connection.execution_options.return_value = self.connection
        self.connection.execute.return_value = result
        self.connection.dialect.identifier_preparer.quote.side_effect = (
            lambda name: '"' + name + '"'
        )
        self.target = MagicMock()
        self.paths = []
        self.temporary_paths = []

        def temporary_directory(**kwargs):
            temporary = TemporaryDirectory(**kwargs)
            self.temporary_paths.append(Path(temporary.name))
            return temporary

        self.tables = []
        self.job_configs = []

        def read_upload(source, destination, **kwargs):
            self.paths.append(Path(source.name))
            self.tables.append(pq.read_table(source))
            self.assertEqual(destination, "test-project.raw.dimcurrency")
            self.job_configs.append(kwargs["job_config"])
            self.assertEqual(kwargs["location"], "asia-east2")
            if upload:
                return upload(source)
            return SimpleNamespace(result=lambda: None)

        self.target.load_table_from_file.side_effect = read_upload
        self.output = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {"GBQ_PROJECT_ID": "test-project", "GBQ_DATASET_ID": "raw"},
                clear=True,
            ),
            patch.object(pipeline, "_load_env"),
            patch.object(
                pipeline.tempfile, "TemporaryDirectory", side_effect=temporary_directory
            ),
            patch.object(pipeline, "TABLES_TO_MIGRATE", ["dimcurrency"]),
            patch.object(pipeline, "get_postgres_engine", return_value=self.engine),
            patch.object(
                pipeline.bigquery,
                "Client",
                side_effect=client_failure,
                return_value=self.target,
            ),
            patch.object(pipeline.sa, "inspect") as inspector,
            redirect_stdout(self.output),
        ):
            inspector.return_value.get_columns.return_value = columns or [
                {"name": "id", "type": sa.Integer()}
            ]
            if writer is not None:
                with patch("elt_staging.pq.ParquetWriter", writer):
                    pipeline.run_elt_migration(batch_size=2)
            else:
                pipeline.run_elt_migration(batch_size=2)

    def assert_cleanup(self, result):
        self.assertTrue(result.closed)
        self.connection.close.assert_called_once()
        self.target.close.assert_called_once()
        self.engine.dispose.assert_called_once()
        for path in self.temporary_paths:
            self.assertFalse(path.exists())
        for path in self.paths:
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())

    def test_streaming_cursor_and_single_complete_load(self):
        result = StreamingResult(7, 2)
        self.run_fake(result)
        self.connection.execution_options.assert_called_once_with(
            stream_results=True, yield_per=2, max_row_buffer=2
        )
        self.assertIn(
            'SELECT "id" FROM public.dimcurrency',
            str(self.connection.execute.call_args.args[0]),
        )
        self.target.load_table_from_file.assert_called_once()
        self.assertEqual(self.tables[0].column("id").to_pylist(), list(range(7)))
        self.assertEqual(self.job_configs[0].write_disposition, "WRITE_TRUNCATE")
        self.assertEqual(self.job_configs[0].source_format, "PARQUET")
        self.assert_cleanup(result)

    def test_upload_preserves_explicit_logical_schema_after_null_first_batch(self):
        columns = [
            {"name": "id", "type": sa.Integer()},
            {"name": "flag", "type": sa.Boolean()},
            {"name": "amount", "type": sa.Numeric()},
            {"name": "local", "type": sa.DateTime()},
            {"name": "instant", "type": sa.DateTime(timezone=True)},
            {"name": "day", "type": sa.Date()},
            {"name": "clock", "type": sa.Time()},
            {"name": "name", "type": sa.String()},
            {"name": "binary", "type": sa.LargeBinary()},
        ]
        later = {
            "id": 1,
            "flag": True,
            "amount": Decimal("1.25"),
            "local": datetime(2026, 10, 15, 10, 30),
            "instant": datetime(2026, 10, 15, tzinfo=timezone.utc),
            "day": date(2026, 10, 15),
            "clock": time(10, 30),
            "name": "example",
            "binary": b"example",
        }
        null = dict.fromkeys(later)
        self.run_fake(StreamingResult(3, 2, [null, null, later]), columns=columns)
        self.assertEqual(
            {field.name: field.field_type for field in self.job_configs[0].schema},
            {
                "id": "INTEGER",
                "flag": "BOOLEAN",
                "amount": "FLOAT",
                "local": "DATETIME",
                "instant": "TIMESTAMP",
                "day": "DATE",
                "clock": "TIME",
                "name": "STRING",
                "binary": "BYTES",
            },
        )
        expected = dict(later, amount=float(later["amount"]))
        self.assertEqual(self.tables[0].to_pylist(), [null, null, expected])

    def test_empty_source_skips_upload(self):
        result = StreamingResult(0, 2)
        self.run_fake(result)
        self.target.load_table_from_file.assert_not_called()
        self.assertIn("Skipping dimcurrency", self.output.getvalue())
        self.assert_cleanup(result)

    def test_source_failure_no_publication_and_spool_removed(self):
        result = StreamingResult(7, 2, fail_after=4)
        paths = []
        original = pipeline.spool_table

        def capture(connection, table, path, size):
            paths.append(path)
            return original(connection, table, path, size)

        with (
            patch.object(pipeline, "spool_table", side_effect=capture),
            self.assertRaises(SystemExit),
        ):
            self.run_fake(result)
        self.target.load_table_from_file.assert_not_called()
        self.assertFalse(paths[0].parent.exists())
        self.assertNotIn("synthetic-secret", self.output.getvalue())
        self.assert_cleanup(result)

    def test_serialization_and_disk_failure_no_publication(self):
        cases = [
            (
                StreamingResult(4, 2, [{"id": 1}, {"id": 2}, {"id": "bad"}, {"id": 4}]),
                None,
            ),
            (
                StreamingResult(4, 2),
                MagicMock(side_effect=OSError(28, "disk full synthetic-secret")),
            ),
        ]
        for result, writer in cases:
            with self.subTest(writer=writer), self.assertRaises(SystemExit):
                self.run_fake(result, writer=writer)
            self.target.load_table_from_file.assert_not_called()
            self.assert_cleanup(result)

    def test_footer_failure_no_publication(self):
        writer = MagicMock()
        writer.return_value.close.side_effect = OSError("disk full")
        result = StreamingResult(4, 2)
        with self.assertRaises(SystemExit):
            self.run_fake(result, writer=writer)
        self.target.load_table_from_file.assert_not_called()
        self.assert_cleanup(result)

    def test_failed_load_is_not_success(self):
        result = StreamingResult(4, 2)

        def upload(source):
            return SimpleNamespace(
                result=MagicMock(side_effect=RuntimeError("synthetic-secret"))
            )

        with self.assertRaises(SystemExit):
            self.run_fake(result, upload=upload)
        self.assertIn("0/1", self.output.getvalue())
        self.assertNotIn("synthetic-secret", self.output.getvalue())
        self.assert_cleanup(result)

    def test_client_construction_failure_disposes_engine_without_tempfile(self):
        with patch.object(pipeline.tempfile, "TemporaryDirectory") as temporary:
            with self.assertRaises(ConnectionError):
                self.run_fake(
                    StreamingResult(4, 2), client_failure=ConnectionError("private")
                )
        self.engine.dispose.assert_called_once()
        self.engine.connect.assert_not_called()
        temporary.assert_not_called()

    def test_invalid_batches_and_dry_run_do_not_stage(self):
        for batch_size in (True, 0, -1, 100001, "100", 1.5):
            with (
                patch.object(pipeline, "_load_env") as env,
                self.assertRaises(pipeline.PipelineConfigurationError),
            ):
                pipeline.run_elt_migration(batch_size=batch_size)
            env.assert_not_called()
        with (
            patch.dict(
                os.environ,
                {"GBQ_PROJECT_ID": "test-project", "GBQ_DATASET_ID": "raw"},
                clear=True,
            ),
            patch.object(pipeline, "_load_env"),
            patch.object(pipeline.tempfile, "TemporaryDirectory") as temporary,
            patch.object(pipeline, "get_postgres_engine") as engine,
            patch.object(pipeline.bigquery, "Client") as target,
            redirect_stdout(io.StringIO()),
        ):
            pipeline.run_elt_migration(dry_run=True)
        temporary.assert_not_called()
        engine.assert_not_called()
        target.assert_not_called()
