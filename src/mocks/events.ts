import type {
    Action,
    AiInference,
    BankOffer,
    BankView,
    Confidence,
    Fact,
    Feature,
    Impact,
    Insight,
    Source,
    Topic,
    TraceStep,
} from '../types/insight';
import { SCHEMA_VERSION } from '../types/insight';
import { COMPANIES } from './companies';
import { plural } from '../utils/format';
import { interpretationToInsight } from '../api/adapters/interpretation';
import type { Interpretation } from '../types/interpretation';

/**
 * Мок-данные в формате insight.v1.
 * Событие (новостной кластер) общее для всех клиентов: факты, позиция банка, источники.
 * Интерпретация (релевантность, влияние, выводы AI, действия, трасса) — своя для каждой компании.
 *
 * Ссылки ведут на разделы первоисточников; конкретные публикации синтетические.
 */

interface EventBase {
    event_id: string;
    title: string;
    summary: string;
    published_at: string;
    topics: Topic[];
    facts: Fact[];
    bank_view: BankView[];
    sources: Source[];
    query: string;
}

interface CompanyInterpretation {
    company_id: string;
    title?: string;
    relevance: number;
    impact: Impact;
    why_you: string;
    ai_inference: AiInference[];
    actions: Action[];
    features: Feature[];
    confidence: Confidence;
    bank_offer?: BankOffer;
    suggested_questions: string[];
    /** Отличия в трассе: признаки профиля, расчёт, самопроверка */
    trace: { profile: string; calc_tool: string; calc: string; retry?: string };
}

/* ---------------- Источники ---------------- */

const SRC: Record<string, Source> = {
    cbr: {
        id: 'cbr',
        kind: 'regulator',
        publisher: 'Банк России',
        title: 'Пресс-релиз о ключевой ставке',
        url: 'https://www.cbr.ru/press/keypr/',
        published_at: '2026-09-11T13:30:00+03:00',
    },
    'cmi-rate': {
        id: 'cmi-rate',
        kind: 'bank_research',
        publisher: 'ЦМИ Альфа-Банка',
        title: 'Ставка без изменения на 14,0%, риторика стала жестче',
        url: 'https://alfabank.ru/corporate/',
        published_at: '2026-09-11T15:10:00+03:00',
    },
    'cmi-macro': {
        id: 'cmi-macro',
        kind: 'bank_research',
        publisher: 'ЦМИ Альфа-Банка',
        title: 'Макростатистика 7М26',
        url: 'https://alfabank.ru/corporate/',
        published_at: '2026-09-02T10:00:00+03:00',
    },
    'ifx-rate': {
        id: 'ifx-rate',
        kind: 'news',
        publisher: 'Интерфакс',
        title: 'ЦБ взял паузу в снижении ставки',
        url: 'https://www.interfax.ru/business/',
        published_at: '2026-09-11T13:34:00+03:00',
    },
    spimex: {
        id: 'spimex',
        kind: 'exchange',
        publisher: 'СПбМТСБ',
        title: 'Итоги торгов нефтепродуктами за неделю',
        url: 'https://spimex.com/markets/oil_products/',
        published_at: '2026-09-11T19:00:00+03:00',
    },
    'rbc-diesel': {
        id: 'rbc-diesel',
        kind: 'news',
        publisher: 'РБК',
        title: 'Цены на летнее дизтопливо обновили максимум года',
        url: 'https://www.rbc.ru/business/',
        published_at: '2026-09-11T16:20:00+03:00',
    },
    'cmi-commod': {
        id: 'cmi-commod',
        kind: 'bank_research',
        publisher: 'Альфа-Банк',
        title: 'Commodities performance: нефтепродукты, сентябрь',
        url: 'https://alfabank.ru/corporate/',
        published_at: '2026-09-09T09:00:00+03:00',
    },
    kad: {
        id: 'kad',
        kind: 'registry',
        publisher: 'Картотека арбитражных дел',
        title: 'Заявление ФНС о признании АО «ТрансЛогистик» банкротом',
        url: 'https://kad.arbitr.ru/',
        published_at: '2026-09-10T11:00:00+03:00',
    },
    kommersant: {
        id: 'kommersant',
        kind: 'news',
        publisher: 'Коммерсант',
        title: 'Налоговая требует банкротства перевозчика',
        url: 'https://www.kommersant.ru/',
        published_at: '2026-09-10T18:40:00+03:00',
    },
    'cbr-fx': {
        id: 'cbr-fx',
        kind: 'regulator',
        publisher: 'Банк России',
        title: 'Официальные курсы иностранных валют',
        url: 'https://www.cbr.ru/currency_base/daily/',
        published_at: '2026-09-10T17:00:00+03:00',
    },
    'cmi-tactic': {
        id: 'cmi-tactic',
        kind: 'bank_research',
        publisher: 'ЦМИ Альфа-Банка',
        title: 'Тактический взгляд на 3-й квартал 2026',
        url: 'https://alfabank.ru/corporate/',
        published_at: '2026-07-03T10:00:00+03:00',
    },
    vedomosti: {
        id: 'vedomosti',
        kind: 'news',
        publisher: 'Ведомости',
        title: 'Рубль держится у 92 за доллар',
        url: 'https://www.vedomosti.ru/finance',
        published_at: '2026-09-10T12:15:00+03:00',
    },
    'gov-duty': {
        id: 'gov-duty',
        kind: 'regulator',
        publisher: 'Правительство РФ',
        title: 'Постановление о параметрах зерновой пошлины',
        url: 'http://government.ru/docs/',
        published_at: '2026-09-09T20:00:00+03:00',
    },
    'ifx-grain': {
        id: 'ifx-grain',
        kind: 'news',
        publisher: 'Интерфакс',
        title: 'Базовая цена для расчёта пошлины на пшеницу повышена',
        url: 'https://www.interfax.ru/business/',
        published_at: '2026-09-09T20:40:00+03:00',
    },
    'cmi-agro': {
        id: 'cmi-agro',
        kind: 'bank_research',
        publisher: 'ЦМИ Альфа-Банка',
        title: 'Агросектор: урожай-2026 и экспортная маржа',
        url: 'https://alfabank.ru/corporate/',
        published_at: '2026-08-28T10:00:00+03:00',
    },
    'mz-mark': {
        id: 'mz-mark',
        kind: 'regulator',
        publisher: 'Правительство РФ',
        title: 'Расширение обязательной маркировки медицинских изделий',
        url: 'http://government.ru/docs/',
        published_at: '2026-09-08T19:00:00+03:00',
    },
    'crpt': {
        id: 'crpt',
        kind: 'registry',
        publisher: 'Честный ЗНАК',
        title: 'Сроки и этапы маркировки медизделий',
        url: 'https://честныйзнак.рф/',
        published_at: '2026-09-09T10:00:00+03:00',
    },
    'vedomosti-med': {
        id: 'vedomosti-med',
        kind: 'news',
        publisher: 'Ведомости',
        title: 'Дистрибьюторов медизделий обяжут маркировать остатки',
        url: 'https://www.vedomosti.ru/business',
        published_at: '2026-09-09T13:00:00+03:00',
    },
};

