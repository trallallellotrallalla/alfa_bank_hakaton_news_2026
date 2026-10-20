import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "arch")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "alfa_db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

CSV_COMPANIES = "df_Uid_data_hack.csv"
CSV_PERSONS = "df_Fid_Uid_link_hack.csv"
CSV_PAYMENTS = "df_Uid_payment_hack.csv"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит названия колонок к нижнему регистру и убирает пробелы."""
    df.columns = [str(c).strip().lower().replace('"', '').replace("'", "") for c in df.columns]
    return df


def clean_id(val):
    """Убирает кавычки, пробелы и прочий мусор из ID."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip().replace('"', '').replace("'", "").replace(' ', '')


def read_csv_clean(path: str) -> pd.DataFrame:
    """Стандартное, надежное чтение CSV."""
    print(f"\n--- Чтение файла: {path} ---")
    df = pd.read_csv(
        path,
        sep=';',
        encoding='utf-8',
        dtype=str,
        on_bad_lines='skip'
    )
    df = clean_columns(df)
    print(f"Прочитано строк: {len(df)}")
    return df


def to_bool(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)): return False
    if isinstance(value, str): return value.strip().lower() in ("1", "true", "yes", "y", "t", "1.0")
    try:
        return bool(int(float(value)))
    except (ValueError, TypeError):
        return bool(value)


