# data_loader

Модуль для работы с базой данных клиентов (юридических лиц и связанных физлиц). Отвечает за **загрузку данных из CSV в PostgreSQL** и **получение персонализированного профиля клиента** в формате, готовом для передачи в RAG-модуль.

---

## Структура модуля

```text
data_loader/
├── __init__.py             # Экспорт публичных функций
├── config.py               # Настройки подключения к БД (из .env)
├── load_clients_data.py    # Загрузка CSV → PostgreSQL
└── get_client_info.py      # Сборка профиля клиента (JSON для LLM)
```

---

## Требования к окружению

- Python 3.9+
- PostgreSQL 14+ (с расширением `pg_trgm` для поиска, опционально)
- Установленные зависимости:

```bash
pip install pandas psycopg2-binary python-dotenv
```

---

## Настройка `.env`

В корне проекта должен лежать файл `.env`:

```env
DB_USER=arch
DB_PASSWORD=password
DB_NAME=alfa_db
DB_HOST=localhost
DB_PORT=5432
```

*Если переменные не заданы, используются значения по умолчанию (см. `config.py`).*

---

## Схема базы данных

Перед первым запуском модуля убедитесь, что в БД созданы таблицы и материализованное представление. Минимальный SQL:

```sql
CREATE TABLE IF NOT EXISTS companies (
    uid TEXT PRIMARY KEY,
    org_type TEXT,
    okfs_name TEXT,
    company_age_years_gradation TEXT,
    eco_mark_label TEXT,
    mainokved_code TEXT,
    mainokved_name TEXT,
    negativemark BOOLEAN,
    workers_fns_gradation TEXT,
    workers_spark_gradation TEXT,
    cl_type TEXT,
    has_rko BOOLEAN DEFAULT FALSE,
    has_gar BOOLEAN DEFAULT FALSE,
    has_loa BOOLEAN DEFAULT FALSE,
    has_lea BOOLEAN DEFAULT FALSE,
    has_dep BOOLEAN DEFAULT FALSE,
    has_zpp BOOLEAN DEFAULT FALSE,
    fts_flag BOOLEAN DEFAULT FALSE,
    fts_country_name TEXT,
    has_factoring BOOLEAN DEFAULT FALSE,
    revenue_company NUMERIC,
    group_id TEXT,
    city TEXT,
    region TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    fid TEXT PRIMARY KEY,
    city_name TEXT,
    rc_name TEXT
);

CREATE TABLE IF NOT EXISTS person_company (
    fid TEXT REFERENCES persons(fid) ON DELETE CASCADE,
    uid TEXT REFERENCES companies(uid) ON DELETE CASCADE,
    PRIMARY KEY (fid, uid)
);

CREATE TABLE IF NOT EXISTS payments (
    payer TEXT REFERENCES companies(uid) ON DELETE CASCADE,
    beneficiary TEXT REFERENCES companies(uid) ON DELETE CASCADE,
    pay_amt NUMERIC,
    pay_cnt INTEGER,
    PRIMARY KEY (payer, beneficiary)
);

CREATE MATERIALIZED VIEW IF NOT EXISTS top_counterparties AS
SELECT payer AS uid, beneficiary AS counterparty,
       SUM(pay_amt) AS total_amt, SUM(pay_cnt) AS total_cnt,
       RANK() OVER (PARTITION BY payer ORDER BY SUM(pay_amt) DESC) AS rnk
FROM payments
GROUP BY payer, beneficiary;

CREATE INDEX IF NOT EXISTS idx_top_counterparties_uid ON top_counterparties (uid, rnk);
```

---

## Загрузка данных

Функция `load_all_data` выполняет полный цикл загрузки:

- Очищает таблицы `payments`, `person_company`, `persons` (компании не очищаются, чтобы сохранить «призраков»).
- Загружает компании (`df_Uid_data_hack.csv`).
- Загружает физлиц (`df_Fid_Uid_link_hack.csv`).
- Загружает связи физлицо ↔ компания (из того же файла).
- Загружает платежи (`df_Uid_payment_hack.csv`).
- Обновляет материализованное представление `top_counterparties`.

**Пример:**

```python
from data_loader import load_all_data

load_all_data(
    csv_companies="df_Uid_data_hack.csv",
    csv_persons="df_Fid_Uid_link_hack.csv",
    csv_payments="df_Uid_payment_hack.csv"
)
```

**Особенности:**