/* ---------------- События ---------------- */

const EVENTS: EventBase[] = [
    {
        event_id: 'cbr-2026-09-11',
        title: 'ЦБ сохранил ключевую ставку 14%: кредиты не подешевеют до конца года',
        summary: 'Совет директоров Банка России взял паузу после десяти снижений подряд и ужесточил риторику.',
        published_at: '2026-09-11T13:30:00+03:00',
        topics: ['rates'],
        facts: [
            {
                text: '11 сентября 2026 года Совет директоров Банка России сохранил ключевую ставку на уровне 14% годовых — первая пауза после десяти снижений подряд с июня 2025 года. Риторика регулятора стала жёстче.',
                src: ['cbr', 'ifx-rate'],
            },
        ],
        bank_view: [
            {
                text: 'Центр макроэкономических исследований Альфа-Банка: ставка без изменения, риторика жёстче. Данные по рынку труда не подтверждают охлаждения экономики — возобновления снижения стоит ждать не раньше декабря.',
                src: ['cmi-rate', 'cmi-macro'],
            },
        ],
        sources: [SRC.cbr, SRC['cmi-rate'], SRC['cmi-macro'], SRC['ifx-rate']],
        query: "news_search('ключевая ставка', 48h)",
    },
    {
        event_id: 'spimex-diesel-2026-37',
        title: 'Биржевые цены на дизельное топливо выросли на 6% за неделю',
        summary: 'На СПбМТСБ котировки летнего ДТ обновили максимум года на фоне ремонтов НПЗ и роста экспортного спроса.',
        published_at: '2026-09-11T19:00:00+03:00',
        topics: ['commodities'],
        facts: [
            {
                text: 'Индекс летнего дизельного топлива на СПбМТСБ за неделю вырос на 6% и обновил максимум года. Участники рынка связывают рост с внеплановыми ремонтами НПЗ и экспортным спросом.',
                src: ['spimex', 'rbc-diesel'],
            },
        ],
        bank_view: [
            {
                text: 'Аналитики Альфа-Банка ожидают, что повышенные цены на ДТ сохранятся до завершения ремонтной кампании НПЗ в октябре; после этого вероятна коррекция на 3–5%.',
                src: ['cmi-commod'],
            },
        ],
        sources: [SRC.spimex, SRC['rbc-diesel'], SRC['cmi-commod']],
        query: "news_search('дизельное топливо биржа', 7d)",
    },
    {
        event_id: 'kad-translogistik-2026-09',
        title: 'ФНС подала иск о банкротстве АО «ТрансЛогистик»',
        summary: 'Налоговая служба требует взыскать 1,2 млрд ₽ недоимки. Заседание назначено на 18 ноября.',
        published_at: '2026-09-10T11:00:00+03:00',
        topics: ['counterparty'],
        facts: [
            {
                text: 'ФНС подала в арбитражный суд заявление о признании АО «ТрансЛогистик» банкротом. Сумма требований — 1,2 млрд ₽ недоимки и пеней. Заседание по проверке обоснованности назначено на 18 ноября.',
                src: ['kad', 'kommersant'],
            },
        ],
        bank_view: [],
        sources: [SRC.kad, SRC.kommersant],
        query: "registry_check(counterparties=top5)",
    },
    {
        event_id: 'fx-rub-2026-09-10',
        title: 'Рубль укрепился до 92 ₽ за доллар — Альфа-Банк ждёт ослабления к концу года',
        summary: 'Укрепление поддерживают высокие ставки и продажи экспортной выручки; аналитики банка видят риски разворота в IV квартале.',
        published_at: '2026-09-10T17:00:00+03:00',
        topics: ['fx'],
        facts: [
            {
                text: 'Официальный курс доллара, установленный Банком России на 11 сентября, — 92,41 ₽. С начала квартала рубль укрепился на 4%.',
                src: ['cbr-fx', 'vedomosti'],
            },
        ],
        bank_view: [
            {
                text: 'ЦМИ Альфа-Банка: укрепление поддерживают высокая ставка и продажи экспортной выручки. В IV квартале банк ждёт ослабления рубля к 96–98 ₽ за доллар по мере снижения ставки и сезонного роста импорта.',
                src: ['cmi-tactic'],
            },
        ],
        sources: [SRC['cbr-fx'], SRC['cmi-tactic'], SRC.vedomosti],
        query: "news_search('курс рубля', 72h)",
    },
    {
        event_id: 'gov-grain-duty-2026-09',
        title: 'Правительство повысило базовую цену зерновой пошлины',
        summary: 'Пошлина на экспорт пшеницы снизится примерно на 15% с 1 октября; параметры действуют до конца сезона.',
        published_at: '2026-09-09T20:00:00+03:00',
        topics: ['regulation', 'trade', 'commodities'],
        facts: [
            {
                text: 'Правительство повысило базовую цену для расчёта экспортной пошлины на пшеницу. По оценкам участников рынка, ставка пошлины с 1 октября снизится примерно на 15%.',
                src: ['gov-duty', 'ifx-grain'],
            },
        ],
        bank_view: [
            {
                text: 'ЦМИ Альфа-Банка: снижение пошлины частично компенсирует экспортёрам крепкий рубль; маржа экспорта пшеницы в IV квартале оценивается на 2–3 п.п. выше, чем в III квартале.',
                src: ['cmi-agro'],
            },
        ],
        sources: [SRC['gov-duty'], SRC['ifx-grain'], SRC['cmi-agro']],
        query: "news_search('зерновая пошлина', 72h)",
    },
    {
        event_id: 'gov-med-marking-2026-09',
        title: 'Маркировку медицинских изделий распространят на остатки у дистрибьюторов',
        summary: 'С 1 марта 2027 года остатки немаркированных медизделий нельзя будет продавать; товар нужно промаркировать до конца февраля.',
        published_at: '2026-09-08T19:00:00+03:00',
        topics: ['regulation'],
        facts: [
            {
                text: 'Правительство утвердило расширение обязательной маркировки медицинских изделий: с 1 марта 2027 года продажа немаркированных остатков у дистрибьюторов запрещена. Остатки нужно промаркировать до 28 февраля 2027 года.',
                src: ['mz-mark', 'crpt', 'vedomosti-med'],
            },
        ],
        bank_view: [],
        sources: [SRC['mz-mark'], SRC.crpt, SRC['vedomosti-med']],
        query: "news_search('маркировка медизделий', 7d)",
    },
];

