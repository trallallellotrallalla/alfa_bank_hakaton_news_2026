import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "arch")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "alfa_db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

IMPORT_DEPENDENT_PREFIXES = (
    "01", "02", "03",  # Сельское хозяйство
    "05", "06", "07", "08", "09",  # Добыча
    "10", "11", "12", "13", "14", "15", "16", "17", "18",  # Производство
    "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
    "41", "42", "43",  # Строительство
)

EXPORT_ORIENTED_PREFIXES = (
    "05", "06", "07", "08", "09",  # Добыча
    "24", "25",  # Металлургия
    "20",  # Химия
    "02",  # Лес
)

def get_client_info(client_id: str) -> dict:
    """
    Возвращает словарь client в формате, который ожидает LLM-модуль.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Базовые данные о компании (добавили mainokved_code)
            cur.execute("""
                SELECT 
                    uid, 
                    COALESCE(mainokved_code, '00') as okved_code,
                    COALESCE(mainokved_name, 'Неизвестно') as industry,
                    COALESCE(revenue_company, 0) as revenue_rub,
                    COALESCE(region, 'Неизвестно') as region,
                    has_rko, has_loa, has_lea, has_dep, has_gar, has_zpp, has_factoring
                FROM companies 
                WHERE uid = %s
            """, (client_id,))
            row = cur.fetchone()

            if not row:
                return {"error": f"Компания {client_id} не найдена"}

            # 2. Продукты (приводим к bool, чтобы не было null в JSON)
            products = {
                "rko": bool(row["has_rko"]),
                "loa": bool(row["has_loa"]),
                "lea": bool(row["has_lea"]),
                "dep": bool(row["has_dep"]),
                "gar": bool(row["has_gar"]),
                "zpp": bool(row["has_zpp"]),
                "factoring": bool(row["has_factoring"])
            }

            # 3. Топ-контрагентов
            cur.execute("""
                SELECT counterparty 
                FROM top_counterparties 
                WHERE uid = %s AND rnk <= 5 AND counterparty != uid
                ORDER BY total_amt DESC
            """, (client_id,))
            top_counterparties = [r["counterparty"] for r in cur.fetchall()]

            # 4. Связанные компании (через общих физлиц)
            cur.execute("""
                SELECT DISTINCT pc2.uid 
                FROM person_company pc1
                JOIN person_company pc2 ON pc1.fid = pc2.fid
                WHERE pc1.uid = %s AND pc2.uid != %s
                LIMIT 10
            """, (client_id, client_id))
            linked_companies = [r["uid"] for r in cur.fetchall()]

            # 5. Регионы физлиц (считаем долю)
            # Используем COALESCE, чтобы не терять людей без региона
            cur.execute("""
                WITH people AS (
                    SELECT COALESCE(p.rc_name, 'Неизвестно') AS region
                    FROM person_company pc
                    JOIN persons p ON pc.fid = p.fid
                    WHERE pc.uid = %s
                ),
                total AS (
                    SELECT COUNT(*) as cnt FROM people
                )
                SELECT 
                    region, 
                    ROUND((COUNT(*)::numeric / NULLIF((SELECT cnt FROM total), 0)), 2) as share
                FROM people
                GROUP BY region
                ORDER BY share DESC
            """, (client_id,))
            people_regions = [{"region": r["region"], "share": float(r["share"])} for r in cur.fetchall()]

            # 6. Сигналы (по коду ОКВЭД, а не по названию)
            okved = str(row["okved_code"]).strip()
            okved_prefix = okved[:2]

            # Зависимость от импорта
            if okved_prefix in IMPORT_DEPENDENT_PREFIXES:
                import_dep = "high"
            elif okved_prefix in ("45", "46", "47", "52"):
                import_dep = "medium"  # торговля/логистика — смешанная
            else:
                import_dep = "low"

            # Валютная экспозиция (если есть факторинг или отрасль экспортная)
            if row["has_factoring"]:
                fx_exposure = "high"
            elif okved_prefix in EXPORT_ORIENTED_PREFIXES:
                fx_exposure = "medium"
            else:
                fx_exposure = "low"

            # Кредитная зависимость (если есть кредит и выручка < 20 млрд)
            if row["has_loa"] and row["revenue_rub"] < 20e9:
                credit_dependency = "high"
            elif row["has_loa"]:
                credit_dependency = "medium"
            else:
                credit_dependency = "low"

            client_data = {
                "client_id": row["uid"],
                "industry": row["industry"],
                "revenue_rub": int(row["revenue_rub"]),
                "region": row["region"],
                "products": products,
                "signals": {
                    "credit_dependency": credit_dependency,
                    "fx_exposure": fx_exposure,
                    "import_dependency": import_dep
                },
                "top_counterparties": top_counterparties,
                "linked_companies": linked_companies,
                "people_regions": people_regions
            }

            return client_data
    finally:
        conn.close()


if __name__ == "__main__":
    test_id = "U_10"
    profile = get_client_info(test_id)
    print(json.dumps(profile, ensure_ascii=False, indent=2))