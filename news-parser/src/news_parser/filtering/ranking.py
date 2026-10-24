"""Этап ранжирования (scoring) — пока не реализован.

Сейчас порядок не меняется: кандидаты уже отсортированы векторным поиском по сходству
(сначала прошедшие правила, потом запасной поиск). Сюда встанет ранжирование по важности
интересов клиента (Aspect.weight), квотам на интерес, свежести, надёжности источников и т.п.
"""

from news_parser.filtering.candidate import Candidate

STATUS = "not_implemented: порядок = сходство из векторного поиска"


def rank(candidates: list[Candidate]) -> list[Candidate]:
    return candidates
