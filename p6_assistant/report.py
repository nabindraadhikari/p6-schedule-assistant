"""Export check results to a formatted Excel workbook (the format a scheduler already lives in)."""
import io
import re
import pandas as pd
from .checks import CHECK_DEFS


def to_excel(result) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        result["summary"].drop(columns=["key"]).to_excel(xw, sheet_name="Summary", index=False)
        for key, df in result["detail"].items():
            if len(df):
                name = re.sub(r"[^A-Za-z0-9 \-]", "", CHECK_DEFS[key].title)[:31]
                df.to_excel(xw, sheet_name=name, index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 70)
            ws.freeze_panes = "A2"
    return buf.getvalue()
