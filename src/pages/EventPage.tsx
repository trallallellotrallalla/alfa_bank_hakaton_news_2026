import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button } from '@alfalab/core-components-button';
import { Input } from '@alfalab/core-components-input';
import { api } from '../api';
import { useApp } from '../context/AppContext';
import { useAsync } from '../context/useAsync';
import { Icon } from '../components/Icon';
import { ErrorBox, Loading, Panel } from '../components/Panel';
import { ImpactTag, OriginTag } from '../components/Tag';
import type { Insight, Origin } from '../types/insight';
import { ROLE_LABEL } from '../types/insight';
import { formatDate, pct, plural, sec } from '../utils/format';

export function EventPage() {
    const { eventId = '' } = useParams();
    const { company, role } = useApp();
    const navigate = useNavigate();
    const [question, setQuestion] = useState('');
    const state = useAsync(() => (company ? api.getEvent(eventId, company.id, role) : null), [eventId, company?.id, role]);

    const ask = (q: string) => q.trim() && navigate(`/chat?${new URLSearchParams({ event: eventId, q: q.trim() })}`);

    if (state.error)
        return (
            <div className="page">
                <Breadcrumbs />
                <ErrorBox error={state.error} />
                <div>
                    <Button view="secondary" size={48} onClick={() => navigate('/news')}>
                        К ленте выбранной компании
                    </Button>
                </div>
            </div>
        );
    if (!state.data) return <Loading />;
    const i = state.data;

    return (
        <div className="page page_tight">
            <Breadcrumbs />
            <section className="panel event-header">
                <div className="badges">
                    <ImpactTag impact={i.impact} />
                    {i.bank_view.length > 0 && <OriginTag origin="bank" />}
                    <span className="text-secondary-13">
                        Релевантность {pct(i.relevance)} · {formatDate(i.published_at)}
                    </span>
                </div>
                <h1 className="h-medium">{i.title}</h1>
                <div className="badges legend">
                    <span className="text-tertiary-13">Обозначения:</span>
                    <OriginTag origin="fact" label="Факт из источника" />
                    <OriginTag origin="bank" label="Позиция Альфа-Банка" />
                    <OriginTag origin="ai" label="Вывод AI" />
                </div>
            </section>

            <div className="columns">
                <div className="columns__main">
                    <div className="insight-grid">
                        <InsightBlock n={1} title="Что произошло?" origin="fact" footer={`Источник: ${sourceNames(i, i.facts.flatMap((f) => f.src))}`}>
                            {i.facts.map((f) => (
                                <p key={f.text}>{f.text}</p>
                            ))}
                        </InsightBlock>

                        <InsightBlock n={2} title="Почему это важно для компании?" origin="ai" footer={`Признаки: ${featureNames(i, 'why_relevant')}`}>
                            {i.ai_inference
                                .filter((x) => x.kind === 'why_relevant')
                                .map((x) => (
                                    <p key={x.text}>{x.text}</p>
                                ))}
                        </InsightBlock>

                        <InsightBlock n={3} title="Какие последствия возможны?" origin="ai" footer={consequenceFooter(i)}>
                            {i.ai_inference
                                .filter((x) => x.kind !== 'why_relevant')
                                .map((x) => (
                                    <p key={x.text}>
                                        <b>{x.kind === 'consequence_risk' ? 'Риск' : 'Возможность'}:</b> {x.text}
                                    </p>
                                ))}
                        </InsightBlock>

                        <InsightBlock
                            n={4}
                            title="Как это оценивает банк?"
                            origin="bank"
                            footer={i.bank_view.length ? `Источник: ${sourceNames(i, i.bank_view.flatMap((b) => b.src), true)}` : 'Источник: аналитика Альфа-Банка по теме не найдена'}
                        >
                            {i.bank_view.length ? (
                                i.bank_view.map((b) => <p key={b.text}>{b.text}</p>)
                            ) : (
                                <p className="text-secondary-14">
                                    У Альфа-Банка нет опубликованной позиции по этой теме. Блок намеренно пуст, чтобы не выдавать вывод AI за мнение
                                    банка.
                                </p>
                            )}
                        </InsightBlock>

                        <InsightBlock n={5} title="Какие действия могут быть релевантны?" origin="ai" footer={`Для роли «${ROLE_LABEL[role]}» · следующий шаг — расчёт с менеджером банка`}>
                            <ul className="actions">
                                {i.actions.map((a) => (
                                    <li key={a.id} className={a.roles?.includes(role) ? 'actions__item_role' : undefined}>
                                        {a.text}
                                    </li>
                                ))}
                            </ul>
                        </InsightBlock>

                        <InsightBlock
                            n={6}
                            title="На чём основан вывод?"
                            origin="trace"
                            footer={
                                <Link to={`/news/${i.event_id}/trace`} className="link">
                                    Агент: {agentSummary(i)} →
                                </Link>
                            }
                        >
                            <p>{i.basis}</p>
                        </InsightBlock>
                    </div>

                    <section className="panel bank-offer">
                        <div className="bank-offer__text">
                            <span className="caps">{i.bank_offer?.title ?? 'Следующий шаг'}</span>
                            <p className="text-primary-14">
                                {i.bank_offer?.text ?? 'Обсудите событие с AI-аналитиком или откройте трассу, чтобы проверить, как агент пришёл к выводу.'}
                            </p>
                        </div>
                        <Button view="accent" size={48} onClick={() => ask(i.suggested_questions[0])}>
                            Рассчитать
                        </Button>
                        <Button view="outlined" size={48} onClick={() => navigate(`/news/${i.event_id}/trace`)}>
                            Трасса вывода
                        </Button>
                    </section>
                </div>

                <div className="columns__side">
                    <Panel title="Спросить про событие">
                        {i.suggested_questions.map((q) => (
                            <button key={q} type="button" className="suggestion" onClick={() => ask(q)}>
                                {q}
                            </button>
                        ))}
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                ask(question);
                            }}
                        >
                            <Input
                                block
                                size={56}
                                label="Ваш вопрос"
                                labelView="inner"
                                value={question}
                                onChange={(e) => setQuestion(e.target.value)}
                            />
                        </form>
                    </Panel>
                    <Panel title="Первоисточники">
                        {i.sources.map((s) => {
                            const body = (
                                <>
                                    <Icon name="link" size={18} />
                                    <span className="source__text">
                                        <span className="text-tertiary-12">{s.publisher}</span>
                                        <span className="source__title">{s.title}</span>
                                    </span>
                                </>
                            );
                            // Без URL (бэкенд передал только id) — показываем источник, но не делаем его ссылкой
                            return s.url ? (
                                <a key={s.id} className="source" href={s.url} target="_blank" rel="noreferrer">
                                    {body}
                                </a>
                            ) : (
                                <div key={s.id} className="source source_nolink" title={s.id}>
                                    {body}
                                </div>
                            );
                        })}
                    </Panel>
                </div>
            </div>
        </div>
    );
}

