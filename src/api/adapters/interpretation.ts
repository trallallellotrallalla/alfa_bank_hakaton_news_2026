import type {
    Action,
    AiInference,
    BankView,
    Confidence,
    Fact,
    Feature,
    FeedResponse,
    Impact,
    Insight,
    Role,
    Source,
    Topic,
    TraceResponse,
    TraceStep,
} from '../../types/insight';
import { SCHEMA_VERSION } from '../../types/insight';
import type { BankViewItem, InferenceItem, Interpretation, InterpretationSource } from '../../types/interpretation';
import { isInterpretation } from '../../types/interpretation';
import { plural } from '../../utils/format';

/**
 * Адаптер «ВЫХОД» (ответ пайплайна бэкенда) → insight.v1 (формат экранов).
 *
 *   event.news_id          → event_id          what_happened         → facts[]
 *   interpretation_id      → run_id            attribution.bank_view → bank_view[]
 *   client_id              → company_id        why_it_matters, attribution.model_inference → ai_inference[why_relevant]
 *   risks / opportunities  → ai_inference[consequence_*]
 *   recommended_actions    → actions[]         sources[client_signal] → features[]
 *   sources[news|analytics]→ sources[]         confidence 0..1       → high / medium / low
 *
 * Чего нет во ВЫХОДЕ, адаптер восстанавливает: impact (по рискам и возможностям), topics (по заголовку),
 * relevance (по confidence), trace (по attribution, с пометкой «восстановлено»).
 */

const DEFAULT_PUBLISHER = { news: 'Новость', analytics: 'ЦМИ Альфа-Банка' };

const newsSrcId = (id: string | number) => `news:${id}`;
const analyticsSrcId = (chunk: string) => `analytics:${chunk}`;

/** «news:1001» / «analytics:…» / «1001» → id источника в insight.v1 */
function normalizeSrcRef(ref: string, newsId: string | number): string {
    if (ref.startsWith('news:') || ref.startsWith('analytics:')) return ref;
    return String(ref) === String(newsId) ? newsSrcId(ref) : analyticsSrcId(ref);
}

const textOf = (x: InferenceItem | { text: string }) => (typeof x === 'string' ? x : x.text);
const signalsOf = (x: InferenceItem) => (typeof x === 'string' ? [] : (x.signals ?? []));

/** Подписи для частых сигналов клиента; остальные — из кода сигнала */
const SIGNAL_LABELS: Record<string, string> = {
    credit_dependency: 'Зависимость от заёмного финансирования',
    has_free_cash: 'Свободные денежные средства',
    fx_exposure: 'Валютные расходы или выручка',
    import_dependency: 'Зависимость от импорта',
    export_share: 'Доля экспортной выручки',
    counterparty_risk: 'Риск ключевых контрагентов',
};

/** «credit_dependency» → подпись из словаря или «Credit dependency» */
const humanize = (code: string) => {
    if (SIGNAL_LABELS[code]) return SIGNAL_LABELS[code];
    const s = code.replace(/[_-]+/g, ' ').trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
};

