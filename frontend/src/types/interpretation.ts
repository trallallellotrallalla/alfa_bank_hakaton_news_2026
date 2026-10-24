/**
 * Формат «ВЫХОД» — ответ пайплайна бэкенда (LLM + поля, заполненные кодом).
 * Фронтенд принимает его как есть и переводит в insight.v1 адаптером src/api/adapters/interpretation.ts.
 *
 * Типы допускают и исходный вариант (плоские строки), и рекомендованный
 * (объекты с src / signals / roles), чтобы бэкенд мог переходить постепенно.
 */

import type { Impact, Role } from './insight';

/** Пункт вывода: строка или объект с признаками клиента */
export type InferenceItem = string | { text: string; signals?: string[] };

/** Действие: строка или объект с ролями */
export type ActionItem = string | { text: string; roles?: Role[] };

/** Факт: строка или объект со ссылками на источники */
export type FactItem = string | { text: string; src?: string[] };

export interface BankViewItem {
    text: string;
    chunk_id?: string;
    doc_title?: string;
    page?: number;
    /** Рекомендованный вариант: ссылки вида "analytics:<chunk_id>" */
    src?: string[];
}

export type InterpretationSource =
    | { type: 'news'; id: string | number; title?: string; url?: string; publisher?: string; published_at?: string }
    | { type: 'analytics'; chunk_id: string; doc_title?: string; page?: number; url?: string; publisher?: string; published_at?: string }
    | { type: 'client_signal'; id: string; label?: string; weight?: number };

export interface TraceStepIn {
    title: string;
    tool?: string;
    detail?: string;
    time?: number;
    state?: 'done' | 'retry' | 'running';
}

export interface Interpretation {
    /** Интерпретатор из ветки ml отдаёт число, другие версии — строку */
    interpretation_id: string | number;
    client_id: string;
    event: {
        news_id: string | number;
        title: string;
        published_at: string;
        summary?: string;
    };
    /** Рекомендованные поля — если бэкенд их не передал, адаптер подставит значения по умолчанию */
    relevance?: number;
    impact?: Impact;
    topics?: string[];

    what_happened: string | FactItem[];
    why_it_matters: InferenceItem;
    risks?: InferenceItem[];
    opportunities?: InferenceItem[];
    recommended_actions?: ActionItem[];

    attribution?: {
        /** Один объект (исходный вариант), массив или null, если аналитики банка нет */
        bank_view?: BankViewItem | BankViewItem[] | null;
        model_inference?: string;
    };
    /** Рекомендованный вариант: позиция банка на верхнем уровне */
    bank_view?: BankViewItem[];

    sources: InterpretationSource[];
    /** 0..1 или high / medium / low */
    confidence: number | 'high' | 'medium' | 'low';
    /** Шаги пайплайна, если бэкенд их записывает */
    trace?: TraceStepIn[];
    suggested_questions?: string[];
}

export const isInterpretation = (x: unknown): x is Interpretation =>
    !!x && typeof x === 'object' && 'interpretation_id' in x && 'event' in x;
