import pandas as pd
from psycopg2.extras import execute_values
from .config import get_connection


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower().replace('"', '').replace("'", "") for c in df.columns]
    return df


def _clean_id(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return None
    return str(val).strip().replace('"', '').replace("'", "").replace(' ', '')


def _to_bool(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)): return False
    if isinstance(value, str): return value.strip().lower() in ("1", "true", "yes", "y", "t", "1.0")
    try:
        return bool(int(float(value)))
    except (ValueError, TypeError):
        return bool(value)


def _to_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    if isinstance(value, str): value = value.replace(',', '.').strip()
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _to_str(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    return str(value).strip() or None


def _read_csv_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=';', encoding='utf-8', dtype=str, on_bad_lines='skip')
    return _clean_columns(df)


def _ensure_companies_exist(conn, missing_uids: set, source_name: str) -> int:
    if not missing_uids: return 0
    rows = [(uid, 'MISSING_IN_SOURCE', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ') for uid in missing_uids]
    with conn.cursor() as cur:
        execute_values(cur,
                       "INSERT INTO companies (uid, org_type, okfs_name, mainokved_name, city, region) VALUES %s ON CONFLICT (uid) DO NOTHING",
                       rows, page_size=5000)
    conn.commit()
    return len(rows)


# --- Лоадеры ---
def load_companies(conn, path: str) -> int:
    df = _read_csv_clean(path)
    if "synthetic_u" not in df.columns: raise ValueError("Нет synthetic_u")
    df = df.dropna(subset=["synthetic_u"])
    df["synthetic_u"] = df["synthetic_u"].apply(_clean_id)

    rows = []
    for _, r in df.iterrows():
        uid = r["synthetic_u"]
        if not uid: continue
        rows.append((
            uid, _to_str(r.get("org_type")), _to_str(r.get("okfs_name")),
            _to_str(r.get("company_age_years_gradation")), _to_str(r.get("eco_mark_label")),
            _to_str(r.get("mainokved_code")), _to_str(r.get("mainokved_name")),
            _to_bool(r.get("negativemark")), _to_str(r.get("amount_workers_fns_gradation")),
            _to_str(r.get("amount_workers_spark_gradation")), _to_str(r.get("cl_type")),
            _to_bool(r.get("cl_product_rko_mark")), _to_bool(r.get("cl_product_gar_mark")),
            _to_bool(r.get("cl_product_loa_mark")), _to_bool(r.get("cl_product_lea_mark")),
            _to_bool(r.get("cl_product_dep_mark")), _to_bool(r.get("cl_product_zpp_mark")),
            _to_bool(r.get("fts_flag")), _to_str(r.get("fts_country_name")),
            _to_bool(r.get("factoring_mark")), _to_float(r.get("revenue_company")),
            _to_str(r.get("group_id")), _to_str(r.get("city")), _to_str(r.get("region")),
        ))
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO companies (uid, org_type, okfs_name, company_age_years_gradation, eco_mark_label, mainokved_code, mainokved_name, negativemark, workers_fns_gradation, workers_spark_gradation, cl_type, has_rko, has_gar, has_loa, has_lea, has_dep, has_zpp, fts_flag, fts_country_name, has_factoring, revenue_company, group_id, city, region) 
            VALUES %s ON CONFLICT (uid) DO NOTHING
        """, rows, page_size=1000)
    conn.commit()
    return len(rows)


def load_persons(conn, path: str) -> int:
    df = _read_csv_clean(path)
    if "synthetic_f" not in df.columns: raise ValueError("Нет synthetic_f")
    df["synthetic_f"] = df["synthetic_f"].apply(_clean_id)
    persons = df.dropna(subset=["synthetic_f"]).drop_duplicates("synthetic_f")
    rows = [(r["synthetic_f"], _to_str(r.get("city_name")), _to_str(r.get("rc_name"))) for _, r in persons.iterrows()]
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO persons (fid, city_name, rc_name) VALUES %s ON CONFLICT (fid) DO NOTHING",
                       rows, page_size=1000)
    conn.commit()
    return len(rows)


def load_person_company(conn, path: str) -> int:
    df = _read_csv_clean(path)
    if not {"synthetic_f", "synthetic_u"}.issubset(df.columns): raise ValueError("Нет нужных колонок")
    df["synthetic_f"] = df["synthetic_f"].apply(_clean_id)
    df["synthetic_u"] = df["synthetic_u"].apply(_clean_id)
    links = df.dropna(subset=["synthetic_f", "synthetic_u"])[["synthetic_f", "synthetic_u"]].drop_duplicates()
    link_uids = set(links["synthetic_u"].unique())
    with conn.cursor() as cur:
        cur.execute("SELECT uid FROM companies")
        valid_uids = {row[0] for row in cur.fetchall()}
    _ensure_companies_exist(conn, link_uids - valid_uids, "person_company")
    rows = [(r["synthetic_f"], r["synthetic_u"]) for _, r in links.iterrows()]
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO person_company (fid, uid) VALUES %s ON CONFLICT (fid, uid) DO NOTHING", rows,
                       page_size=1000)
    conn.commit()
    return len(rows)


def load_payments(conn, path: str) -> int:
    df = _read_csv_clean(path)
    if not {"payer", "beneficiary", "pay_amt", "pay_cnt"}.issubset(df.columns): raise ValueError("Нет нужных колонок")
    df["payer"] = df["payer"].apply(_clean_id)
    df["beneficiary"] = df["beneficiary"].apply(_clean_id)
    df = df.dropna(subset=["payer", "beneficiary"])
    agg = df.groupby(["payer", "beneficiary"], as_index=False).agg(
        pay_amt=("pay_amt", lambda x: sum(_to_float(v) or 0 for v in x)),
        pay_cnt=("pay_cnt", lambda x: sum(_to_int(v) or 0 for v in x))
    )
    pay_uids = set(agg["payer"].unique()) | set(agg["beneficiary"].unique())
    with conn.cursor() as cur:
        cur.execute("SELECT uid FROM companies")
        valid_uids = {row[0] for row in cur.fetchall()}
    _ensure_companies_exist(conn, pay_uids - valid_uids, "payments")
    rows = [(r["payer"], r["beneficiary"], r["pay_amt"], r["pay_cnt"]) for _, r in agg.iterrows()]
    with conn.cursor() as cur:
        execute_values(cur,
                       "INSERT INTO payments (payer, beneficiary, pay_amt, pay_cnt) VALUES %s ON CONFLICT (payer, beneficiary) DO UPDATE SET pay_amt = EXCLUDED.pay_amt, pay_cnt = EXCLUDED.pay_cnt",
                       rows, page_size=1000)
    conn.commit()
    return len(rows)


def load_all_data(csv_companies: str, csv_persons: str, csv_payments: str):
    """Загрузка данных CSV -> БД."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE payments, person_company, persons CASCADE;")
        conn.commit()

        c = load_companies(conn, csv_companies)
        p = load_persons(conn, csv_persons)
        pc = load_person_company(conn, csv_persons)
        pay = load_payments(conn, csv_payments)

        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW top_counterparties;")
        conn.commit()

        print(f"[insertClientsData] Загрузка завершена. Компаний: {c}, Физлиц: {p}, Связей: {pc}, Платежей: {pay}")
    finally:
        conn.close()