export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function formatDate(iso: string, withTime = true) {
    // Дата без времени (из бэкенда приходит «2026-09-11») — время не показываем
    if (/T00:00:00(\+03:00)?$/.test(iso)) withTime = false;
    return new Date(iso).toLocaleString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
        timeZone: 'Europe/Moscow',
    });
}

export function formatShortDate(iso: string) {
    const dateOnly = /T00:00:00(\+03:00)?$/.test(iso);
    return new Date(iso).toLocaleString('ru-RU', {
        day: 'numeric',
        month: 'short',
        ...(dateOnly ? {} : { hour: '2-digit', minute: '2-digit' }),
        timeZone: 'Europe/Moscow',
    });
}

export const sec = (x: number) => `${x.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;

export function plural(n: number, one: string, few: string, many: string) {
    const m10 = n % 10;
    const m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
}
