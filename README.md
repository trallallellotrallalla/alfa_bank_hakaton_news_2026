# Новостная аналитика для Альфа-Бизнес — фронтенд-прототип

Прототип для кейса Альфа Хак «Новостная аналитика для принятия бизнес-решений».
Сервис встроен в интернет-банк Альфа-Бизнес: AI-агент отбирает новости под конкретную компанию и роль руководителя
и интерпретирует их с опорой на аналитику Альфа-Банка. В каждом инсайте отделены **факты**, **позиция банка** и **выводы AI**,
есть ссылки на первоисточники и трасса шагов агента.

Макеты: Figma, страница «Cover & Screens», фреймы 01–05.

## Быстрый старт

Нужен Node.js 20+ (проверено на Node 24).

```bash
npm ci
npm run dev
```

Приложение откроется на http://localhost:5173. По умолчанию работает на встроенных мок-данных.

## Docker

```bash
docker build -t alfa-news-insight .
docker run --rm -p 8080:80 alfa-news-insight
```

Приложение — на http://localhost:8080. То же через compose: `docker compose up --build`.

Сборка с реальным бэкендом:

```bash
docker build --build-arg VITE_API_MODE=http -t alfa-news-insight .
docker run --rm -p 8080:80 -e API_UPSTREAM=http://host.docker.internal:8000 alfa-news-insight
```

nginx отдаёт статику и проксирует `/api/*` на `API_UPSTREAM` (префикс `/api` срезается).

## Что посмотреть (сценарий для жюри)

1. **Главная** (`/`) — тёмный блок «Что сегодня важно для …» с тремя главными событиями и кнопкой «Открыть ленту».
2. **Смена компании и роли** — в топбаре клик по названию компании или по чипу «Роль: …». Меняются счета, точка входа, лента,
   «Почему вам», ранжирование и порядок действий.
3. **Лента** (`/news`) — фильтры «Риски / Возможности / Позиция банка / Контрагенты / Ставки и валюта», профиль компании,
   «Уточнить профиль» (Checkbox и Switch из core-ds сужают ленту).
4. **Карточка события** (`/news/:id`) — 6 блоков интерпретации с метками «Факт / Позиция банка / Вывод AI / Трасса»,
   первоисточники, предложение банка. Если у банка нет аналитики по теме, блок «Как это оценивает банк?» честно пуст.
5. **Чат** (`/chat`) — ответы с таблицей сценариев, цитатами [1][2], альтернативными разрезами и шагами агента во время ответа.
   На размытый вопрос (например, «а риски?») агент задаёт **уточняющий вопрос** с вариантами.
6. **Трасса агента** (`/news/:id/trace`) — шаги с инструментами, повторный поиск при самопроверке, вес признаков компании,
   ответ в формате insight.v1, экспорт JSON.

## Контракт insight.v1

| Файл | Что внутри |
| --- | --- |
| [`src/types/insight.ts`](src/types/insight.ts) | TypeScript-типы контракта |
| [`docs/insight.v1.schema.json`](docs/insight.v1.schema.json) | JSON Schema (draft 2020-12) |
| [`docs/insight.v1.example.json`](docs/insight.v1.example.json) | Пример ответа, валиден по схеме |
| [`docs/openapi.yaml`](docs/openapi.yaml) | Эндпоинты `/companies`, `/feed`, `/events/{id}`, `/chat`, `/trace/{run_id}` |

Ключевые поля: `event_id`, `relevance` (0..1), `impact` (`risk` / `opportunity` / `attention` / `scenario`), `facts[]` и `bank_view[]`
со ссылками `src` на `sources[]`, `ai_inference[]` с кодами признаков компании `features`, `actions[]` с ролями, `confidence`,
`trace[]` (шаги агента: `title`, `tool`, `detail`, `time`, `state` = `done` / `retry` / `running`).

## Формат «ВЫХОД» от бэкенда

Пайплайн бэкенда может отдавать интерпретации в своём формате «ВЫХОД» (пример — [`docs/vyhod.example.json`](docs/vyhod.example.json),
типы — [`src/types/interpretation.ts`](src/types/interpretation.ts)). Фронтенд сам распознаёт формат ответа и переводит его в insight.v1
адаптером [`src/api/adapters/interpretation.ts`](src/api/adapters/interpretation.ts):