function Breadcrumbs() {
    return (
        <nav className="breadcrumbs" aria-label="Навигация">
            <Link to="/news">← Новости и аналитика</Link>
            <span>/</span>
            <span>Событие</span>
        </nav>
    );
}

function InsightBlock({ n, title, origin, footer, children }: { n: number; title: string; origin: Origin | 'trace'; footer: ReactNode; children: ReactNode }) {
    return (
        <section className={`panel insight-block insight-block_${origin}`}>
            <div className="insight-block__head">
                <span className="insight-block__num">{n}</span>
                <h2 className="insight-block__title">{title}</h2>
                <OriginTag origin={origin} />
            </div>
            <div className="insight-block__body">{children}</div>
            <div className="text-tertiary-12">{footer}</div>
        </section>
    );
}

function sourceNames(i: Insight, ids: string[], titles = false) {
    return [...new Set(ids)]
        .map((id) => i.sources.find((s) => s.id === id))
        .filter(Boolean)
        .map((s) => (titles ? `«${s!.title}»` : s!.publisher))
        .join(' · ');
}

function featureNames(i: Insight, kind: string) {
    const codes = new Set(i.ai_inference.filter((x) => x.kind === kind).flatMap((x) => x.features));
    const labels = i.features.filter((f) => codes.has(f.code)).map((f) => f.label);
    return (labels.length ? labels : [...codes]).join(' · ');
}

function agentSummary(i: Insight) {
    const steps = i.trace.length;
    const retries = i.trace.filter((s) => s.state === 'retry').length;
    const total = i.trace.reduce((a, s) => a + s.time, 0);
    return [
        `${steps} ${plural(steps, 'шаг', 'шага', 'шагов')}`,
        retries ? `${retries} ${plural(retries, 'повторный поиск', 'повторных поиска', 'повторных поисков')}` : 'без повторных поисков',
        ...(total ? [sec(total)] : []),
    ].join(' · ');
}

function consequenceFooter(i: Insight) {
    const calc = i.trace.find((s) => s.title.includes('Расчёт'))?.tool;
    return calc ? `Источник: расчёт по данным профиля · ${calc}` : `Признаки: ${featureNames(i, 'consequence_risk') || featureNames(i, 'consequence_opportunity')}`;
}