/** Дата без времени («2026-09-11») трактуется как московская полночь */
const toIso = (d: string) => (/^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T00:00:00+03:00` : d);

const TOPIC_RULES: [RegExp, Topic][] = [
    [/ставк|кредит|ЦБ|банк росси/i, 'rates'],
    [/курс|рубл|доллар|юан|валют/i, 'fx'],
    [/нефт|дизел|топлив|зерн|сырь|металл|цен[аы] на/i, 'commodities'],
    [/банкрот|иск|контрагент|арбитраж/i, 'counterparty'],
    [/закон|правительств|маркировк|пошлин|регулир/i, 'regulation'],
    [/экспорт|импорт|санкц|ВЭД|таможн/i, 'trade'],
];
const KNOWN_TOPICS: Topic[] = ['rates', 'fx', 'commodities', 'counterparty', 'regulation', 'trade'];

function inferTopics(given: string[] | undefined, text: string): Topic[] {
    const fromBackend = (given ?? []).filter((t): t is Topic => (KNOWN_TOPICS as string[]).includes(t));
    if (fromBackend.length) return fromBackend;
    const found = TOPIC_RULES.filter(([re]) => re.test(text)).map(([, t]) => t);
    return found.length ? [...new Set(found)] : ['regulation'];
}

function inferImpact(i: Interpretation): Impact {
    if (i.impact) return i.impact;
    const risks = i.risks?.length ?? 0;
    const opps = i.opportunities?.length ?? 0;
    if (risks && risks >= opps) return 'risk';
    if (opps) return 'opportunity';
    return 'attention';
}

function toConfidence(c: Interpretation['confidence']): Confidence {
    if (typeof c === 'string') return c;
    return c >= 0.75 ? 'high' : c >= 0.5 ? 'medium' : 'low';
}

function bankViewItems(i: Interpretation): BankViewItem[] {
    const raw = i.bank_view ?? i.attribution?.bank_view;
    if (!raw) return [];
    return Array.isArray(raw) ? raw : [raw];
}

function buildSources(i: Interpretation, bank: BankViewItem[]): { sources: Source[]; features: Feature[] } {
    const sources: Source[] = [];
    const features: Feature[] = [];
    const published = toIso(i.event.published_at);
    const add = (s: Source) => !sources.some((x) => x.id === s.id) && sources.push(s);

    for (const s of i.sources) {
        if (s.type === 'news') {
            add({
                id: newsSrcId(s.id),
                kind: 'news',
                publisher: s.publisher ?? DEFAULT_PUBLISHER.news,
                title: s.title ?? (String(s.id) === String(i.event.news_id) ? i.event.title : `Новость #${s.id}`),
                url: s.url,
                published_at: s.published_at ? toIso(s.published_at) : published,
            });
        } else if (s.type === 'analytics') {
            const fromBank = bank.find((b) => b.chunk_id === s.chunk_id);
            add(analyticsSource(s, fromBank, published));
        } else {
            features.push({ code: s.id, label: s.label ?? humanize(s.id), weight: s.weight ?? 0 });
        }
    }
    // Чанки, на которые ссылается позиция банка, но которых нет в sources
    for (const b of bank) {
        if (b.chunk_id) add(analyticsSource({ type: 'analytics', chunk_id: b.chunk_id }, b, published));
    }
    // Новость события должна быть в источниках всегда
    if (!sources.some((s) => s.id === newsSrcId(i.event.news_id))) {
        add({
            id: newsSrcId(i.event.news_id),
            kind: 'news',
            publisher: DEFAULT_PUBLISHER.news,
            title: i.event.title,
            published_at: published,
        });
    }
    return { sources, features };
}

function analyticsSource(
    s: Extract<InterpretationSource, { type: 'analytics' }>,
    b: BankViewItem | undefined,
    published: string,
): Source {
    const title = s.doc_title ?? b?.doc_title ?? s.chunk_id;
    const page = s.page ?? b?.page;
    return {
        id: analyticsSrcId(s.chunk_id),
        kind: 'bank_research',
        publisher: s.publisher ?? DEFAULT_PUBLISHER.analytics,
        title: page ? `${title}, с. ${page}` : title,
        url: s.url,
        published_at: s.published_at ? toIso(s.published_at) : published,
    };
}

/** Признаки клиента: из sources[client_signal] + все signals, упомянутые в выводах; вес — по частоте упоминаний */
function buildFeatures(i: Interpretation, base: Feature[]): Feature[] {
    const mentioned = [i.why_it_matters, ...(i.risks ?? []), ...(i.opportunities ?? [])].flatMap(signalsOf);
    const all = new Map(base.map((f) => [f.code, f]));
    for (const code of mentioned) if (!all.has(code)) all.set(code, { code, label: humanize(code), weight: 0 });
    const list = [...all.values()];
    const count = (code: string) => mentioned.filter((m) => m === code).length;
    return list
        .map((f, idx) => ({ ...f, weight: f.weight || Math.max(0.3, Math.min(0.95, 0.9 - idx * 0.15 + count(f.code) * 0.05)) }))
        .sort((a, b) => b.weight - a.weight);
}

