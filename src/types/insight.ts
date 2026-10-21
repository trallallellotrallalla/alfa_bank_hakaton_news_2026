/**
 * Контракт insight.v1 — ответ AI-агента по одному событию для конкретной компании и роли.
 * Это контракт с бэкендом: JSON Schema лежит в docs/insight.v1.schema.json,
 * пример — в docs/insight.v1.example.json, эндпоинты — в docs/openapi.yaml.
 *
 * Главный принцип: каждое утверждение помечено происхождением —
 *   facts        → «Факт» (только из первоисточников, со ссылками src)
 *   bank_view    → «Позиция банка» (только из аналитики Альфа-Банка, со ссылками src)
 *   ai_inference → «Вывод AI» (интерпретация агента, с признаками компании features)
 */

export const SCHEMA_VERSION = 'insight.v1' as const;

/** Характер влияния события на бизнес клиента */
export type Impact = 'risk' | 'opportunity' | 'attention' | 'scenario';

/** Происхождение утверждения */
export type Origin = 'fact' | 'bank' | 'ai';

export type Confidence = 'high' | 'medium' | 'low';

/** Роль пользователя в Альфа-Бизнесе — влияет на ранжирование и формулировку действий */
export type Role = 'ceo' | 'cfo' | 'treasurer' | 'procurement';

/** Тема события — используется в фильтрах ленты и в ранжировании под роль */
export type Topic = 'rates' | 'fx' | 'commodities' | 'counterparty' | 'regulation' | 'trade';

export type SourceKind = 'regulator' | 'news' | 'bank_research' | 'registry' | 'exchange' | 'client_data';

/** Первоисточник. id используется в полях src[] у утверждений */
export interface Source {
    id: string;
    kind: SourceKind;
    publisher: string;
    title: string;
    /** Ссылка на первоисточник; без неё источник показывается, но не ссылкой */
    url?: string;
    published_at: string; // ISO 8601
}

/** Утверждение-факт (из новостей/регулятора/реестров) */
export interface Fact {
    text: string;
    src: string[];
}

/** Утверждение из аналитики банка (ЦМИ Альфа-Банка и др.) */
export interface BankView {
    text: string;
    src: string[];
}

/** Признак компании, на который опирается вывод AI */
export interface Feature {
    /** Код признака в витрине клиента, например CL_PRODUCT_LOA_MARK */
    code: string;
    label: string;
    /** Вклад признака в вывод, 0..1 */
    weight: number;
}

export type InferenceKind = 'why_relevant' | 'consequence_risk' | 'consequence_opportunity';

/** Вывод AI — всегда со списком признаков компании */
export interface AiInference {
    kind: InferenceKind;
    text: string;
    features: string[]; // Feature.code
    src?: string[];
}

export interface Action {
    id: string;
    text: string;
    /** Для каких ролей действие приоритетно (пусто — для всех) */
    roles?: Role[];
    /** Связанный продукт банка, если действие ведёт к предложению */
    product?: string;
}

export type TraceState = 'done' | 'retry' | 'running';

/** Шаг агента в трассе вывода */
export interface TraceStep {
    title: string;
    tool: string;
    detail: string;
    /** Длительность шага в секундах */
    time: number;
    state: TraceState;
}

export interface BankOffer {
    title: string;
    text: string;
    product: string;
}

/** Основной объект insight.v1 */
export interface Insight {
    schema: typeof SCHEMA_VERSION;
    /** id события (новостного кластера), общий для всех компаний */
    event_id: string;
    /** id прогона агента; по нему доступна трасса GET /trace/:run_id */
    run_id: string;
    company_id: string;
    title: string;
    summary: string;
    published_at: string;
    topics: Topic[];
    /** Релевантность события для компании и роли, 0..1 */
    relevance: number;
    impact: Impact;
    /** Короткая причина персонализации: «Почему вам: …» */
    why_you: string;
    facts: Fact[];
    bank_view: BankView[];
    ai_inference: AiInference[];
    actions: Action[];
    sources: Source[];
    features: Feature[];
    confidence: Confidence;
    /** Краткое обоснование для блока «На чём основан вывод?» */
    basis: string;
    trace: TraceStep[];
    bank_offer?: BankOffer;
    /** Подсказки для уточняющих вопросов в чате */
    suggested_questions: string[];
}

/* ---------- Компания (синтетический клиент) ---------- */

export interface Account {
    title: string;
    amount: string;
    note: string;
}

export interface Operation {
    title: string;
    amount: string;
    incoming?: boolean;
}

export interface CreditLine {
    limit_mln: number;
    drawn_mln: number;
    /** Маржа к ключевой ставке, п.п. */
    margin_pp: number;
}

export interface Company {
    /** Синтетический идентификатор клиента, формат U-XXXXX */
    id: string;
    name: string;
    short: string;
    initials: string;
    okved: string;
    okved_title: string;
    revenue: string;
    staff: string;
    region: string;
    group_id: string;
    group_size: number;
    foreign_trade: string;
    products: string[];
    top_counterparties: string;
    credit_line?: CreditLine;
    accounts: Account[];
    operations: Operation[];
    tasks: string[];
    user_name: string;
    user_initials: string;
    /** Количество признаков в профиле, по которым идёт отбор */
    features_count: number;
}

export const ROLE_LABEL: Record<Role, string> = {
    ceo: 'генеральный директор',
    cfo: 'финансовый директор',
    treasurer: 'казначей',
    procurement: 'директор по закупкам',
};

export const IMPACT_LABEL: Record<Impact, string> = {
    risk: 'Риск',
    opportunity: 'Возможность',
    attention: 'Внимание',
    scenario: 'Сценарий',
};

export const TOPIC_LABEL: Record<Topic, string> = {
    rates: 'Ставки',
    fx: 'Валюта',
    commodities: 'Сырьё',
    counterparty: 'Контрагенты',
    regulation: 'Регулирование',
    trade: 'ВЭД',
};

/* ---------- Чат ---------- */

export interface ChatTable {
    columns: string[];
    rows: string[][];
}

export interface Citation {
    n: number;
    label: string;
    source_id?: string;
}

export interface ChatAnswer {
    /** Происхождение ответа: всегда содержит 'ai', плюс 'bank', если опирается на позицию банка */
    origins: Origin[];
    paragraphs: string[];
    table?: ChatTable;
    citations: Citation[];
    /** Уточняющий вопрос агента, если запрос неоднозначен */
    clarify?: { question: string; options: string[] };
    /** Альтернативные разрезы ответа */
    slices?: string[];
    run_id?: string;
}

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    text?: string;
    answer?: ChatAnswer;
}

export interface ChatRequest {
    company_id: string;
    role: Role;
    event_id?: string;
    messages: { role: 'user' | 'assistant'; content: string }[];
}

export interface FeedResponse {
    company_id: string;
    role: Role;
    updated_at: string;
    items: Insight[];
}

export interface TraceResponse {
    run_id: string;
    event_id: string;
    company_id: string;
    steps: TraceStep[];
    retries: number;
    duration_s: number;
    tokens: number;
    models: string;
    features: Feature[];
    insight: Insight;
}