| ВЫХОД | insight.v1 / экран |
| --- | --- |
| `event.news_id`, `event.title`, `event.published_at` | `event_id`, `title`, `published_at` |
| `interpretation_id` | `run_id` — ключ трассы |
| `what_happened` | `facts[]` — блок «Что произошло?», метка «Факт» |
| `why_it_matters`, `attribution.model_inference` | `ai_inference[why_relevant]` — «Почему это важно», «Вывод AI» |
| `risks[]`, `opportunities[]` | `ai_inference[consequence_*]` — «Какие последствия возможны?» |
| `attribution.bank_view` (`chunk_id`, `doc_title`, `page`) | `bank_view[]` + источник «ЦМИ Альфа-Банка» — «Как это оценивает банк?» |
| `recommended_actions[]` | `actions[]` — «Какие действия могут быть релевантны?» |
| `sources[news / analytics]` | `sources[]` — «Первоисточники» |
| `sources[client_signal]` | `features[]` — «Признаки, повлиявшие на вывод» |
| `confidence` 0..1 | `confidence` high / medium / low + `relevance`, если бэкенд её не передал |

Чего во ВЫХОДЕ нет, адаптер восстанавливает: `impact` — по рискам и возможностям, темы для фильтров — по заголовку,
трассу — по `attribution` (с пометкой «восстановлено»). Если бэкенд передаст необязательные поля `relevance`, `impact`, `topics`,
`trace`, `url` и `title` у источников, `signals` у выводов и `roles` у действий — адаптер возьмёт их вместо восстановленных.

Эндпоинты `/feed`, `/events/{id}` и `/trace/{run_id}` могут возвращать как insight.v1, так и ВЫХОД (для `/feed` — массив или `{ items: [...] }`).
В режиме `mock` пример ВЫХОДА показывается как компания **U_176 «ТрансМагистраль»** — её лента собрана из `docs/vyhod.example.json`
через тот же адаптер. Чат (`POST /chat`) по-прежнему ждёт ответ в формате `ChatAnswer` из `docs/openapi.yaml`.

## API: моки или бэкенд

Один флаг — `VITE_API_MODE` (см. [`.env.example`](.env.example)):

| Значение | Поведение |
| --- | --- |
| `mock` (по умолчанию) | Данные из `src/mocks`, задержки имитируют работу агента |
| `http` | `fetch` на `VITE_API_BASE_URL` (по умолчанию `/api`) по `docs/openapi.yaml` |

Локально с бэкендом на порту 8000:

```bash
VITE_API_MODE=http VITE_API_PROXY=http://localhost:8000 npm run dev
```

Код: [`src/api/index.ts`](src/api/index.ts) выбирает реализацию; [`src/api/mock.ts`](src/api/mock.ts) и [`src/api/http.ts`](src/api/http.ts)
реализуют один интерфейс [`Api`](src/api/types.ts).

## Мок-данные

Все клиенты синтетические (`SYNTHETIC_U`), совпадения случайны:

| ID | Компания | ОКВЭД | Группа | Продукты в банке |
| --- | --- | --- | --- | --- |
| U-10482 | ООО «СеверТопливо» | 46.71, опт топлива | G-311 | РКО, кредитная линия, гарантии, депозит |
| U-20917 | АО «АгроЮг» | 01.11, зерновые | G-127 | РКО, валютный контроль, сезонный кредит, факторинг |
| U-33650 | ООО «МедТехСнаб» | 46.46, опт медтоваров | G-502 | РКО, овердрафт, аккредитивы, валютный контроль |

6 событий (ставка ЦБ, цены на ДТ, банкротство контрагента, курс рубля, зерновая пошлина, маркировка медизделий) интерпретированы
по-разному для каждой компании — всего 11 инсайтов. Ссылки ведут на разделы реальных первоисточников, сами публикации синтетические.

## Стек

- React 19, TypeScript, Vite 8, React Router 7
- Компоненты core-ds Альфа-Банка: `@alfalab/core-components-button`, `-input`, `-status`, `-switch`, `-checkbox`
  (пакеты, из которых собран `@alfalab/core-components`; ставятся по отдельности, чтобы не тянуть всю библиотеку)
- Токены `@alfalab/core-components-vars`: палитра bluetint, радиусы, отступы
- Шрифт — системный (`--font-family-system`), как в core-ds. В макетах Figma — Inter, потому что фирменный шрифт недоступен.

## Структура

```
src/
  api/          флаг mock/http, интерфейс Api, реализации
  components/   Sidebar, Topbar (переключатели компании и роли), метки, модалка профиля
  context/      выбранная компания, роль, уточнения профиля
  mocks/        компании, события → insight.v1, логика мок-чата
  pages/        5 экранов
  types/        контракт insight.v1
docs/           JSON Schema, пример, OpenAPI
docker/         конфиг nginx
```

## Скрипты

| Команда | Что делает |
| --- | --- |
| `npm run dev` | Dev-сервер |
| `npm run build` | Проверка типов и production-сборка в `dist/` |
| `npm run preview` | Локальный просмотр сборки |
| `npm run typecheck` | Только проверка типов |
