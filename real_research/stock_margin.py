"""RealResearch: rr-stock-margin — 查询融资融券交易汇总（两融数据）

基于 Tushare margin 接口，分析市场杠杆资金动向：
- 融资余额（借入买股的总金额）→ 看多信号
- 融券余额（借券卖出的总金额）→ 做空信号
- 融资净买入额（当日买入 - 偿还）→ 杠杆资金真实流入
- 融资融券余额合计 → 市场杠杆总水平

数据按交易所汇总（SSE/SZSE/BSE），不是个股级别。

核心价值：
- 融资余额持续增加 → 杠杆资金看多，市场情绪偏乐观
- 融资余额大幅下降 → 杠杆资金撤退，信心不足
- 融券余额增加 → 做空力量增强
- 融资净买入额为正 → 杠杆资金净流入

Usage:
    rr-stock-margin --exchange SSE --last 10          # 上交所最近10天
    rr-stock-margin --exchange SZSE --start 2026-04-01  # 深交所指定日期
    rr-stock-margin --last 5                           # 不指定交易所，查全部
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


def _to_float(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _add_derived_fields(records: list[dict]) -> list[dict]:
    """Add derived fields for analysis."""
    for r in records:
        # Net margin buy (融资净买入额 = 买入额 - 偿还额)
        rzmre = _to_float(r.get("rzmre"))
        rzche = _to_float(r.get("rzche"))
        if rzmre is not None and rzche is not None:
            r["rz_net_buy"] = round(rzmre - rzche, 2)
        else:
            r["rz_net_buy"] = None

    return records


def run_stock_margin(args) -> dict:
    token = os.environ.get("RR_TUSHARE_TOKEN")
    if not token:
        return {"error": "RR_TUSHARE_TOKEN not set"}

    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()

        # Determine date range
        if args.last:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=args.last * 2)).strftime("%Y%m%d")
        else:
            start_date = _normalize_date(args.start) if args.start else None
            end_date = _normalize_date(args.end) if args.end else datetime.now().strftime("%Y%m%d")

        exchange = args.exchange.upper() if args.exchange else None

        # Fetch margin data
        time.sleep(0.3)
        kwargs = {}
        if exchange:
            kwargs["exchange_id"] = exchange
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date

        df = pro.margin(**kwargs)

        if df is None or len(df) == 0:
            return {
                "ok": True,
                "exchange": exchange or "ALL",
                "data": [],
                "meta": {"source": "tushare", "api": "margin", "count": 0},
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
            "exchange": exchange or "ALL",
            "data": records,
            "meta": {
                "source": "tushare",
                "api": "margin",
                "count": len(records),
                "fields": "rzye(融资余额),rzmre(融资买入额),rzche(融资偿还额),rqye(融券余额),rqmcl(融券卖出量),rqyl(融券余量),rzrqye(两融余额),rz_net_buy(融资净买入额)",
            },
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询融资融券交易汇总（两融数据）"
    )
    parser.add_argument("--exchange", "-x", help="交易所代码：SSE（沪）、SZSE（深）、BSE（北），不指定则查全部")
    parser.add_argument("--start", "-s", help="起始日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--end", "-e", help="结束日期（YYYY-MM-DD或YYYYMMDD）")
    parser.add_argument("--last", "-l", type=int, help="最近N个交易日（与start/end互斥）")
    args = parser.parse_args()

    if not args.start and not args.last:
        parser.error("必须指定 --start 或 --last")

    result = run_stock_margin(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
