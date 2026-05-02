"""RealResearch: rr-stock-flow — 查询个股资金流向（大单/小单买卖统计）

基于 Tushare moneyflow 接口，分析主力资金与散户资金的动向：
- 超大单（≥100万）、大单（20-100万）、中单（5-20万）、小单（<5万）
- 各类别的买入/卖出量和金额
- 净流入量和金额

数据从2010年开始，单次请求最大6000行。

核心价值：
- 超大单+大单净流入 → 机构/主力在买入
- 大单卖+小单买 → 主力出货，散户接盘
- 净流入金额持续为正 → 资金面支撑较强

Usage:
    rr-stock-flow --code 601899 --last 10            # 最近10个交易日资金流向
    rr-stock-flow --code 601899 --start 2026-04-01   # 指定起始日期
    rr-stock-flow --code 601899 --start 2026-01-01 --end 2026-04-30
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


def _to_float(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _add_derived_fields(records: list[dict]) -> list[dict]:
    """Add derived fields for analysis."""
    for r in records:
        # Big money net flow (超大单+大单 净流入)
        elg_buy = _to_float(r.get("buy_elg_amount"))
        elg_sell = _to_float(r.get("sell_elg_amount"))
        lg_buy = _to_float(r.get("buy_lg_amount"))
        lg_sell = _to_float(r.get("sell_lg_amount"))
        sm_buy = _to_float(r.get("buy_sm_amount"))
        sm_sell = _to_float(r.get("sell_sm_amount"))

        if elg_buy is not None and elg_sell is not None and lg_buy is not None and lg_sell is not None:
            r["big_net_amount"] = round(elg_buy - elg_sell + lg_buy - lg_sell, 2)
        else:
            r["big_net_amount"] = None

        # Small money net flow (小单 净流入)
        if sm_buy is not None and sm_sell is not None:
            r["sm_net_amount"] = round(sm_buy - sm_sell, 2)
        else:
            r["sm_net_amount"] = None

        # Big net as percentage of total net
        net = _to_float(r.get("net_mf_amount"))
        big_net = r.get("big_net_amount")
        if net is not None and big_net is not None and net != 0:
            r["big_net_pct"] = round(big_net / net * 100, 1)
        else:
            r["big_net_pct"] = None

    return records


def run_stock_flow(args) -> dict:
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
            start_date = _normalize_date(args.start) if args.start else None
            end_date = _normalize_date(args.end) if args.end else datetime.now().strftime("%Y%m%d")

        # Fetch money flow data
        time.sleep(0.3)
        kwargs = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date

        df = pro.moneyflow(**kwargs)

        if df is None or len(df) == 0:
            return {
                "ok": True,
                "code": ts_code,
                "name": name,
                "data": [],
                "meta": {"source": "tushare", "api": "moneyflow", "count": 0},
            }

        records = _df_to_records(df)

        # Add derived fields
        records = _add_derived_fields(records)

        # Sort by date ascending
        records.sort(key=lambda x: x.get("trade_date", ""))

        # Trim to --last
        if args.last:
            records = records[-args.last:]

        return {
            "ok": True,
            "code": ts_code,
            "name": name,
            "data": records,
            "meta": {
                "source": "tushare",
                "api": "moneyflow",
                "count": len(records),
                "order_types": "sm(<5万) md(5-20万) lg(20-100万) elg(≥100万)",
                "derived_fields": "big_net_amount(超大单+大单净流入), sm_net_amount(小单净流入), big_net_pct(大资金净流入占比)",
            },
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询个股资金流向（大单/小单买卖统计）"
    )
    parser.add_argument("--code", "-c", required=True, help="股票代码（6位数字，如601899）")
    parser.add_argument("--start", "-s", help="起始日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--end", "-e", help="结束日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--last", "-l", type=int, help="最近N个交易日（与start/end互斥）")
    args = parser.parse_args()

    if not args.start and not args.last:
        parser.error("必须指定 --start 或 --last")

    result = run_stock_flow(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
