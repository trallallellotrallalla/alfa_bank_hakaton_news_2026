"""news-parser: сбор, классификация и отбор новостей и аналитики Альфа-Банка под клиента.

Публичные функции — в news_parser.interface; доступны и короче:

    from news_parser import get_packets, ingest, stats
"""


import importlib


def _interface():
    # importlib, а не «from news_parser import interface»: тот снова вызвал бы __getattr__ пакета
    return importlib.import_module("news_parser.interface")


def __getattr__(name: str):
    # ленивый импорт: `import news_parser` не тянет модель, БД и настройки,
    # пока не нужна конкретная функция
    interface = _interface()
    if name in interface.__all__:
        return getattr(interface, name)
    raise AttributeError(f"module 'news_parser' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_interface().__all__)