function buildTrace(i: Interpretation, insight: Omit<Insight, 'trace' | 'basis'>): TraceStep[] {
    if (i.trace?.length) {
        return i.trace.map((s, idx) => ({
            title: /^\d+\./.test(s.title) ? s.title : `${idx + 1}. ${s.title}`,
            tool: s.tool ?? '—',
            detail: s.detail ?? '',
            time: s.time ?? 0,
            state: s.state ?? 'done',
        }));
    }
    // Бэкенд трассу не передал — восстанавливаем шаги по attribution и источникам
    const bank = insight.sources.filter((s) => s.kind === 'bank_research');
    const note = ' (восстановлено по attribution — бэкенд не передал trace)';
    const steps: Omit<TraceStep, 'title'>[] = [
        {
            tool: `client.signals(${i.client_id})`,
            detail: `Сигналы клиента: ${insight.features.map((f) => f.code).join(', ') || 'не переданы'}.${note}`,
            time: 0,
            state: 'done',
        },
        {
            tool: `news[${i.event.news_id}]`,
            detail: `Событие: «${i.event.title}».${note}`,
            time: 0,
            state: 'done',
        },
        {
            tool: bank.length ? `analytics[${bank.map((s) => s.id.replace('analytics:', '')).join(', ')}]` : 'analytics[]',
            detail: bank.length
                ? `Позиция банка взята из: ${bank.map((s) => `«${s.title}»`).join(', ')}.${note}`
                : 'Аналитика банка по теме не найдена — блок «Позиция банка» пуст.',
            time: 0,
            state: 'done',
        },
        {
            tool: 'llm(schema=ВЫХОД)',
            detail: `Интерпретация ${i.interpretation_id}: ${insight.ai_inference.length} ${plural(insight.ai_inference.length, 'вывод', 'вывода', 'выводов')}, ${insight.actions.length} ${plural(insight.actions.length, 'действие', 'действия', 'действий')}.`,
            time: 0,
            state: 'done',
        },
        {
            tool: `adapter(ВЫХОД → ${SCHEMA_VERSION})`,
            detail: 'Разметка origin: fact / bank / ai для интерфейса.',
            time: 0,
            state: 'done',
        },
    ];
    const titles = ['Профиль клиента', 'Новость', 'Аналитика Альфа-Банка', 'Генерация интерпретации', 'Сборка для интерфейса'];
    return steps.map((s, idx) => ({ ...s, title: `${idx + 1}. ${titles[idx]}` }));
}

