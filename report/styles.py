# -*- coding: utf-8 -*-
# ============================================================
# 样式
# ============================================================
def _mkstyle():
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    thin = Side(style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return dict(
        border=border,
        hdr_fill=PatternFill("solid", fgColor="1976D2"),
        hdr_font=Font(bold=True, color="FFFFFF", size=10),
        title_font=Font(bold=True, size=13, color="212121"),
        sub_font=Font(size=9, color="757575"),
        pass_fill=PatternFill("solid", fgColor="C8E6C9"),
        fail_fill=PatternFill("solid", fgColor="FFCDD2"),
        skip_fill=PatternFill("solid", fgColor="F5F5F5"),
        alt_fill=PatternFill("solid", fgColor="FAFAFA"),
    )


def _rfill(result: str, s: dict):
    return {"PASS": s["pass_fill"], "FAIL": s["fail_fill"], "SKIP": s["skip_fill"]}.get(result.upper())


def _fmt(v):
    if v == "" or v is None:
        return ""
    try:
        return f"{float(v):.3f}"
    except (ValueError, TypeError):
        return str(v)


