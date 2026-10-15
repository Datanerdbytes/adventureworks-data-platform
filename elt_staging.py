"""Offline bounded Parquet staging; no configuration or service clients."""

from contextlib import suppress

import sqlalchemy as sa
import pyarrow as pa
import pyarrow.parquet as pq

DEFAULT_BATCH_SIZE = 10_000
MAX_BATCH_SIZE = 100_000


def validate_batch_size(batch_size):
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be an integer between 1 and {MAX_BATCH_SIZE}."
        )


def arrow_type(sql_type):
    """Use source metadata even if the first batch contains only nulls.

    Numeric/Decimal intentionally retains the previous float conversion; this
    pipeline is not a lossless financial-number export.
    """
    if isinstance(sql_type, sa.Boolean):
        return pa.bool_()
    if isinstance(sql_type, sa.Integer):
        return pa.int64()
    if isinstance(sql_type, (sa.Numeric, sa.Float)):
        return pa.float64()
    if isinstance(sql_type, sa.DateTime):
        return pa.timestamp("us", tz="UTC" if sql_type.timezone else None)
    if isinstance(sql_type, sa.Date):
        return pa.date32()
    if isinstance(sql_type, sa.Time) and not sql_type.timezone:
        return pa.time64("us")
    if isinstance(sql_type, sa.LargeBinary):
        return pa.binary()
    if isinstance(sql_type, (sa.String, sa.Uuid)):
        return pa.string()
    # Unknown types fail before a replacement is submitted, rather than silently
    # inferring a type from whichever values happen to occur in the first batch.
    raise ValueError("Unsupported source column type.")


def write_parquet_batches(result, schema, path, batch_size=DEFAULT_BATCH_SIZE):
    """Consume a streaming result in bounded batches into one local spool.

    The caller owns the result and temporary path. No warehouse client is used.
    Parquet metadata grows with row-group count; row storage is batch bounded.
    """
    validate_batch_size(batch_size)
    if not schema:
        raise ValueError("Source schema must contain at least one column.")
    writer = None
    row_count = 0
    try:
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            arrays = []
            for field in schema:
                values = [row._mapping[field.name] for row in rows]
                if pa.types.is_floating(field.type):
                    values = [None if v is None else float(v) for v in values]
                elif pa.types.is_string(field.type):
                    values = [None if v is None else str(v) for v in values]
                arrays.append(pa.array(values, type=field.type))
            batch = pa.Table.from_arrays(arrays, schema=schema)
            if writer is None:
                writer = pq.ParquetWriter(path, schema)
            writer.write_table(batch, row_group_size=batch_size)
            row_count += len(rows)
            # Release all references before fetching the next batch.
            del rows, arrays, values, batch
    except BaseException:
        if writer is not None:
            with suppress(Exception):
                writer.close()
        raise
    else:
        if writer is not None:
            writer.close()  # A footer/disk error prevents publication too.
    return row_count
