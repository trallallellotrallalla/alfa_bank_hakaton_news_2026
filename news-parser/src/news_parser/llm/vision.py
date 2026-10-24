"""Распознавание страниц аналитики через мультимодальную модель (Qwen3-VL).

Нужно для PDF, сохранённых картинками (без текстового слоя): модель переписывает текст
страницы и описывает графики и таблицы — их обычный OCR теряет, а там самое ценное
(динамика инфляции, кривые доходностей, таблицы прогнозов банка).
"""

import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from news_parser.llm.client import LlmClient

log = logging.getLogger(__name__)

PAGE_PROMPT = """Это страница аналитического отчёта Альфа-Банка (страница {page} из {pages}).

Перепиши текст страницы полностью и точно, в порядке чтения (если колонки — по очереди).
НЕ включай: колонтитулы, логотипы, имена, должности и контакты авторов (e-mail, телефоны),
номера страниц, юридические дисклеймеры.

Каждый график или диаграмму опиши отдельным блоком:
[График: название] что показано, период, ключевые значения и тренд, вывод, если он подписан.
Значения, которые читаются с графика на глаз (без подписей), помечай словом «около».

Таблицы перепиши в Markdown, сохранив все строки и столбцы.

Ничего не выдумывай и не добавляй от себя — только то, что есть на странице.
Ответ — только содержимое страницы, без вступлений."""


def _to_jpeg_b64(image: Image.Image, max_side: int) -> str:
    img = image.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def transcribe_page(client: LlmClient, image: Image.Image, *, page: int, pages: int, max_side: int) -> str:
    """Бросает LlmUnavailable / BudgetExceeded — вызывающий код решает, что делать."""
    b64 = _to_jpeg_b64(image, max_side)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PAGE_PROMPT.format(page=page, pages=pages)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
    ]
    return client.chat(messages, purpose="analytics_vision", max_tokens=3000).content.strip()


def transcribe_pages(client: LlmClient, images: list[Image.Image | None], *, max_side: int, workers: int) -> list[str]:
    """Все страницы документа параллельно (модель отвечает ~30 с на страницу).
    Страница без картинки -> пустая строка. Первая ошибка прерывает документ целиком."""
    total = len(images)

    def one(i: int) -> str:
        img = images[i]
        if img is None:
            return ""
        text = transcribe_page(client, img, page=i + 1, pages=total, max_side=max_side)
        log.info("страница %d/%d распознана (%d символов)", i + 1, total, len(text))
        return text

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, range(total)))
