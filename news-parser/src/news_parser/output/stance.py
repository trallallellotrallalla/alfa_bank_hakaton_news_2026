"""Позиция банка во фрагменте аналитики: hawkish | dovish | neutral | risk.

Rule-based, без LLM: аналитики немного, а бюджет токенов нужнее для новостей.
- hawkish — за жёсткую политику / долгий период высоких ставок;
- dovish  — за смягчение, снижение ставок;
- risk    — фрагмент в основном про риски и угрозы;
- neutral — ничего из этого явно не выражено.
Отрицания учитываются: «не ждём снижения ставки» — это hawkish, а не dovish.
"""

import re

_HAWKISH = [
    r"жёстк\w*", r"жестк\w*", r"ужесточ\w*", r"повышени\w* ставк\w*", r"повыс\w* ставк\w*",
    r"высок\w* ставк\w*", r"дорог\w* (деньг|кредит)\w*", r"пауз\w*", r"сохранени\w* ставк\w*",
    r"инфляционн\w* давлени\w*", r"проинфляционн\w*",
]
_DOVISH = [
    r"снижени\w* ставк\w*", r"сниз\w* ставк\w*", r"смягчени\w*", r"смягч\w*", r"мягк\w*",
    r"понижени\w*", r"удешевлени\w*", r"дезинфляц\w*", r"замедлени\w* инфляци\w*",
]
_RISK = [
    r"риск\w*", r"угроз\w*", r"неопределённост\w*", r"неопределенност\w*", r"рецесси\w*",
    r"санкци\w*", r"дефолт\w*", r"кризис\w*", r"спад\w*", r"шок\w*",
]
# «не ждём / маловероятно ... снижения» и «снижение / удешевление ... приостановлено» —
# по смыслу жёсткая позиция, а не мягкая
_NEGATED_DOVISH = re.compile(
    r"(не\s+(жд|ожида|видим|прогнозир|рассчитыва)\w*|маловероятн\w*|вряд ли)[^.!?]{0,60}?"
    r"(снижени\w*|смягчени\w*|сниз\w*|удешевлени\w*)"
    r"|(снижени\w*|смягчени\w*|удешевлени\w*)[^.!?]{0,60}?"
    r"(приостановлен\w*|прерван\w*|прекращ\w*|откладыва\w*|отложен\w*)",
    re.IGNORECASE,
)


def _compile(words: list[str]) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(words) + r")", re.IGNORECASE)


_H, _D, _R = _compile(_HAWKISH), _compile(_DOVISH), _compile(_RISK)


def classify_stance(text: str) -> str:
    negated = len(_NEGATED_DOVISH.findall(text))
    hawkish = len(_H.findall(text)) + 2 * negated
    dovish = max(len(_D.findall(text)) - negated, 0)
    risk = len(_R.findall(text))

    policy = max(hawkish, dovish)
    if risk >= 2 and risk > policy:
        return "risk"
    if policy == 0 or hawkish == dovish:
        return "risk" if risk >= 2 else "neutral"
    return "hawkish" if hawkish > dovish else "dovish"
