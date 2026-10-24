import type { ChatAnswer, ChatRequest, Company, FeedResponse, Insight, Role, TraceResponse } from '../types/insight';

/** Единый интерфейс API — реализуется моками и HTTP-клиентом (docs/openapi.yaml) */
export interface Api {
    getCompanies(): Promise<Company[]>;
    /** GET /feed?company_id=&role= */
    getFeed(companyId: string, role: Role): Promise<FeedResponse>;
    /** GET /events/:id?company_id=&role= */
    getEvent(eventId: string, companyId: string, role: Role): Promise<Insight>;
    /** POST /chat */
    chat(req: ChatRequest): Promise<ChatAnswer>;
    /** GET /trace/:run_id */
    getTrace(runId: string): Promise<TraceResponse>;
}
