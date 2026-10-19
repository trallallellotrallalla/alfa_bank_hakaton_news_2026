import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../api';
import type { Company, Role, Topic } from '../types/insight';

/** Уточнения профиля, которые пользователь задаёт сам (кнопка «Уточнить профиль») */
export interface ProfilePrefs {
    topics: Topic[];
    onlyBankView: boolean;
}

export const ALL_TOPICS: Topic[] = ['rates', 'fx', 'commodities', 'counterparty', 'regulation', 'trade'];
const DEFAULT_PREFS: ProfilePrefs = { topics: ALL_TOPICS, onlyBankView: false };

interface AppState {
    companies: Company[];
    company: Company | null;
    role: Role;
    prefs: ProfilePrefs;
    setCompanyId(id: string): void;
    setRole(role: Role): void;
    setPrefs(prefs: ProfilePrefs): void;
}

const Ctx = createContext<AppState | null>(null);

const STORAGE_KEY = 'alfa-news-insight:v1';

function load(): { companyId?: string; role?: Role; prefs?: Record<string, ProfilePrefs> } {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    } catch {
        return {};
    }
}

export function AppProvider({ children }: { children: ReactNode }) {
    const saved = useMemo(load, []);
    const [companies, setCompanies] = useState<Company[]>([]);
    const [companyId, setCompanyId] = useState<string | undefined>(saved.companyId);
    const [role, setRole] = useState<Role>(saved.role ?? 'cfo');
    const [prefsByCompany, setPrefsByCompany] = useState<Record<string, ProfilePrefs>>(saved.prefs ?? {});

    useEffect(() => {
        api.getCompanies().then(setCompanies).catch(console.error);
    }, []);

    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({ companyId, role, prefs: prefsByCompany }));
        } catch {
            /* приватный режим — просто не сохраняем */
        }
    }, [companyId, role, prefsByCompany]);

    const company = companies.find((c) => c.id === companyId) ?? companies[0] ?? null;
    const prefs = (company && prefsByCompany[company.id]) || DEFAULT_PREFS;

    const setPrefs = useCallback(
        (p: ProfilePrefs) => company && setPrefsByCompany((all) => ({ ...all, [company.id]: p })),
        [company],
    );

    const value = useMemo(
        () => ({ companies, company, role, prefs, setCompanyId, setRole, setPrefs }),
        [companies, company, role, prefs, setPrefs],
    );
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
    const ctx = useContext(Ctx);
    if (!ctx) throw new Error('useApp вне AppProvider');
    return ctx;
}
