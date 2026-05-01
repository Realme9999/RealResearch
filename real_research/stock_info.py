"""RealResearch: rr-stock-info — 查询公司基本信息与最新估值

Usage:
    rr-stock-info --code 688256
    rr-stock-info --name 寒武纪
    rr-stock-info --code 688256 --fields name,industry,market_cap,pe_ttm,pb
"""
import argparse
import json
import os
import sys
import math
import time

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


def _resolve_ts_code(pro, code: str = None, name: str = None) -> str:
    """Resolve 6-digit code or name to ts_code like 688256.SH"""
    if code:
        code = code.strip()
        if "." in code:
            return code
        # Try SH first (60xxxx, 68xxxx), then SZ (00xxxx, 30xxxx)
        for suffix in [".SH", ".SZ"]:
            try:
                df = pro.stock_basic(ts_code=code + suffix, fields="ts_code,name")
                if df is not None and len(df) > 0:
                    return code + suffix
            except Exception:
                pass
        # Try as-is
        return code
    if name:
        df = pro.stock_basic(fields="ts_code,name")
        if df is not None and len(df) > 0:
            matches = df[df["name"].str.contains(name, na=False)]
            if len(matches) > 0:
                return matches.iloc[0]["ts_code"]
        return None
    return None


DEFAULT_BASIC_FIELDS = (
    "ts_code,name,area,industry,market,list_date,"
    "curr_type,exchange,province,city"
)

DEFAULT_DAILY_FIELDS = (
    "ts_code,trade_date,close,turnover_rate,turnover_rate_f,"
    "volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,"
    "total_share,float_share,total_mv,circ_mv"
)


def run_stock_info(args) -> dict:
    token = os.environ.get("RR_TUSHARE_TOKEN")
    if not token:
        return {"error": "RR_TUSHARE_TOKEN not set"}

    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()

        # Resolve ts_code
        ts_code = _resolve_ts_code(pro, code=args.code, name=args.name)
        if not ts_code:
            return {"error": f"Cannot resolve: code={args.code}, name={args.name}"}

        # Get basic info
        basic_fields = args.fields if args.fields else DEFAULT_BASIC_FIELDS
        time.sleep(0.3)
        df_basic = pro.stock_basic(ts_code=ts_code, fields=basic_fields)
        if df_basic is None or len(df_basic) == 0:
            return {"error": f"Stock not found: {ts_code}"}

        basic = _df_to_records(df_basic)[0]

        # Get latest valuation from daily_basic
        time.sleep(0.3)
        try:
            df_val = pro.daily_basic(
                ts_code=ts_code, fields=DEFAULT_DAILY_FIELDS
            )
            if df_val is not None and len(df_val) > 0:
                val = _df_to_records(df_val)[0]
                basic.update(val)
        except Exception:
            pass  # valuation is optional

        return {
            "ok": True,
            "data": [basic],
            "meta": {"source": "tushare", "api": "stock_basic+daily_basic"},
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询公司基本信息与最新估值"
    )
    parser.add_argument("--code", "-c", help="股票代码（6位数字，如688256）")
    parser.add_argument("--name", "-n", help="股票名称（模糊匹配）")
    parser.add_argument("--fields", "-f", help="返回字段（逗号分隔）")
    args = parser.parse_args()

    if not args.code and not args.name:
        parser.error("必须指定 --code 或 --name")

    result = run_stock_info(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
