"""Parser for Primavera P6 .xer export files (tab-delimited, %T table / %F fields / %R rows)."""
import pandas as pd


def read_xer_bytes(raw: bytes):
    """Parse raw XER bytes -> (header_fields, {table_name: DataFrame of strings})."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    tables, cur, cols, rows, header = {}, None, None, [], []

    def flush():
        if cur is not None and cols is not None:
            tables[cur] = pd.DataFrame(rows, columns=cols)

    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        tag = parts[0]
        if tag == "ERMHDR":
            header = parts
        elif tag == "%T":
            flush()
            cur, cols, rows = parts[1], None, []
        elif tag == "%F":
            cols = parts[1:]
        elif tag == "%R" and cols is not None:
            r = parts[1:]
            r += [""] * (len(cols) - len(r))
            rows.append(r[: len(cols)])
    flush()
    if "TASK" not in tables:
        raise ValueError("This does not look like a P6 XER file (no TASK table found).")
    return header, tables


def read_xer(path):
    with open(path, "rb") as f:
        return read_xer_bytes(f.read())