def to_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    if isinstance(value, str):
        value = value.replace(',', '.').strip()
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def to_int(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def to_str(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    return str(value).strip() or None


def ensure_companies_exist(conn, missing_uids: set, source_name: str) -> int:
    if not missing_uids:
        return 0

    print(f"[{source_name}] Обнаружено {len(missing_uids)} ID, которых нет в базе. Создаем 'призраков'...")

    rows = [(uid, 'MISSING_IN_SOURCE', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ', 'НЕТ ДАННЫХ') for uid in missing_uids]

    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO companies (uid, org_type, okfs_name, mainokved_name, city, region) VALUES %s ON CONFLICT (uid) DO NOTHING",
            rows, page_size=5000
        )
    conn.commit()
    return len(rows)


def load_companies(conn, path: str) -> int:
    df = read_csv_clean(path)

    if "synthetic_u" not in df.columns:
        raise ValueError(f"В companies нет колонки synthetic_u. Найдены: {df.columns.tolist()}")

    initial_count = len(df)
    df = df.dropna(subset=["synthetic_u"])
    dropped = initial_count - len(df)
    if dropped > 0:
        print(f"[companies] Отброшено {dropped} пустых строк.")

    df["synthetic_u"] = df["synthetic_u"].apply(clean_id)

    rows = []
    for _, r in df.iterrows():
        uid = r["synthetic_u"]
        if not uid: continue
        rows.append((
            uid, to_str(r.get("org_type")), to_str(r.get("okfs_name")),
            to_str(r.get("company_age_years_gradation")), to_str(r.get("eco_mark_label")),
            to_str(r.get("mainokved_code")), to_str(r.get("mainokved_name")),
            to_bool(r.get("negativemark")), to_str(r.get("amount_workers_fns_gradation")),
            to_str(r.get("amount_workers_spark_gradation")), to_str(r.get("cl_type")),
            to_bool(r.get("cl_product_rko_mark")), to_bool(r.get("cl_product_gar_mark")),
            to_bool(r.get("cl_product_loa_mark")), to_bool(r.get("cl_product_lea_mark")),
            to_bool(r.get("cl_product_dep_mark")), to_bool(r.get("cl_product_zpp_mark")),
            to_bool(r.get("fts_flag")), to_str(r.get("fts_country_name")),
            to_bool(r.get("factoring_mark")), to_float(r.get("revenue_company")),
            to_str(r.get("group_id")), to_str(r.get("city")), to_str(r.get("region")),
        ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO companies (
                uid, org_type, okfs_name, company_age_years_gradation,
                eco_mark_label, mainokved_code, mainokved_name, negativemark,
                workers_fns_gradation, workers_spark_gradation, cl_type,
                has_rko, has_gar, has_loa, has_lea, has_dep, has_zpp,
                fts_flag, fts_country_name, has_factoring,
                revenue_company, group_id, city, region
            ) VALUES %s ON CONFLICT (uid) DO NOTHING
            """, rows, page_size=1000,
        )
    conn.commit()
    print(f"[companies] Загружено {len(rows)} уникальных компаний в БД.")
    return len(rows)


def load_persons(conn, path: str) -> int:
    df = read_csv_clean(path)
    if "synthetic_f" not in df.columns:
        raise ValueError(f"В persons нет колонки synthetic_f. Найдены: {df.columns.tolist()}")

    df["synthetic_f"] = df["synthetic_f"].apply(clean_id)
    persons = df.dropna(subset=["synthetic_f"]).drop_duplicates("synthetic_f")

    rows = [(r["synthetic_f"], to_str(r.get("city_name")), to_str(r.get("rc_name"))) for _, r in persons.iterrows()]

    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO persons (fid, city_name, rc_name) VALUES %s ON CONFLICT (fid) DO NOTHING",
                       rows, page_size=1000)
    conn.commit()
    print(f"[persons] Загружено {len(rows)} физлиц.")
    return len(rows)


def load_person_company(conn, path: str) -> int:
    df = read_csv_clean(path)
    if not {"synthetic_f", "synthetic_u"}.issubset(df.columns):
        raise ValueError(f"В связях нет нужных колонок. Найдены: {df.columns.tolist()}")

    df["synthetic_f"] = df["synthetic_f"].apply(clean_id)
    df["synthetic_u"] = df["synthetic_u"].apply(clean_id)

    links = df.dropna(subset=["synthetic_f", "synthetic_u"])[["synthetic_f", "synthetic_u"]].drop_duplicates()

    link_uids = set(links["synthetic_u"].unique())
    with conn.cursor() as cur:
        cur.execute("SELECT uid FROM companies")
        valid_uids = {row[0] for row in cur.fetchall()}

    missing_uids = link_uids - valid_uids
    ghosts = ensure_companies_exist(conn, missing_uids, "person_company")

    rows = [(r["synthetic_f"], r["synthetic_u"]) for _, r in links.iterrows()]
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO person_company (fid, uid) VALUES %s ON CONFLICT (fid, uid) DO NOTHING", rows,
                       page_size=1000)
    conn.commit()
    print(f"[person_company] Загружено {len(rows)} связей. Создано призраков: {ghosts}")
    return len(rows)


def load_payments(conn, path: str) -> int:
    df = read_csv_clean(path)

    required = {"payer", "beneficiary", "pay_amt", "pay_cnt"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В файле платежей нет колонок: {missing}. Найдены: {df.columns.tolist()}")

    df["payer"] = df["payer"].apply(clean_id)
    df["beneficiary"] = df["beneficiary"].apply(clean_id)

    initial_count = len(df)
    df = df.dropna(subset=["payer", "beneficiary"])
    dropped = initial_count - len(df)
    if dropped > 0:
        print(f"[payments] Отброшено {dropped} строк с пустыми ID.")

    # Агрегация
    print(f"[payments] Начинаем агрегацию {len(df)} строк...")
    agg = df.groupby(["payer", "beneficiary"], as_index=False).agg(
        pay_amt=("pay_amt", lambda x: sum(to_float(v) or 0 for v in x)),
        pay_cnt=("pay_cnt", lambda x: sum(to_int(v) or 0 for v in x))
    )

    pay_uids = set(agg["payer"].unique()) | set(agg["beneficiary"].unique())
    with conn.cursor() as cur:
        cur.execute("SELECT uid FROM companies")
        valid_uids = {row[0] for row in cur.fetchall()}

    missing_uids = pay_uids - valid_uids
    ghosts = ensure_companies_exist(conn, missing_uids, "payments")

    rows = [(r["payer"], r["beneficiary"], r["pay_amt"], r["pay_cnt"]) for _, r in agg.iterrows()]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO payments (payer, beneficiary, pay_amt, pay_cnt)
            VALUES %s ON CONFLICT (payer, beneficiary) DO UPDATE
            SET pay_amt = EXCLUDED.pay_amt, pay_cnt = EXCLUDED.pay_cnt
            """,
            rows, page_size=1000,
        )
    conn.commit()
    print(f"[payments] Загружено {len(rows)} агрегированных транзакций. Создано призраков: {ghosts}")
    return len(rows)


def refresh_views(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW top_counterparties;")
        conn.commit()
        print("[views] top_counterparties обновлено")
    except psycopg2.errors.UndefinedTable:
        print("[views] ВНИМАНИЕ: top_counterparties не существует. Проверить init.sql")


def main() -> None:
    print(f"Подключение к {DATABASE_URL}...")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        print("ЭТАП 1: Загрузка реальных компаний")
        c_count = load_companies(conn, CSV_COMPANIES)

        print("ЭТАП 2: Загрузка физлиц")
        p_count = load_persons(conn, CSV_PERSONS)

        print("ЭТАП 3: Связи (физлица - компании)")
        pc_count = load_person_company(conn, CSV_PERSONS)

        print("ЭТАП 4: Платежи")
        pay_count = load_payments(conn, CSV_PAYMENTS)

        print("ИТОГОВАЯ СТАТИСТИКА:")
        print(f"Компаний в базе: {c_count}")
        print(f"Физлиц в базе: {p_count}")
        print(f"Связей в базе: {pc_count}")
        print(f"Агрегированных транзакций в базе: {pay_count}")

        refresh_views(conn)
    finally:
        conn.close()
        print("\nГотово. Соединение закрыто.")


if __name__ == "__main__":
    main()