- **Разделитель CSV** — строго `;` (как в исходных файлах кейса).
- **Пустые строки** и строки без `synthetic_u` / `synthetic_f` — отбрасываются.
- **Компании-призраки**: если в файлах связей или платежей встречается ID, которого нет в `companies`, модуль автоматически создаёт запись с `org_type = 'MISSING_IN_SOURCE'`. Это нужно, чтобы не нарушать `FOREIGN KEY`.
- **Платежи** агрегируются по паре `(payer, beneficiary)` — если в CSV несколько строк на одну пару, суммы складываются.
- **`TRUNCATE`** касается только таблиц `payments`, `person_company`, `persons`. Компании не удаляются, чтобы не потерять `MISSING_IN_SOURCE`.

---

## Получение профиля клиента

Функция `get_client_info(client_id)` возвращает JSON-словарь с полями, готовыми для передачи в LLM.

**Пример:**

```python
from data_loader import get_client_info
import json

profile = get_client_info("U_123456")
print(json.dumps(profile, ensure_ascii=False, indent=2))
```

**Что возвращает функция:**

```json
{
  "client_id": "U_123456",
  "industry": "Деятельность автомобильного грузового транспорта",
  "revenue_rub": 18500000000,
  "region": "Москва",
  "products": {
    "rko": true,
    "loa": true,
    "lea": false,
    "dep": true,
    "gar": true,
    "zpp": true,
    "factoring": false
  },
  "signals": {
    "credit_dependency": "high",
    "fx_exposure": "medium",
    "import_dependency": "high"
  },
  "top_counterparties": ["U_201", "U_305"],
  "linked_companies": ["U_201", "U_412"],
  "people_regions": [
    {"region": "Москва", "share": 0.62},
    {"region": "Санкт-Петербург", "share": 0.23},
    {"region": "Казань", "share": 0.15}
  ]
}
```

**Что происходит внутри:**

1. **Базовые данные** — берутся из `companies`.
2. **Продукты** — конвертируются в `bool` (чтобы в JSON были `true/false`, а не `null`).
3. **Топ-контрагенты** — из `top_counterparties` (первые 5, исключая саму компанию).
4. **Связанные компании** — через общих физлиц в `person_company`.
5. **Регионы физлиц** — считаются как доля от общего числа связанных людей (пустые регионы группируются как «Неизвестно»).
6. **Сигналы** — эвристики на основе ОКВЭД и флагов продуктов:
   - `credit_dependency`: `high` — если есть кредит и выручка < 20 млрд; `medium` — если есть кредит, но выручка больше; `low` — если кредита нет.
   - `fx_exposure`: `high` — если есть факторинг; `medium` — если отрасль экспортно-ориентированная (добыча, металлургия, химия); `low` — иначе.
   - `import_dependency`: `high` — если ОКВЭД начинается на отрасли из `IMPORT_DEPENDENT_PREFIXES` (сельское хозяйство, добыча, производство, строительство); `medium` — для торговли (45-47) и логистики (52); `low` — иначе.

**Обратите внимание:** 
- Если компания не найдена, возвращается `{"error": "..."}`.
- Фильтр `counterparty != uid` в топ-контрагентах исключает саму компанию.
- Если у клиента нет связанных физлиц, `linked_companies` и `people_regions` будут пустыми списками (это нормально).

---

## Тестирование

В файле `get_clients_info.py` есть блок `if __name__ == "__main__":` для быстрой проверки.

**Проверить получение профиля:**

```bash
python -m data_loader.get_client_info
```

---

## Зависимости

Модуль использует:

- `pandas` — чтение CSV.
- `psycopg2-binary` — работа с PostgreSQL.
- `python-dotenv` — загрузка переменных из `.env`.

---

## 🛠️ Известные ограничения

1. **Разделитель CSV** — жёстко задан `;`. Если в будущем формат изменится, потребуется правка `_read_csv_clean`.
2. **Эвристики сигналов** — упрощены. В продакшене их следует вычислять в отдельном пайплайне на основе финансовых данных и транзакций.
3. **«Компании-призраки»** — создаются для всех ID из связей и платежей, которых нет в `companies`. Это защищает от `ForeignKeyViolation`, но загрязняет таблицу `companies` записями с `org_type = 'MISSING_IN_SOURCE'`. В будущем можно добавить флаг `is_real` или вынести их в отдельную таблицу.
4. **`TRUNCATE`** — очищает `payments`, `person_company`, `persons`, но не `companies`. Если нужно загрузить всё с нуля, выполните `TRUNCATE companies CASCADE` вручную.