/* ---------------- Интерпретации по компаниям ---------------- */

const F = {
    loa: { code: 'CL_PRODUCT_LOA_MARK', label: 'Кредитная линия с плавающей ставкой', weight: 0.92 },
    invest: { code: 'CL_INVEST_PROGRAM', label: 'Инвестпрограмма на заёмные средства', weight: 0.71 },
    deposit: { code: 'CL_PRODUCT_DEP_MARK', label: 'Депозит 120 млн ₽', weight: 0.48 },
    okvedFuel: { code: 'OKVED_MAIN', label: 'Сезон закупок ДТ (ОКВЭД 46.71)', weight: 0.36 },
} satisfies Record<string, Feature>;

const INTERPRETATIONS: Record<string, CompanyInterpretation[]> = {
    'cbr-2026-09-11': [
        {
            company_id: 'U-10482',
            title: 'ЦБ сохранил ключевую ставку 14%: кредиты для «СеверТопливо» не подешевеют до конца года',
            relevance: 0.94,
            impact: 'risk',
            why_you: 'кредитный портфель в Альфа-Банке · инвестпрограмма на заёмные средства',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'У «СеверТопливо» кредитная линия 250 млн ₽ по ставке КС + 3,1% и инвестпрограмма на заёмные средства. Ставка по линии остаётся 17,1% вместо ожидавшихся после снижения ~16%.',
                    features: ['CL_PRODUCT_LOA_MARK', 'CL_INVEST_PROGRAM'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Каждый 1 п.п. ставки выше плана — около +0,6 млн ₽ процентов за квартал при полной выборке лимита; дорожает пополнение оборотки в сезон закупок ДТ.',
                    features: ['CL_PRODUCT_LOA_MARK', 'OKVED_MAIN'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Депозит 120 млн ₽ продолжит приносить ~16%, досрочное гашение невыгодно.',
                    features: ['CL_PRODUCT_DEP_MARK'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Пересчитать бюджет процентных расходов на IV квартал при КС 14%.', roles: ['cfo', 'treasurer'] },
                { id: 'a2', text: 'Обсудить фиксацию ставки на часть лимита.', roles: ['cfo', 'ceo'], product: 'IRS' },
                { id: 'a3', text: 'Финансировать закупку ДТ с депозита, если спред выше 1 п.п.', roles: ['treasurer', 'procurement'] },
            ],
            features: [F.loa, F.invest, F.deposit, F.okvedFuel],
            confidence: 'high',
            bank_offer: {
                title: 'Предложение Альфа-Банка',
                text: 'Процентный своп или фиксированная ставка на часть кредитной линии — защитит бюджет, если снижение ставки отложится.',
                product: 'IRS',
            },
            suggested_questions: [
                'Сколько мы переплатим за IV квартал?',
                'Как это влияет на группу компаний G-311?',
                'Покажи прогноз ставки по мнению банка',
                'Что пишут первоисточники?',
            ],
            trace: {
                profile: 'ОКВЭД 46.71 · выручка 38 млрд ₽ · CL_PRODUCT_LOA_MARK = 1 · GROUP_ID G-311 · топ-5 контрагентов по платежам.',
                calc_tool: 'calc_interest_impact(limit=250 млн, Δ=1 п.п.)',
                calc: '≈ 0,63 млн ₽ процентов за квартал на каждый 1 п.п. при полной выборке.',
                retry: 'Противоречие: Интерфакс датирует решение 12.09. Повторный поиск по первоисточнику — дата 11.09 подтверждена Банком России.',
            },
        },
        {
            company_id: 'U-20917',
            relevance: 0.71,
            impact: 'risk',
            why_you: 'сезонный кредит 400 млн ₽ по плавающей ставке · уборочная кампания',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'Сезонный кредит «АгроЮг» (400 млн ₽, КС + 2,8%) выбран на 78% на финансирование уборочной. Пауза ЦБ сохраняет ставку 16,8% до конца сезона.',
                    features: ['CL_PRODUCT_LOA_MARK', 'SEASONALITY'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Процентные расходы до погашения в декабре — около 13 млн ₽; при снижении ставки в октябре было бы на 0,8 млн ₽ меньше.',
                    features: ['CL_PRODUCT_LOA_MARK'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Высокая ставка поддерживает крепкий рубль — это давит на экспортную выручку; факторинг по экспортным контрактам может сократить потребность в кредите.',
                    features: ['FX_EXPORT', 'CL_PRODUCT_FACTOR_MARK'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Ускорить погашение сезонного кредита из экспортной выручки.', roles: ['cfo', 'treasurer'] },
                { id: 'a2', text: 'Перевести часть финансирования на экспортный факторинг.', roles: ['cfo', 'ceo'], product: 'Факторинг' },
            ],
            features: [
                { code: 'CL_PRODUCT_LOA_MARK', label: 'Сезонный кредит с плавающей ставкой', weight: 0.84 },
                { code: 'SEASONALITY', label: 'Уборочная кампания (ОКВЭД 01.11)', weight: 0.57 },
                { code: 'FX_EXPORT', label: 'Экспортная выручка в USD', weight: 0.41 },
            ],
            confidence: 'high',
            bank_offer: {
                title: 'Предложение Альфа-Банка',
                text: 'Экспортный факторинг: деньги по контрактам с Турцией и Египтом сразу после отгрузки — меньше выборка по кредиту.',
                product: 'Факторинг',
            },
            suggested_questions: ['Сколько мы переплатим за IV квартал?', 'Покажи прогноз ставки по мнению банка', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ОКВЭД 01.11 · выручка 21 млрд ₽ · CL_PRODUCT_LOA_MARK = 1 · экспорт USD · GROUP_ID G-127.',
                calc_tool: 'calc_interest_impact(limit=400 млн, Δ=1 п.п.)',
                calc: '≈ 1,0 млн ₽ процентов за квартал на каждый 1 п.п. при полной выборке.',
                retry: 'Противоречие: Интерфакс датирует решение 12.09. Повторный поиск по первоисточнику — дата 11.09 подтверждена Банком России.',
            },
        },
        {
            company_id: 'U-33650',
            relevance: 0.62,
            impact: 'attention',
            why_you: 'овердрафт 120 млн ₽ по плавающей ставке',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'Овердрафт «МедТехСнаб» (КС + 3,6%) используется в среднем на 64 млн ₽ для кассовых разрывов по госконтрактам. Ставка остаётся 17,6%.',
                    features: ['CL_PRODUCT_OVD_MARK', 'GOV_CONTRACTS'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Стоимость кассовых разрывов до конца года — около 2,8 млн ₽; задержки оплаты по госконтрактам увеличивают её пропорционально.',
                    features: ['GOV_CONTRACTS'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Сверить график поступлений по госконтрактам с использованием овердрафта.', roles: ['cfo', 'treasurer'] },
                { id: 'a2', text: 'Рассмотреть банковскую гарантию вместо обеспечения контрактов деньгами.', roles: ['ceo', 'cfo'], product: 'Гарантии' },
            ],
            features: [
                { code: 'CL_PRODUCT_OVD_MARK', label: 'Овердрафт с плавающей ставкой', weight: 0.74 },
                { code: 'GOV_CONTRACTS', label: 'Поступления по госконтрактам', weight: 0.52 },
            ],
            confidence: 'medium',
            suggested_questions: ['Сколько мы переплатим за IV квартал?', 'Покажи прогноз ставки по мнению банка'],
            trace: {
                profile: 'ОКВЭД 46.46 · выручка 9,4 млрд ₽ · CL_PRODUCT_OVD_MARK = 1 · госконтракты · GROUP_ID G-502.',
                calc_tool: 'calc_interest_impact(limit=120 млн, Δ=1 п.п.)',
                calc: '≈ 0,16 млн ₽ процентов за квартал на каждый 1 п.п. при средней выборке.',
            },
        },
    ],
    'spimex-diesel-2026-37': [
        {
            company_id: 'U-10482',
            relevance: 0.88,
            impact: 'opportunity',
            why_you: 'основной ОКВЭД 46.71 · оптовая торговля топливом · запасы на складах',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'Основной бизнес «СеверТопливо» — опт ДТ. Запасы на складах закуплены в августе по ценам на 6–8% ниже текущих.',
                    features: ['OKVED_MAIN', 'INVENTORY'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Реализация запасов по текущим ценам даёт дополнительную валовую маржу порядка 40–55 млн ₽ за месяц.',
                    features: ['INVENTORY'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Пополнение запасов на пике цен рискованно: банк ждёт коррекции на 3–5% после завершения ремонтов НПЗ.',
                    features: ['OKVED_MAIN'],
                    src: ['cmi-commod'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Приоритизировать реализацию складских запасов в сентябре.', roles: ['ceo', 'procurement'] },
                { id: 'a2', text: 'Отложить крупные закупки ДТ до конца октября.', roles: ['procurement', 'cfo'] },
                { id: 'a3', text: 'Зафиксировать цену части закупок форвардом на бирже.', roles: ['cfo', 'treasurer'] },
            ],
            features: [
                { code: 'OKVED_MAIN', label: 'ОКВЭД 46.71 — опт топлива', weight: 0.9 },
                { code: 'INVENTORY', label: 'Складские запасы ДТ', weight: 0.66 },
            ],
            confidence: 'medium',
            suggested_questions: ['Сколько мы заработаем на запасах?', 'Когда лучше закупать ДТ?', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ОКВЭД 46.71 · склады в Тюменской обл. · средний запас ДТ ≈ 9 тыс. т.',
                calc_tool: 'calc_margin_impact(volume=9 тыс. т, Δprice=6%)',
                calc: '≈ 47 млн ₽ дополнительной валовой маржи при реализации запасов за месяц.',
            },
        },
        {
            company_id: 'U-20917',
            relevance: 0.66,
            impact: 'risk',
            why_you: 'расходы на ГСМ в уборочную · парк техники',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'Уборочная кампания «АгроЮг» идёт до конца октября; ГСМ — около 9% себестоимости.',
                    features: ['SEASONALITY', 'COST_FUEL'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Рост ДТ на 6% увеличит расходы на уборку примерно на 7 млн ₽.',
                    features: ['COST_FUEL'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Закупить ДТ на остаток уборочной по текущим договорам до новой индексации.', roles: ['procurement', 'ceo'] },
            ],
            features: [
                { code: 'SEASONALITY', label: 'Уборочная кампания', weight: 0.62 },
                { code: 'COST_FUEL', label: 'Доля ГСМ в себестоимости 9%', weight: 0.55 },
            ],
            confidence: 'medium',
            suggested_questions: ['Насколько вырастут расходы на уборку?', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ОКВЭД 01.11 · парк техники 140 ед. · уборочная до 31.10.',
                calc_tool: 'calc_cost_impact(fuel_share=9%, Δprice=6%)',
                calc: '≈ 7 млн ₽ дополнительных расходов на ГСМ до конца уборочной.',
            },
        },
    ],
    'kad-translogistik-2026-09': [
        {
            company_id: 'U-10482',
            relevance: 0.81,
            impact: 'attention',
            why_you: 'контрагент из топ-5 плательщиков · 12% входящих платежей за год',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'АО «ТрансЛогистик» — один из пяти крупнейших плательщиков «СеверТопливо»: 12% входящих платежей за 12 месяцев, текущая дебиторка ≈ 31 млн ₽.',
                    features: ['TOP_COUNTERPARTY', 'RECEIVABLES'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'При введении наблюдения платежи по старым обязательствам могут быть заморожены — риск невозврата дебиторки и выпадения выручки.',
                    features: ['RECEIVABLES'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Перевести поставки «ТрансЛогистик» на предоплату.', roles: ['ceo', 'cfo'] },
                { id: 'a2', text: 'Запросить гарантию или аккредитив по текущим договорам.', roles: ['cfo', 'treasurer'], product: 'Аккредитив' },
                { id: 'a3', text: 'Подготовить требования к включению в реестр кредиторов.', roles: ['ceo'] },
            ],
            features: [
                { code: 'TOP_COUNTERPARTY', label: 'Контрагент в топ-5 по платежам', weight: 0.88 },
                { code: 'RECEIVABLES', label: 'Дебиторская задолженность 31 млн ₽', weight: 0.7 },
            ],
            confidence: 'high',
            bank_offer: {
                title: 'Предложение Альфа-Банка',
                text: 'Аккредитив для расчётов с рисковыми контрагентами: оплата гарантирована банком, поставка — без предоплаты.',
                product: 'Аккредитив',
            },
            suggested_questions: ['Сколько денег под риском?', 'Какие ещё контрагенты в зоне риска?', 'Что пишут первоисточники?'],
            trace: {
                profile: 'Топ-5 контрагентов по входящим платежам · ИНН контрагентов замаскированы.',
                calc_tool: 'calc_exposure(counterparty=ТрансЛогистик)',
                calc: 'Дебиторка 31 млн ₽ · 12% входящих платежей · последняя оплата 02.09.',
            },
        },
    ],
    'fx-rub-2026-09-10': [
        {
            company_id: 'U-10482',
            relevance: 0.74,
            impact: 'scenario',
            why_you: 'импорт присадок по данным ФТС (Беларусь) · валютные расходы',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: '«СеверТопливо» импортирует присадки из Беларуси (около 6% закупок). Крепкий рубль временно удешевляет импорт.',
                    features: ['FX_IMPORT'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Если прогноз банка сбудется (96–98 ₽/$), стоимость импорта в IV квартале вырастет на 4–6%.',
                    features: ['FX_IMPORT'],
                    src: ['cmi-tactic'],
                },
            ],
            actions: [{ id: 'a1', text: 'Предоплатить поставки присадок на IV квартал по текущему курсу.', roles: ['procurement', 'treasurer'] }],
            features: [{ code: 'FX_IMPORT', label: 'Импорт присадок (ФТС)', weight: 0.58 }],
            confidence: 'medium',
            suggested_questions: ['Сколько стоит отложить закупку?', 'Покажи прогноз курса по мнению банка'],
            trace: {
                profile: 'ВЭД: импорт · Беларусь · 6% закупок.',
                calc_tool: 'calc_fx_impact(import_share=6%, Δfx=5%)',
                calc: '≈ +3,4 млн ₽ к стоимости импорта в IV квартале при курсе 97 ₽/$.',
            },
        },
        {
            company_id: 'U-20917',
            relevance: 0.9,
            impact: 'risk',
            why_you: 'экспортная выручка в USD · контракты с Турцией и Египтом',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: '«АгроЮг» получает около 60% выручки в долларах по экспортным контрактам. Крепкий рубль снижает рублёвую выручку.',
                    features: ['FX_EXPORT'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Каждый рубль укрепления — около −11 млн ₽ выручки за квартал при текущем объёме отгрузок.',
                    features: ['FX_EXPORT'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Если банк прав и рубль ослабнет к концу года, выгоднее не продавать всю выручку сразу, а растянуть продажу.',
                    features: ['FX_EXPORT'],
                    src: ['cmi-tactic'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Распределить продажу валютной выручки на IV квартал.', roles: ['treasurer', 'cfo'] },
                { id: 'a2', text: 'Захеджировать часть выручки форвардом.', roles: ['cfo', 'ceo'], product: 'Форвард' },
            ],
            features: [
                { code: 'FX_EXPORT', label: 'Экспортная выручка в USD (60%)', weight: 0.93 },
                { code: 'CL_PRODUCT_FXC_MARK', label: 'Валютный контроль в банке', weight: 0.44 },
            ],
            confidence: 'high',
            bank_offer: {
                title: 'Предложение Альфа-Банка',
                text: 'Валютный форвард на часть экспортной выручки — фиксирует курс продажи на IV квартал.',
                product: 'Форвард',
            },
            suggested_questions: ['Сколько мы теряем на курсе?', 'Покажи прогноз курса по мнению банка', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ВЭД: экспорт · Турция, Египет · 60% выручки в USD.',
                calc_tool: 'calc_fx_impact(export_share=60%, Δfx=1 ₽)',
                calc: '≈ −11 млн ₽ выручки за квартал на каждый рубль укрепления.',
            },
        },
        {
            company_id: 'U-33650',
            relevance: 0.85,
            impact: 'opportunity',
            why_you: 'импорт из Китая · расчёты в CNY · аккредитивы',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: '«МедТехСнаб» закупает оборудование в Китае с оплатой в юанях — около 70% себестоимости.',
                    features: ['FX_IMPORT_CNY'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Сейчас юань дешевле, чем банк ожидает в IV квартале. Покупка CNY под платежи до декабря может сэкономить 4–6% стоимости поставок.',
                    features: ['FX_IMPORT_CNY', 'CL_PRODUCT_LC_MARK'],
                    src: ['cmi-tactic'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Купить CNY под аккредитивы IV квартала по текущему курсу.', roles: ['treasurer', 'cfo'] },
                { id: 'a2', text: 'Оформить форвард на покупку юаней.', roles: ['cfo'], product: 'Форвард' },
            ],
            features: [
                { code: 'FX_IMPORT_CNY', label: 'Импорт в CNY (70% себестоимости)', weight: 0.9 },
                { code: 'CL_PRODUCT_LC_MARK', label: 'Аккредитивы в банке', weight: 0.5 },
            ],
            confidence: 'medium',
            bank_offer: {
                title: 'Предложение Альфа-Банка',
                text: 'Форвард на покупку CNY: фиксирует курс оплаты поставок по аккредитивам IV квартала.',
                product: 'Форвард',
            },
            suggested_questions: ['Сколько сэкономим на покупке юаней?', 'Покажи прогноз курса по мнению банка'],
            trace: {
                profile: 'ВЭД: импорт · Китай · CNY · аккредитивы на ¥ 18 млн до декабря.',
                calc_tool: 'calc_fx_impact(cny_payments=¥18 млн, Δfx=5%)',
                calc: '≈ 11 млн ₽ экономии при покупке CNY сейчас против прогноза банка.',
            },
        },
    ],
    'gov-grain-duty-2026-09': [
        {
            company_id: 'U-20917',
            relevance: 0.92,
            impact: 'opportunity',
            why_you: 'экспорт пшеницы · ОКВЭД 01.11 · контракты на IV квартал',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: '«АгроЮг» планирует отгрузить на экспорт около 120 тыс. т пшеницы в IV квартале.',
                    features: ['OKVED_MAIN', 'FX_EXPORT'],
                },
                {
                    kind: 'consequence_opportunity',
                    text: 'Снижение пошлины на ~15% даёт экономию около 70 млн ₽ на объёме IV квартала и частично компенсирует крепкий рубль.',
                    features: ['FX_EXPORT'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Сдвинуть часть сентябрьских отгрузок на октябрь.', roles: ['ceo', 'procurement'] },
                { id: 'a2', text: 'Пересмотреть цены в контрактах IV квартала.', roles: ['ceo', 'cfo'] },
            ],
            features: [
                { code: 'OKVED_MAIN', label: 'ОКВЭД 01.11 — зерновые', weight: 0.86 },
                { code: 'FX_EXPORT', label: 'Экспорт пшеницы 120 тыс. т', weight: 0.79 },
            ],
            confidence: 'high',
            suggested_questions: ['Сколько сэкономим на пошлине?', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ОКВЭД 01.11 · экспорт 120 тыс. т в IV кв. · Турция, Египет.',
                calc_tool: 'calc_duty_impact(volume=120 тыс. т, Δduty=-15%)',
                calc: '≈ 70 млн ₽ экономии на пошлине в IV квартале.',
            },
        },
    ],
    'gov-med-marking-2026-09': [
        {
            company_id: 'U-33650',
            relevance: 0.87,
            impact: 'attention',
            why_you: 'ОКВЭД 46.46 · складские остатки медизделий',
            ai_inference: [
                {
                    kind: 'why_relevant',
                    text: 'На складах «МедТехСнаб» около 14 тыс. единиц медизделий, ввезённых до начала маркировки.',
                    features: ['OKVED_MAIN', 'INVENTORY'],
                },
                {
                    kind: 'consequence_risk',
                    text: 'Остатки, не промаркированные до 28 февраля 2027 года, нельзя будет продать — под риском товар примерно на 180 млн ₽.',
                    features: ['INVENTORY'],
                },
            ],
            actions: [
                { id: 'a1', text: 'Провести инвентаризацию остатков и заказать коды маркировки.', roles: ['procurement', 'ceo'] },
                { id: 'a2', text: 'Заложить в бюджет расходы на маркировку (~1,5 млн ₽).', roles: ['cfo'] },
            ],
            features: [
                { code: 'OKVED_MAIN', label: 'ОКВЭД 46.46 — опт медтоваров', weight: 0.9 },
                { code: 'INVENTORY', label: 'Остатки 14 тыс. ед.', weight: 0.72 },
            ],
            confidence: 'high',
            suggested_questions: ['Какие сроки маркировки?', 'Сколько это стоит?', 'Что пишут первоисточники?'],
            trace: {
                profile: 'ОКВЭД 46.46 · склад в Москве · остатки 14 тыс. ед.',
                calc_tool: 'calc_inventory_risk(units=14 тыс.)',
                calc: '≈ 180 млн ₽ остатков под риском; маркировка ≈ 1,5 млн ₽.',
            },
        },
    ],
};

/* ---------------- Трасса агента ---------------- */

function buildTrace(event: EventBase, it: CompanyInterpretation): TraceStep[] {
    const company = COMPANIES.find((c) => c.id === it.company_id)!;
    const bankCount = event.sources.filter((s) => s.kind === 'bank_research').length;
    const newsCount = event.sources.length - bankCount;
    const steps: TraceStep[] = [
        {
            title: 'Планирование',
            tool: 'planner',
            detail: `Цель: оценить влияние события на ${company.id}. План: профиль → первоисточник → аналитика банка → расчёт → самопроверка → сборка.`,
            time: 0.6,
            state: 'done',
        },
        { title: 'Профиль клиента', tool: `get_client_profile(${company.id})`, detail: it.trace.profile, time: 0.2, state: 'done' },
        {
            title: 'Поиск новостей',
            tool: event.query,
            detail: `Найдено ${newsCount + 2} ${plural(newsCount + 2, 'публикация', 'публикации', 'публикаций')}, 2 дубля объединены, ${newsCount} ${plural(newsCount, 'источник оставлен', 'источника оставлено', 'источников оставлено')}.`,
            time: 1.1,
            state: 'done',
        },
        {
            title: 'RAG по аналитике Альфа-Банка',
            tool: 'rag_alfa_research(k=5)',
            detail: bankCount
                ? `${bankCount} ${plural(bankCount, 'релевантный материал', 'релевантных материала', 'релевантных материалов')} ЦМИ: ${event.sources
                      .filter((s) => s.kind === 'bank_research')
                      .map((s) => `«${s.title}»`)
                      .join(', ')}.`
                : 'Материалов банка по теме не найдено — блок «Позиция банка» не заполняется, вывод помечен как вывод AI.',
            time: 1.4,
            state: 'done',
        },
        {
            title: 'Самопроверка',
            tool: it.trace.retry ? "verifier → news_search(source='cbr.ru')" : 'verifier',
            detail: it.trace.retry ?? 'Факты сверены с первоисточниками, противоречий не найдено.',
            time: it.trace.retry ? 2.3 : 0.9,
            state: it.trace.retry ? 'retry' : 'done',
        },
        { title: 'Расчёт влияния', tool: it.trace.calc_tool, detail: it.trace.calc, time: 0.1, state: 'done' },
        {
            title: 'Сборка инсайта',
            tool: `compose_insight(schema=${SCHEMA_VERSION})`,
            detail: `6 блоков, ${event.sources.length + it.ai_inference.length} ссылок на источники и признаки, разметка origin: fact / bank / ai.`,
            time: 4.1,
            state: 'done',
        },
    ];
    return steps.map((s, i) => ({ ...s, title: `${i + 1}. ${s.title}` }));
}

function runId(eventId: string, companyId: string) {
    let h = 0;
    for (const ch of eventId + companyId) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const hex = h.toString(16).padStart(8, '0');
    return `${hex.slice(0, 4)}-${hex.slice(4, 8)}`;
}

function buildInsight(event: EventBase, it: CompanyInterpretation): Insight {
    const trace = buildTrace(event, it);
    const bankCount = event.bank_view.length ? event.sources.filter((s) => s.kind === 'bank_research').length : 0;
    const newsCount = event.sources.length - bankCount;
    const retries = trace.filter((s) => s.state === 'retry').length;
    const confidenceText = { high: 'высокая', medium: 'средняя', low: 'низкая' }[it.confidence];
    return {
        schema: SCHEMA_VERSION,
        event_id: event.event_id,
        run_id: runId(event.event_id, it.company_id),
        company_id: it.company_id,
        title: it.title ?? event.title,
        summary: event.summary,
        published_at: event.published_at,
        topics: event.topics,
        relevance: it.relevance,
        impact: it.impact,
        why_you: it.why_you,
        facts: event.facts,
        bank_view: event.bank_view,
        ai_inference: it.ai_inference,
        actions: it.actions,
        sources: event.sources,
        features: it.features,
        confidence: it.confidence,
        basis: `${newsCount} ${plural(newsCount, 'новостной источник', 'новостных источника', 'новостных источников')} · ${bankCount} ${plural(bankCount, 'материал', 'материала', 'материалов')} ЦМИ Альфа-Банка · ${it.features.length} ${plural(it.features.length, 'признак', 'признака', 'признаков')} компании. ${retries ? 'Противоречие между источниками устранено повторным поиском' : 'Противоречий между источниками не найдено'}, уверенность ${confidenceText}.`,
        trace,
        bank_offer: it.bank_offer,
        suggested_questions: it.suggested_questions,
    };
}


/**
 * Тестовые ответы пайплайна бэкенда в формате «ВЫХОД» (docs/vyhod-examples/*.json) —
 * проходят через тот же адаптер, что и в режиме http. Новый файл в папке появится в ленте сам.
 */
export const BACKEND_OUTPUTS: Interpretation[] = Object.values(
    import.meta.glob<Interpretation>('../../docs/vyhod-examples/*.json', { eager: true, import: 'default' }),
);

/** Все инсайты: event × company */
export const INSIGHTS: Insight[] = [
    ...EVENTS.flatMap((event) => (INTERPRETATIONS[event.event_id] ?? []).map((it) => buildInsight(event, it))),
    ...BACKEND_OUTPUTS.map(interpretationToInsight),
];
