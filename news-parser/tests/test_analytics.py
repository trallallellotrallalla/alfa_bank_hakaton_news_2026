import json
from types import SimpleNamespace

from pypdf import PdfWriter

from news_parser.core.taxonomy import get_taxonomy
from news_parser.llm.client import LlmResponse
from news_parser.llm.doc_profiler import profile_document
from news_parser.parser import analytics_loader as al
from news_parser.parser.analytics_cleaner import clean_page

tax = get_taxonomy()


def test_clean_page_removes_authors_contacts_and_disclaimer():
    page = "\n".join([
        "A",
        "Центр макроэкономического анализа",
        "Наталия Орлова",
        "Norlova@alfabank.ru",
        "Ключевая ставка ЦБ РФ",
        "ЦБ сохранил ставку 14%, риторика стала жестче.  GBarabanov@alfabank.ru",
        "Банк России сохранит паузу до конца года.",
        "3",
        "Настоящий материал не является инвестиционной рекомендацией.",
        "Любой текст после дисклеймера.",
    ])
    out = clean_page(page)
    assert "Ключевая ставка ЦБ РФ" in out
    assert "ЦБ сохранил ставку 14%, риторика стала жестче." in out  # контакт вырезан, содержание осталось
    assert "Банк России сохранит паузу" in out  # «Банк России» — не имя автора
    for junk in ("Орлова", "@", "Центр макроэкономического", "инвестиционной рекомендацией", "после дисклеймера"):
        assert junk not in out
    assert "\n3\n" not in f"\n{out}\n"


class FakeLlm:
    model = "qwen/qwen3.6-35b-a3b"
    configured = True

    def __init__(self, answers):
        self.answers = list(answers)

    def chat(self, messages, *, purpose, article_id=None, max_tokens=None):
        return LlmResponse(content=self.answers.pop(0), call_id=1, total_tokens=10)


def test_profile_document_cleans_ids_and_handles_null_date():
    answer = json.dumps({
        "title": "Ключевая ставка ЦБ РФ",
        "published_date": "null",
        "summary": "Ставка надолго высокая",
        "stance": "hawkish",
        "macro_factors": ["key_rate", "made_up"],
        "industries": ["finance"],
    })
    p = profile_document(FakeLlm([answer]), tax, title_hint="x", text="...", max_chars=1000)
    assert p.published_date is None and p.stance == "hawkish"
    assert p.macro_factors == ["key_rate"] and p.summary == ["Ставка надолго высокая"]


def _scanned_pdf(path):
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    with open(path, "wb") as f:
        w.write(f)
    return path


def _loader(vision_configured: bool):
    settings = SimpleNamespace(analytics_vision=True, analytics_vision_max_side=1400, analytics_vision_workers=2)
    vision = SimpleNamespace(configured=vision_configured, model="qwen/qwen3-vl-30b-a3b-instruct")
    return al.AnalyticsLoader(settings, tax, embedder=None, text_llm=None, vision_llm=vision)


def test_text_source_priority_for_scanned_pdf(tmp_path, monkeypatch):
    pdf = _scanned_pdf(tmp_path / "doc.pdf")
    txt = tmp_path / "doc.txt"
    txt.write_text("Название\n\nтекст OCR", encoding="utf-8")
    files = {".pdf": pdf, ".txt": txt}

    # 1) есть кеш распознавания — берём его, LLM не зовём
    cache = al._Cache(tmp_path / "doc.analysis.json", {"pages": ["из кеша"], "text_method": "vision"})
    assert _loader(True)._pages(pdf, files, cache) == (["из кеша"], "vision")

    # 2) кеша нет, Qwen-VL доступна — распознаём и кладём в кеш
    monkeypatch.setattr(al, "_page_images", lambda p: ["img"])
    monkeypatch.setattr(al, "transcribe_pages", lambda client, images, **kw: ["распознано VL"])
    cache = al._Cache(tmp_path / "doc.analysis.json", {})
    assert _loader(True)._pages(pdf, files, cache) == (["распознано VL"], "vision")
    assert cache.changed and cache.data["pages"] == ["распознано VL"]

    # 3) LLM недоступна — запасной .txt
    cache = al._Cache(tmp_path / "doc.analysis.json", {})
    assert _loader(False)._pages(pdf, files, cache) == (["Название\n\nтекст OCR"], "ocr_txt")


def test_cache_is_bound_to_source_hash(tmp_path):
    path = tmp_path / "doc.analysis.json"
    c = al._Cache.load(path, "sha-1")
    c.data["pages"] = ["стр"]
    c.changed = True
    c.save()
    assert al._Cache.load(path, "sha-1").data["pages"] == ["стр"]
    assert "pages" not in al._Cache.load(path, "sha-2").data  # файл поменялся — кеш устарел
