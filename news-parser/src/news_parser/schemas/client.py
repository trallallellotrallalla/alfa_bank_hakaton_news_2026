"""Профиль клиента — формат данных из модуля клиентских данных.

Поля ClientProfile совпадают с колонками таблицы companies (schema.sql), так что строку
из БД можно передавать как есть. Контрагенты — из payments и person_company.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Counterparty(BaseModel):
    """Крупный контрагент из графа платежей (payments). Названий нет — данные
    обезличены, — поэтому важна его отрасль: риски в цепочке поставок."""

    uid: str | None = None
    # supplier — клиент платит ему; customer — он платит клиенту;
    # linked — связан через общих физлиц (владельцы/руководители), без платежей
    role: Literal["supplier", "customer", "linked"] = "supplier"
    mainokved_code: str | None = None
    mainokved_name: str | None = None
    total_amt: float | None = None


class ClientProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uid: str | None = None
    org_type: str | None = None
    okfs_name: str | None = None
    company_age_years_gradation: str | None = None
    eco_mark_label: str | None = None
    mainokved_code: str | None = None
    mainokved_name: str | None = None
    negativemark: bool | None = None
    workers_fns_gradation: str | None = None
    workers_spark_gradation: str | None = None
    cl_type: str | None = None
    has_rko: bool | None = None
    has_gar: bool | None = None
    has_loa: bool | None = None
    has_lea: bool | None = None
    has_dep: bool | None = None
    has_zpp: bool | None = None
    fts_flag: bool | None = None
    fts_country_name: str | None = None
    has_factoring: bool | None = None
    revenue_company: float | None = None
    group_id: str | None = None
    city: str | None = None
    region: str | None = None
    counterparties: list[Counterparty] = []
    # Готовые сигналы из модуля клиентских данных (data_loader.get_client_info):
    # credit_dependency / fx_exposure / import_dependency = low | medium | high.
    # Меняют вес аспектов; аспект ВЭД создают только данные ФТС (fts_flag).
    signals: dict[str, str] = {}
