"""Чтение профиля клиента по uid из БД клиентских данных (таблицы schema.sql:
companies, payments, person_company). Только чтение. Если таблиц нет — профиль передают в теле
match_profile(), этот модуль тогда не нужен.
"""

import os
from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from news_parser.core.settings import get_settings
from news_parser.schemas.client import ClientProfile, Counterparty
from news_parser.storage.db import get_engine


class ProfileSourceUnavailable(Exception):
    pass


def _url_from_db_env() -> URL | None:
    """Те же переменные DB_*, что читает data_loader Славика: одна настройка на оба модуля."""
    if not os.getenv("DB_HOST"):
        return None
    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
    )


@lru_cache
def _engine() -> Engine:
    """Приоритет: PROFILES_DATABASE_URL -> переменные DB_* -> та же база, что у парсера."""
    url = get_settings().profiles_database_url or _url_from_db_env()
    return create_engine(url, pool_pre_ping=True) if url else get_engine()


def _top_counterparties(conn, schema: str, uid: str, role: str, limit: int) -> list[Counterparty]:
    # supplier: клиент платит контрагенту; customer: контрагент платит клиенту
    me, other = ("payer", "beneficiary") if role == "supplier" else ("beneficiary", "payer")
    rows = conn.execute(
        text(
            f"""
            SELECT p.{other} AS uid, c.mainokved_code, c.mainokved_name, SUM(p.pay_amt) AS total_amt
            FROM "{schema}".payments p
            JOIN "{schema}".companies c ON c.uid = p.{other}
            WHERE p.{me} = :uid
            GROUP BY p.{other}, c.mainokved_code, c.mainokved_name
            ORDER BY total_amt DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"uid": uid, "limit": limit},
    ).mappings()
    return [
        Counterparty(
            uid=r["uid"],
            role=role,
            mainokved_code=r["mainokved_code"],
            mainokved_name=r["mainokved_name"],
            total_amt=float(r["total_amt"]) if r["total_amt"] is not None else None,
        )
        for r in rows
    ]


def _linked_companies(conn, schema: str, uid: str, limit: int) -> list[Counterparty]:
    """Компании, связанные с клиентом через общих физлиц (person_company)."""
    rows = conn.execute(
        text(
            f"""
            SELECT DISTINCT c.uid, c.mainokved_code, c.mainokved_name
            FROM "{schema}".person_company pc1
            JOIN "{schema}".person_company pc2 ON pc2.fid = pc1.fid AND pc2.uid <> pc1.uid
            JOIN "{schema}".companies c ON c.uid = pc2.uid
            WHERE pc1.uid = :uid
            LIMIT :limit
            """
        ),
        {"uid": uid, "limit": limit},
    ).mappings()
    return [
        Counterparty(uid=r["uid"], role="linked", mainokved_code=r["mainokved_code"], mainokved_name=r["mainokved_name"])
        for r in rows
    ]


def load_profile(uid: str, *, counterparties: int = 5) -> ClientProfile | None:
    schema = get_settings().profiles_db_schema
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(f'SELECT * FROM "{schema}".companies WHERE uid = :uid'), {"uid": uid}).mappings().first()
            if row is None:
                return None
            profile = ClientProfile.model_validate(dict(row))
            profile.counterparties = (
                _top_counterparties(conn, schema, uid, "supplier", counterparties)
                + _top_counterparties(conn, schema, uid, "customer", counterparties)
                + _linked_companies(conn, schema, uid, counterparties)
            )
            return profile
    except DBAPIError as exc:
        raise ProfileSourceUnavailable(
            f"таблицы клиентов недоступны ({schema}.companies / {schema}.payments): {exc.orig!r}"
        ) from exc
