"""Чистка текста аналитики перед нарезкой: убираем то, что не несёт смысла, но портит
векторы и подбор — имена и контакты авторов, колонтитулы, номера страниц, дисклеймеры.

Работает построчно и консервативно: строку с содержанием не выбрасываем, а только
вырезаем из неё контакты. Qwen3-VL и так просят всё это пропускать — чистка нужна
для текстового слоя PDF и для OCR.
"""

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"\+?\s?7[\s(]*\d{3}[\s)]*\d{3}[\s-]?\d{2}[\s-]?\d{2}")
_URL = re.compile(r"(https?://)?(www\.)?alfabank\.ru\S*", re.IGNORECASE)
# строки-колонтитулы целиком
_BOILERPLATE_LINE = re.compile(
    r"^(центр макроэкономического анализа|рынок облигаций|долговой рынок|рынок акций|альфа[\s-]?банк|"
    r"аналитический департамент|глава аналитического|департамента|старший аналитик.*|аналитик.*москва|"
    r"стр\.?\s*\d+|\d{1,3}|[aа]|-|•)$",
    re.IGNORECASE,
)
# юридический хвост: такие строки (и всё после них на странице) — дисклеймер
_DISCLAIMER = re.compile(
    r"не является (индивидуальной )?инвестиционной рекомендаци|настоящ(ий|ая|ее) (материал|документ|отч[её]т|информаци)"
    r"|информация,? (содержащаяся|приведенная|представленная) в настоящ|все права защищены|©",
    re.IGNORECASE,
)
_NAME = re.compile(r"^[А-ЯЁ][а-яё]+(\s[А-ЯЁ]\.)?\s[А-ЯЁ][а-яё]+,?$")  # «Наталия Орлова», «Мария Радченко,»


def clean_page(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for i, line in enumerate(lines):
        if _DISCLAIMER.search(line):
            break  # дальше на странице — юридический текст
        had_contact = bool(_EMAIL.search(line) or _PHONE.search(line))
        line = _URL.sub("", _PHONE.sub("", _EMAIL.sub("", line))).strip(" ,;|")
        if not line or _BOILERPLATE_LINE.match(line):
            continue
        # имя автора: короткая строка «Имя Фамилия», рядом с которой стоят контакты
        near_contact = any(_EMAIL.search(x) or _PHONE.search(x) for x in lines[max(0, i - 1) : i + 2])
        if _NAME.match(line) and (near_contact or had_contact):
            continue
        out.append(line)
    return "\n".join(out)
