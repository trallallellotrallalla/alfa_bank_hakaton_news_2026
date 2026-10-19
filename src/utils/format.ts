export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function formatDate(iso: string, withTime = true) {
    return new Date(iso).toLocaleString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
        timeZone: 'Europe/Moscow',
    });
}

export function formatShortDate(iso: string) {
    return new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' });
}

export const sec = (x: number) => `${x.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;

export function plural(n: number, one: string, few: string, many: string) {
    const m10 = n % 10;
    const m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
}
