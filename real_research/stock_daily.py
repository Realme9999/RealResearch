"""RealResearch: rr-stock-daily — 查询股价走势与交易数据

Usage:
    rr-stock-daily --code 688256 --start 2025-01-01 --end 2025-12-31
    rr-stock-daily --code 688256 --last 30
    rr-stock-daily --code 688256 --last 30 --adj qfq   # 前复权
"""
import argparse
import json
import os
import sys
import math
import time
from datetime import datetime, timedelta

from .utils import setup_utf8, load_dotenv

load_dotenv()


def _clean(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    return s if s and s != "nan" and s != "None" else None


def _df_to_records(df) -> list[dict]:
    df = df.where(df.notna(), None)
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def _normalize_date(d: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD"""
    if d and "-" in d:
        return d.replace("-", "")
    return d


def _resolve_ts_code(pro, code: str) -> str:
    """Resolve 6-digit code to ts_code like 688256.SH"""
    code = code.strip()
    if "." in code:
        return code
    for suffix in [".SH", ".SZ"]:
        try:
            df = pro.stock_basic(ts_code=code + suffix, fields="ts_code,name")
            if df is not None and len(df) > 0:
                return code + suffix
        except Exception:
            pass
    return code


def _get_stock_name(pro, ts_code: str) -> str:
    try:
        df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
        if df is not None and len(df) > 0:
            return df.iloc[0]["name"]
    except Exception:
        pass
    return ""


DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
BASIC_FIELDS = "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,total_share,float_share,total_mv,circ_mv"


def run_stock_daily(args) -> dict:
    token = os.environ.get("RR_TUSHARE_TOKEN")
    if not token:
        return {"error": "RR_TUSHARE_TOKEN not set"}

    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()

        code = args.code.strip()
        ts_code = _resolve_ts_code(pro, code)
        name = _get_stock_name(pro, ts_code)

        # Determine date range
        if args.last:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=args.last * 2)).strftime("%Y%m%d")
        else:
            if not args.start:
                return {"error": "必须指定 --start 或 --last"}
            start_date = _normalize_date(args.start)
            end_date = _normalize_date(args.end) if args.end else datetime.now().strftime("%Y%m%d")

        # Fetch daily OHLCV — use pro_bar for adjusted prices
        adj = args.adj if args.adj else "none"
        time.sleep(0.3)
        if adj in ("qfq", "hfq"):
            import tushare as ts
            df_daily = ts.pro_bar(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
                adj=adj, factors=["tor", "vr"]
            )
        else:
            df_daily = pro.daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
                fields=DAILY_FIELDS
            )

        # Fetch daily_basic (valuation)
        time.sleep(0.3)
        df_basic = pro.daily_basic(
            ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields=BASIC_FIELDS
        )

        if df_daily is None or len(df_daily) == 0:
            return {
                "ok": True,
                "code": ts_code,
                "name": name,
                "data": [],
                "meta": {"source": "tushare", "api": "daily+daily_basic", "adj": adj, "count": 0, "period": f"{start_date}~{end_date}"},
            }

        records_daily = _df_to_records(df_daily)
        records_basic = _df_to_records(df_basic) if df_basic is not None and len(df_basic) > 0 else []

        # Merge by trade_date
        basic_by_date = {}
        for r in records_basic:
            basic_by_date[r.get("trade_date", "")] = r

        merged = []
        for d in records_daily:
            td = d.get("trade_date", "")
            b = basic_by_date.get(td, {})
            merged.append({**d, **b})

        # Sort by date ascending
        merged.sort(key=lambda x: x.get("trade_date", ""))

        # Trim to --last
        if args.last:
            merged = merged[-args.last:]

        return {
            "ok": True,
            "code": ts_code,
            "name": name,
            "data": merged,
            "meta": {
                "source": "tushare",
                "api": "daily+daily_basic",
                "adj": adj,
                "count": len(merged),
                "period": f"{start_date}~{end_date}",
            },
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询股价走势与交易数据"
    )
    parser.add_argument("--code", "-c", required=True, help="股票代码（6位数字，如688256）")
    parser.add_argument("--start", "-s", help="起始日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--end", "-e", help="结束日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--last", "-l", type=int, help="最近N个交易日（与start/end互斥）")
    parser.add_argument("--adj", choices=["qfq", "hfq"], help="复权类型：qfq前复权，hfq后复权（默认不复权）")
    args = parser.parse_args()

    if not args.start and not args.last:
        parser.error("必须指定 --start 或 --last")

    result = run_stock_daily(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
