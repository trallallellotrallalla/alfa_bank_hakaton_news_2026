import type { ReactNode } from 'react';

export function Panel({ title, children, className = '' }: { title?: ReactNode; children: ReactNode; className?: string }) {
    return (
        <section className={`panel ${className}`}>
            {title && <h2 className="panel__title">{title}</h2>}
            {children}
        </section>
    );
}

export function Loading({ text = 'Агент готовит данные…' }: { text?: string }) {
    return <div className="loading">{text}</div>;
}

export function ErrorBox({ error }: { error: Error }) {
    return <div className="error-box">Не удалось загрузить данные: {error.message}</div>;
}
