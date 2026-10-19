import type { Api } from './types';

/** HTTP-клиент по контракту docs/openapi.yaml */
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
        getFeed: (companyId, role) => request(`/feed?${qs({ company_id: companyId, role })}`),
        getEvent: (eventId, companyId, role) =>
            request(`/events/${encodeURIComponent(eventId)}?${qs({ company_id: companyId, role })}`),
        chat: (req) => request('/chat', { method: 'POST', body: JSON.stringify(req) }),
        getTrace: (runId) => request(`/trace/${encodeURIComponent(runId)}`),
    };
}
