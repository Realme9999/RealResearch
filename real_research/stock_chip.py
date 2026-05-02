"""RealResearch: rr-stock-chip — 查询筹码分布与胜率（获利盘占比）

基于 Tushare cyq_perf 接口，分析股票的筹码成本结构：
- 各分位成本（5%/15%/50%/85%/95%）
- 加权平均成本（重要支撑/压力位）
- 胜率（当前价格高于多少比例的持仓成本）
- 成本集中度（85%分位 - 15%分位，越小筹码越集中）

数据从2018年开始，每天18:00-19:00更新。

Usage:
    rr-stock-chip --code 688256 --last 10            # 最近10个交易日筹码
    rr-stock-chip --code 688256 --start 2026-01-01   # 指定起始日期
    rr-stock-chip --code 688256 --start 2026-01-01 --end 2026-04-30
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


def run_stock_chip(args) -> dict:
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

        # Fetch chip distribution data
        time.sleep(0.3)
        kwargs = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date

        df = pro.cyq_perf(**kwargs)

        if df is None or len(df) == 0:
            return {
                "ok": True,
                "code": ts_code,
                "name": name,
                "data": [],
                "meta": {"source": "tushare", "api": "cyq_perf", "count": 0},
            }

        records = _df_to_records(df)

        # Add derived fields
        for r in records:
            c85 = r.get("cost_85pct")
            c15 = r.get("cost_15pct")
            if c85 is not None and c15 is not None:
                try:
                    r["cost_concentration"] = round(float(c85) - float(c15), 2)
                except (ValueError, TypeError):
                    r["cost_concentration"] = None

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
                "api": "cyq_perf",
                "count": len(records),
                "fields": "his_low,his_high,cost_5pct,cost_15pct,cost_50pct,cost_85pct,cost_95pct,weight_avg,winner_rate,cost_concentration",
            },
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询筹码分布与胜率（获利盘占比）"
    )
    parser.add_argument("--code", "-c", required=True, help="股票代码（6位数字，如688256）")
    parser.add_argument("--start", "-s", help="起始日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--end", "-e", help="结束日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--last", "-l", type=int, help="最近N个交易日（与start/end互斥）")
    args = parser.parse_args()

    if not args.start and not args.last:
        parser.error("必须指定 --start 或 --last")

    result = run_stock_chip(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
