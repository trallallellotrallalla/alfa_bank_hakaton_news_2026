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


def get_client_info(client_id: str) -> dict:
    """
    Возвращает словарь client в формате, который ожидает LLM-модуль.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем базовые данные о компании
            cur.execute("""
                SELECT 
                    uid, 
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

            products = {
                "rko": row["has_rko"],
                "loa": row["has_loa"],
                "lea": row["has_lea"],
                "dep": row["has_dep"],
                "gar": row["has_gar"],
                "zpp": row["has_zpp"],
                "factoring": row["has_factoring"]
            }

            # Получаем топ-контрагентов (из материализованного представления)
            cur.execute("""
                SELECT counterparty 
                FROM top_counterparties 
                WHERE uid = %s AND rnk <= 5
                ORDER BY total_amt DESC
            """, (client_id,))
            top_counterparties = [r["counterparty"] for r in cur.fetchall()]

            # Получаем связанные компании (через общих физлиц)
            cur.execute("""
                SELECT DISTINCT pc2.uid 
                FROM person_company pc1
                JOIN person_company pc2 ON pc1.fid = pc2.fid
                WHERE pc1.uid = %s AND pc2.uid != %s
                LIMIT 10
            """, (client_id, client_id))
            linked_companies = [r["uid"] for r in cur.fetchall()]

            # Считаем долю каждого региона от общего числа связанных людей
            cur.execute("""
                WITH people AS (
                    SELECT p.rc_name AS region
                    FROM person_company pc
                    JOIN persons p ON pc.fid = p.fid
                    WHERE pc.uid = %s AND p.rc_name IS NOT NULL
                ),
                total AS (
                    SELECT COUNT(*) as cnt FROM people
                )
                SELECT 
                    region, 
                    ROUND((COUNT(*)::numeric / (SELECT cnt FROM total)), 2) as share
                FROM people
                GROUP BY region
                ORDER BY share DESC
            """, (client_id,))
            people_regions = [{"region": r["region"], "share": float(r["share"])} for r in cur.fetchall()]

            # Вычисляем сигналы (эвристики на основе продуктов и данных)
            credit_dependency = "high" if row["has_loa"] and row["revenue_rub"] < 20e9 else (
                "medium" if row["has_loa"] else "low")
            # Валютная экспозиция: если есть факторинг или компания связана с импортом (упрощенно)
            fx_exposure = "high" if row["has_factoring"] else "medium"
            # Зависимость от импорта: если ОКВЭД начинается на 45, 46, 47 (торговля) или 52 (логистика)
            import_dep = "high" if str(row["industry"]).lower().startswith(("торговля", "деятельность")) else "low"

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
    test_id = "U_161022"
    profile = get_client_info(test_id)
    print(json.dumps(profile, ensure_ascii=False, indent=2))