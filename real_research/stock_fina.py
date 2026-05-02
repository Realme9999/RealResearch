"""RealResearch: rr-stock-fina — 查询公司财务报表（利润表/资产负债表/现金流量表）

返回指定报告期的财务数据，支持年报和季报。
报告期格式：YYYY（年报）、YYYYQ1-Q4（季报）、YYYYMMDD。

Usage:
    rr-stock-fina --code 688256 --period 2025           # 2025年报
    rr-stock-fina --code 688256 --period 2025Q3         # 2025三季报
    rr-stock-fina --code 688256 --period 2024 --type income  # 只看利润表
"""
import argparse
import json
import os
import sys
import math
import re
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


def _resolve_ts_code(pro, code: str) -> str:
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


def _parse_period(period: str) -> str:
    """Convert period string to Tushare report_date (YYYYMMDD).

    Supported formats:
        2025     -> 20251231 (年报)
        2025Q1   -> 20250331 (一季报)
        2025Q2   -> 20250630 (中报)
        2025Q3   -> 20250930 (三季报)
        2025Q4   -> 20251231 (年报)
        20250331 -> 20250331 (原始格式)
    """
    period = period.strip()

    # Already YYYYMMDD
    if re.match(r"^\d{8}$", period):
        return period

    # YYYYQN format
    m = re.match(r"^(\d{4})Q([1-4])$", period, re.IGNORECASE)
    if m:
        year = m.group(1)
        q = int(m.group(2))
        end_dates = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        return year + end_dates[q]

    # Plain YYYY -> annual report
    m = re.match(r"^(\d{4})$", period)
    if m:
        return m.group(1) + "1231"

    return period


INCOME_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,"
    "revenue,oper_cost,total_profit,operate_profit,n_income,n_income_attr_p,"
    "basic_eps,diluted_eps,total_cogs,sell_exp,admin_exp,rd_exp,fin_exp"
)

BALANCE_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,"
    "total_assets,total_liab,total_hldr_eqy_exc_min_int,"
    "total_cur_assets,total_nca,total_cur_liab,total_ncl,"
    "money_cap,accounts_receiv,inventories,fix_assets,long_eqy_inv"
)

CASHFLOW_FIELDS = (
    "ts_code,ann_date,f_ann_date,end_date,report_type,update_flag,"
    "n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act,"
    "c_fr_sale_sg,pay_all_tax_payable,c_pay_acq_const_fiamt"
)


def run_stock_fina(args) -> dict:
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
        report_date = _parse_period(args.period)

        want_types = []
        if args.type:
            want_types = [t.strip().lower() for t in args.type.split(",")]
        else:
            want_types = ["income", "balance", "cashflow"]

        result = {
            "ok": True,
            "code": ts_code,
            "name": name,
            "period": report_date,
        }

        # Fetch income statement
        if "income" in want_types:
            time.sleep(0.3)
            df = pro.income(ts_code=ts_code, period=report_date, fields=INCOME_FIELDS)
            result["income"] = _df_to_records(df) if df is not None and len(df) > 0 else []

        # Fetch balance sheet
        if "balance" in want_types:
            time.sleep(0.3)
            df = pro.balancesheet(ts_code=ts_code, period=report_date, fields=BALANCE_FIELDS)
            result["balance"] = _df_to_records(df) if df is not None and len(df) > 0 else []

        # Fetch cash flow
        if "cashflow" in want_types:
            time.sleep(0.3)
            df = pro.cashflow(ts_code=ts_code, period=report_date, fields=CASHFLOW_FIELDS)
            result["cashflow"] = _df_to_records(df) if df is not None and len(df) > 0 else []

        result["meta"] = {
            "source": "tushare",
            "api": "+".join(want_types),
            "report_type": "年报" if report_date.endswith("1231") else "季报/中报",
        }

        return result

    except Exception as e:
        return {"error": str(e)}


def main():
    setup_utf8()
    parser = argparse.ArgumentParser(
        description="RealResearch: 查询公司财务报表（利润表/资产负债表/现金流量表）"
    )
    parser.add_argument("--code", "-c", required=True, help="股票代码（6位数字，如688256）")
    parser.add_argument(
        "--period", "-p", required=True,
        help="报告期：YYYY（年报）、YYYYQ1-Q4（季报）、YYYYMMDD"
    )
    parser.add_argument(
        "--type", "-t",
        help="报表类型：income/balance/cashflow（逗号分隔，默认全部）"
    )
    args = parser.parse_args()

    result = run_stock_fina(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
