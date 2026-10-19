import { useEffect, useState, type DependencyList } from 'react';

/** Загрузка данных с отменой устаревших ответов (важно при быстрой смене компании) */
export function useAsync<T>(fn: () => Promise<T> | null, deps: DependencyList) {
    const [state, setState] = useState<{ data?: T; error?: Error; loading: boolean }>({ loading: true });
    useEffect(() => {
        let alive = true;
        const p = fn();
        if (!p) return;
        setState((s) => ({ data: s.data, loading: true }));
        p.then(
            (data) => alive && setState({ data, loading: false }),
            (error: Error) => alive && setState({ error, loading: false }),
        );
        return () => {
            alive = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
    return state;
}
