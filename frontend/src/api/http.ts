import type { Api } from './types';
import { toFeed, toInsight, toTrace } from './adapters/interpretation';

/**
 * HTTP-клиент по контракту docs/openapi.yaml.
 * Инсайты бэкенд может отдавать в insight.v1 или в формате «ВЫХОД» — адаптер приводит всё к insight.v1.
 */
export function createHttpApi(baseUrl: string): Api {
    const base = baseUrl.replace(/\/$/, '');

    async function request<T>(path: string, init?: RequestInit): Promise<T> {
        const res = await fetch(`${base}${path}`, {
            ...init,
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
        });
        if (!res.ok) {
            const text = await res.text().catch(() => '');
            throw new Error(`API ${res.status}: ${text || res.statusText}`);
        }
        return res.json() as Promise<T>;
    }

    const qs = (params: Record<string, string>) => new URLSearchParams(params).toString();

    return {
        getCompanies: () => request('/companies'),
        getFeed: async (companyId, role) => toFeed(await request(`/feed?${qs({ company_id: companyId, role })}`), companyId, role),
        getEvent: async (eventId, companyId, role) =>
            toInsight(await request(`/events/${encodeURIComponent(eventId)}?${qs({ company_id: companyId, role })}`)),
        chat: (req) => request('/chat', { method: 'POST', body: JSON.stringify(req) }),
        getTrace: async (runId) => toTrace(await request(`/trace/${encodeURIComponent(runId)}`)),
    };
}
