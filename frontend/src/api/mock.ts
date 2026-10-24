import type { Api } from './types';
import type { Insight, Role, Topic, TraceResponse } from '../types/insight';
import { COMPANIES, getCompany } from '../mocks/companies';
import { INSIGHTS } from '../mocks/events';
import { mockChatAnswer } from '../mocks/chat';

const delay = <T>(value: T, ms = 250) => new Promise<T>((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

/** Насколько роль усиливает интерес к теме — так одна и та же лента ранжируется по-разному */
const ROLE_TOPIC_BOOST: Record<Role, Partial<Record<Topic, number>>> = {
    ceo: { counterparty: 0.06, regulation: 0.05, trade: 0.03 },
    cfo: { rates: 0.04, fx: 0.03 },
    treasurer: { fx: 0.08, rates: 0.03 },
    procurement: { commodities: 0.08, trade: 0.04, counterparty: 0.03 },
};

/** Порог, ниже которого событие не попадает в ленту */
const MIN_RELEVANCE = 0.5;

function personalize(insight: Insight, role: Role): Insight {
    const boost = Math.max(0, ...insight.topics.map((t) => ROLE_TOPIC_BOOST[role][t] ?? 0));
    const relevance = Math.min(0.99, Math.round((insight.relevance + boost) * 100) / 100);
    const actions = [...insight.actions].sort(
        (a, b) => Number(!!b.roles?.includes(role)) - Number(!!a.roles?.includes(role)),
    );
    return { ...insight, relevance, actions };
}

function feedFor(companyId: string, role: Role) {
    return INSIGHTS.filter((i) => i.company_id === companyId && i.relevance >= MIN_RELEVANCE)
        .map((i) => personalize(i, role))
        .sort((a, b) => b.relevance - a.relevance);
}

export const mockApi: Api = {
    getCompanies: () => delay(COMPANIES, 50),

    getFeed: (companyId, role) =>
        delay({ company_id: companyId, role, updated_at: '2026-09-12T09:40:00+03:00', items: feedFor(companyId, role) }),

    getEvent: (eventId, companyId, role) => {
        const insight = INSIGHTS.find((i) => i.event_id === eventId && i.company_id === companyId);
        if (!insight) return Promise.reject(new Error('Событие не относится к выбранной компании'));
        return delay(personalize(insight, role));
    },

    chat: (req) => {
        const company = getCompany(req.company_id);
        const feed = feedFor(company.id, req.role);
        const insight = feed.find((i) => i.event_id === req.event_id) ?? feed[0];
        const fxInsight = feed.find((i) => i.topics.includes('fx'));
        const question = [...req.messages].reverse().find((m) => m.role === 'user')?.content ?? '';
        return delay(mockChatAnswer(question, company, req.role, insight, fxInsight), 2600);
    },

    getTrace: (runId) => {
        const insight = INSIGHTS.find((i) => i.run_id === runId);
        if (!insight) return Promise.reject(new Error('Трасса не найдена'));
        const trace: TraceResponse = {
            run_id: runId,
            event_id: insight.event_id,
            company_id: insight.company_id,
            steps: insight.trace,
            retries: insight.trace.filter((s) => s.state === 'retry').length,
            duration_s: Math.round(insight.trace.reduce((a, s) => a + s.time, 0) * 10) / 10,
            tokens: 4800 + Math.round(insight.relevance * 1700),
            models: 'GLM-5.3 + Qwen3.6',
            features: insight.features,
            insight,
        };
        return delay(trace);
    },
};
