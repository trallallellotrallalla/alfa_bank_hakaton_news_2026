"""Готовый текстовый контекст для промпта локальной LLM.

Агент может вставить поле `context` в промпт как есть: в нём профиль клиента,
новости с фактами и фрагментами текста, аналитика банка. Каждый блок помечен
ref-меткой ([N1], [A1]), чтобы модель ссылалась на источники, а агент мог
восстановить, на чём основан вывод. Новости (внешние факты) и аналитика
(позиция банка) разведены по разным разделам — это требование ТЗ.

Длина ограничена max_context_chars: у локальной модели маленькое окно, поэтому
блоки добавляются по убыванию важности, пока помещаются.
"""

from typing import TYPE_CHECKING

from news_parser.core.taxonomy import Taxonomy

if TYPE_CHECKING:
    from news_parser.schemas.match import AnalyticsItem, NewsItem, ProfileMatchResponse

DIRECTION_RU = {
    "positive": "позитивное",
    "negative": "негативное",
    "mixed": "неоднозначное",
    "neutral": "нейтральное",
}
NEWS_SHARE = 0.65  # доля бюджета символов под новости, если есть аналитика


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines() if line.strip())


def _news_block(n: "NewsItem", taxonomy: Taxonomy) -> str:
    sources = ", ".join(dict.fromkeys(src.source_name for src in n.sources)) or "—"
    why = "; ".join(
        m.aspect_title + (f" ({', '.join(v for vals in m.matched_labels.values() for v in vals)})" if m.matched_labels else "")
        for m in n.matched_aspects
    )
    lines = [
        f"[{n.ref}] {n.title}",
        f"Дата: {n.last_seen_at:%d.%m.%Y} · Источники: {sources} · "
        f"Тип: {taxonomy.event_types.get(n.event_type, n.event_type)} · "
        f"Влияние на бизнес: {DIRECTION_RU.get(n.direction, n.direction)}",
        f"Почему отобрано: {why}"
        + ("" if n.passed_rules else " (запасной поиск: теги не совпали, отобрано только по смыслу)"),
        f"Суть: {n.summary}",
    ]
    if n.facts:
        lines.append("Факты:")
        for f in n.facts:
            mark = "подтверждено" if f.get("confirmed", True) else "прогноз/мнение"
            lines.append(f"- [{mark}] {f.get('text', '')}")
    if n.chunks:
        lines.append("Фрагменты статей:")
        lines += [_quote(f"({c.source_name}) {c.text}") for c in n.chunks]
    if n.related_analytics:
        lines.append("Аналитика банка по теме: " + ", ".join(n.related_analytics))
    return "\n".join(lines)


def _analytics_block(a: "AnalyticsItem") -> str:
    pages = ""
    if a.page_from:
        pages = f", стр. {a.page_from}" + (f"–{a.page_to}" if a.page_to and a.page_to != a.page_from else "")
    summary = f"\nГлавное в документе:\n{a.doc_summary}" if a.doc_summary else ""
    return f"[{a.ref}] «{a.doc_title}»{pages}{summary}\nФрагмент:\n{_quote(a.text)}"


def _fit(blocks: list[str], budget: int) -> tuple[list[str], int]:
    out, used = [], 0
    for b in blocks:
        if used + len(b) + 2 > budget:
            break
        out.append(b)
        used += len(b) + 2
    return out, len(blocks) - len(out)


def render_context(r: "ProfileMatchResponse", taxonomy: Taxonomy, max_chars: int) -> str:
    header = "\n".join(
        [
            "# КОНТЕКСТ ДЛЯ АНАЛИЗА",
            "[N…] — новости из внешних источников (факты). [A…] — аналитика Альфа-Банка (позиция банка).",
            "Ссылайся на эти метки в выводах. Не добавляй фактов, которых нет в контексте.",
            "",
            "## Клиент",
            r.profile_summary,
            "Интересы клиента: " + "; ".join(a.title for a in r.aspects),
        ]
    )
    budget = max_chars - len(header)
    news_blocks = [_news_block(n, taxonomy) for n in r.news]
    analytics_blocks = [_analytics_block(a) for a in r.bank_analytics]
    news_budget = int(budget * NEWS_SHARE) if analytics_blocks else budget
    news_fit, news_dropped = _fit(news_blocks, news_budget)
    analytics_fit, analytics_dropped = _fit(analytics_blocks, budget - sum(len(b) + 2 for b in news_fit))

    parts = [header, "", "## Новости"]
    parts += news_fit or ["Значимых для клиента новостей за период не найдено."]
    if analytics_fit:
        parts += ["", "## Аналитика Альфа-Банка (позиция банка)"] + analytics_fit
    if news_dropped or analytics_dropped:
        parts.append(f"\n(не поместилось в лимит контекста: новостей {news_dropped}, фрагментов аналитики {analytics_dropped})")
    return "\n\n".join(p for p in parts if p is not None).replace("\n\n\n", "\n\n")