/** ВЫХОД → insight.v1 */
export function interpretationToInsight(i: Interpretation): Insight {
    const newsId = i.event.news_id;
    const bank = bankViewItems(i);
    const { sources, features: signalFeatures } = buildSources(i, bank);
    const features = buildFeatures(i, signalFeatures);
    const allCodes = features.map((f) => f.code);
    const withSignals = (x: InferenceItem) => (signalsOf(x).length ? signalsOf(x) : allCodes);

    const facts: Fact[] = (typeof i.what_happened === 'string' ? [i.what_happened] : i.what_happened).map((f) =>
        typeof f === 'string'
            ? { text: f, src: [newsSrcId(newsId)] }
            : { text: f.text, src: (f.src?.length ? f.src : [String(newsId)]).map((r) => normalizeSrcRef(r, newsId)) },
    );

    const bank_view: BankView[] = bank.map((b) => ({
        text: b.text,
        src: b.src?.length ? b.src.map((r) => normalizeSrcRef(r, newsId)) : b.chunk_id ? [analyticsSrcId(b.chunk_id)] : [],
    }));

    const ai_inference: AiInference[] = [
        { kind: 'why_relevant', text: textOf(i.why_it_matters), features: withSignals(i.why_it_matters) },
        ...(i.attribution?.model_inference
            ? [{ kind: 'why_relevant' as const, text: i.attribution.model_inference, features: allCodes, src: bank_view.flatMap((b) => b.src) }]
            : []),
        ...(i.risks ?? []).map((r) => ({ kind: 'consequence_risk' as const, text: textOf(r), features: withSignals(r) })),
        ...(i.opportunities ?? []).map((o) => ({ kind: 'consequence_opportunity' as const, text: textOf(o), features: withSignals(o) })),
    ];

    const actions: Action[] = (i.recommended_actions ?? []).map((a, idx) =>
        typeof a === 'string' ? { id: `a${idx + 1}`, text: a } : { id: `a${idx + 1}`, text: a.text, roles: a.roles as Role[] | undefined },
    );

    const confidence = toConfidence(i.confidence);
    const relevance = i.relevance ?? (typeof i.confidence === 'number' ? i.confidence : { high: 0.85, medium: 0.7, low: 0.55 }[confidence]);
    const whyCodes = signalsOf(i.why_it_matters).length ? signalsOf(i.why_it_matters) : allCodes;
    const whyYou =
        features
            .filter((f) => whyCodes.includes(f.code))
            .map((f) => f.label.toLowerCase())
            .join(' · ') || textOf(i.why_it_matters).split(/ — |\. /)[0];

    const partial: Omit<Insight, 'trace' | 'basis'> = {
        schema: SCHEMA_VERSION,
        event_id: String(newsId),
        run_id: i.interpretation_id,
        company_id: i.client_id,
        title: i.event.title,
        summary: i.event.summary ?? facts[0]?.text.split(/(?<=\.)\s/)[0] ?? '',
        published_at: toIso(i.event.published_at),
        topics: inferTopics(i.topics, `${i.event.title} ${facts.map((f) => f.text).join(' ')}`),
        relevance,
        impact: inferImpact(i),
        why_you: whyYou,
        facts,
        bank_view,
        ai_inference,
        actions,
        sources,
        features,
        confidence,
        suggested_questions: i.suggested_questions ?? [
            'Что это значит для нас в цифрах?',
            'Покажи прогноз по мнению банка',
            'Что пишут первоисточники?',
        ],
    };

    const newsCount = sources.filter((s) => s.kind !== 'bank_research').length;
    const bankCount = sources.length - newsCount;
    const trace = buildTrace(i, partial);
    const retries = trace.filter((s) => s.state === 'retry').length;
    const confidenceText = { high: 'высокая', medium: 'средняя', low: 'низкая' }[confidence];
    const pct = typeof i.confidence === 'number' ? ` (${Math.round(i.confidence * 100)}%)` : '';

    return {
        ...partial,
        trace,
        basis: `${newsCount} ${plural(newsCount, 'новостной источник', 'новостных источника', 'новостных источников')} · ${bankCount} ${plural(bankCount, 'материал', 'материала', 'материалов')} аналитики Альфа-Банка · ${features.length} ${plural(features.length, 'сигнал', 'сигнала', 'сигналов')} клиента. ${retries ? 'Противоречие устранено повторным поиском' : 'Противоречий не найдено'}, уверенность ${confidenceText}${pct}.`,
    };
}

/* ---------- Нормализация ответов API: бэкенд может отдавать и insight.v1, и ВЫХОД ---------- */

const isInsight = (x: unknown): x is Insight => !!x && typeof x === 'object' && (x as Insight).schema === SCHEMA_VERSION;

export function toInsight(x: unknown): Insight {
    if (isInsight(x)) return x;
    if (isInterpretation(x)) return interpretationToInsight(x);
    throw new Error('Ответ бэкенда не похож ни на insight.v1, ни на ВЫХОД');
}

/** /feed: FeedResponse, массив ВЫХОДов или { items: ВЫХОД[] } */
export function toFeed(x: unknown, companyId: string, role: Role): FeedResponse {
    const raw = Array.isArray(x) ? x : ((x as { items?: unknown[] })?.items ?? []);
    const meta = Array.isArray(x) ? {} : (x as Partial<FeedResponse>);
    const items = raw.map(toInsight).sort((a, b) => b.relevance - a.relevance);
    return {
        company_id: meta.company_id ?? companyId,
        role: meta.role ?? role,
        updated_at: meta.updated_at ?? new Date().toISOString(),
        items,
    };
}

/** /trace: TraceResponse или ВЫХОД (тогда трасса собирается из него) */
export function toTrace(x: unknown): TraceResponse {
    if (x && typeof x === 'object' && 'steps' in x && 'insight' in x) {
        const t = x as TraceResponse;
        return { ...t, insight: toInsight(t.insight) };
    }
    const insight = toInsight(x);
    return {
        run_id: insight.run_id,
        event_id: insight.event_id,
        company_id: insight.company_id,
        steps: insight.trace,
        retries: insight.trace.filter((s) => s.state === 'retry').length,
        duration_s: Math.round(insight.trace.reduce((a, s) => a + s.time, 0) * 10) / 10,
        tokens: 0,
        models: '—',
        features: insight.features,
        insight,
    };
}
