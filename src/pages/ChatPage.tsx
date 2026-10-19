import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@alfalab/core-components-button';
import { api } from '../api';
import { useApp } from '../context/AppContext';
import { useAsync } from '../context/useAsync';
import { Icon } from '../components/Icon';
import { Panel } from '../components/Panel';
import { ImpactTag, OriginTag } from '../components/Tag';
import { THINKING_STEPS } from '../mocks/chat';
import type { ChatAnswer, ChatMessage, Insight } from '../types/insight';

let seq = 0;
const nextId = () => `m${++seq}`;

export function ChatPage() {
    const { company, role } = useApp();
    const navigate = useNavigate();
    const [params, setParams] = useSearchParams();
    const feed = useAsync(() => (company ? api.getFeed(company.id, role) : null), [company?.id, role]);

    const eventId = params.get('event');
    const insight: Insight | undefined = feed.data?.items.find((i) => i.event_id === eventId) ?? feed.data?.items[0];

    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState('');
    const [pending, setPending] = useState(false);
    const [step, setStep] = useState(0);
    const threadRef = useRef<HTMLDivElement>(null);
    const autoAsked = useRef<string | null>(null);

    // Новый контекст (другая компания или событие) — новый диалог
    useEffect(() => {
        setMessages([]);
    }, [company?.id, insight?.event_id]);

    useEffect(() => {
        threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages, pending]);

    // «Агент думает»: показываем шаги, пока ждём ответа
    useEffect(() => {
        if (!pending) return;
        setStep(0);
        const t = setInterval(() => setStep((s) => Math.min(s + 1, THINKING_STEPS.length - 1)), 520);
        return () => clearInterval(t);
    }, [pending]);

    async function send(text: string) {
        const q = text.trim();
        if (!q || !company || !insight || pending) return;
        const userMsg: ChatMessage = { id: nextId(), role: 'user', text: q };
        const history = [...messages, userMsg];
        setMessages(history);
        setDraft('');
        setPending(true);
        try {
            const answer = await api.chat({
                company_id: company.id,
                role,
                event_id: insight.event_id,
                messages: history.map((m) => ({ role: m.role, content: m.text ?? m.answer?.paragraphs.join('\n') ?? '' })),
            });
            setMessages((ms) => [...ms, { id: nextId(), role: 'assistant', answer }]);
        } catch (e) {
            setMessages((ms) => [
                ...ms,
                { id: nextId(), role: 'assistant', answer: { origins: ['ai'], paragraphs: [`Не удалось получить ответ: ${(e as Error).message}`], citations: [] } },
            ]);
        } finally {
            setPending(false);
        }
    }

    // Вопрос, пришедший из карточки события или с главной (?q=…)
    useEffect(() => {
        const q = params.get('q');
        if (!q || !insight || autoAsked.current === q) return;
        autoAsked.current = q;
        params.delete('q');
        setParams(params, { replace: true });
        void send(q);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [insight]);

    if (!company) return null;
    const why = insight?.ai_inference.find((x) => x.kind === 'why_relevant');

    return (
        <div className="chat-layout">
            <div className="chat">
                <div className="chat__header">
                    <div>
                        <h1 className="h-small">AI-аналитик</h1>
                        <p className="text-secondary-13">
                            Контекст: {insight ? `«${insight.title}»` : '…'} · {company.name}
                        </p>
                    </div>
                    <Button view="secondary" size={40} onClick={() => setMessages([])} disabled={pending || !messages.length}>
                        Новый диалог
                    </Button>
                </div>

                <div className="chat__thread" ref={threadRef}>
                    {!messages.length && insight && (
                        <div className="chat__empty">
                            <Icon name="sparkle" size={24} />
                            <p className="text-primary-14">
                                Задайте вопрос о событии. Агент опирается на профиль {company.short}, первоисточники и аналитику Альфа-Банка, а
                                в ответе разделяет факты, позицию банка и собственные выводы.
                            </p>
                            <div className="slices">
                                {insight.suggested_questions.map((q) => (
                                    <button key={q} type="button" className="chip chip_soft" onClick={() => send(q)}>
                                        {q}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                    {messages.map((m) =>
                        m.role === 'user' ? (
                            <div className="user-row" key={m.id}>
                                <div className="user-message">{m.text}</div>
                            </div>
                        ) : (
                            <AiAnswer
                                key={m.id}
                                answer={m.answer!}
                                insight={insight}
                                onAsk={send}
                                onTrace={() => insight && navigate(`/news/${insight.event_id}/trace`)}
                            />
                        ),
                    )}
                    {pending && (
                        <div className="ai-typing" aria-live="polite">
                            <Icon name="sparkle" size={18} />
                            <span>
                                {THINKING_STEPS[step]} · шаг {step + 1} из {THINKING_STEPS.length}
                            </span>
                            <span className="dots" aria-hidden>
                                <i />
                                <i />
                                <i />
                            </span>
                        </div>
                    )}
                </div>

                <form
                    className="composer"
                    onSubmit={(e) => {
                        e.preventDefault();
                        void send(draft);
                    }}
                >
                    <input
                        className="composer__input"
                        placeholder="Спросите про событие, компанию или рынок…"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        aria-label="Вопрос AI-аналитику"
                    />
                    <Button type="submit" view="accent" size={48} disabled={!draft.trim() || pending}>
                        Отправить
                    </Button>
                </form>
            </div>

            <div className="chat-context">
                <Panel title="Контекст диалога">
                    {insight && (
                        <Link to={`/news/${insight.event_id}`} className="context-event">
                            <ImpactTag impact={insight.impact} />
                            <span className="text-primary-14 medium">{insight.title}</span>
                        </Link>
                    )}
                    <span className="text-tertiary-12">Признаки компании в ответе</span>
                    {insight?.features.map((f) => (
                        <p className="text-primary-14" key={f.code}>
                            • {f.label}
                        </p>
                    ))}
                    {why && <p className="text-secondary-13">{why.text}</p>}
                </Panel>
                <Panel
                    title={
                        <span className="title-with-icon">
                            <Icon name="shield" /> Данные под защитой
                        </span>
                    }
                >
                    <p className="text-secondary-13">
                        AI видит только данные выбранной компании и вашей роли. Все обращения к инструментам журналируются, AI не выполняет
                        платежи и операции.
                    </p>
                </Panel>
            </div>
        </div>
    );
}

function AiAnswer({
    answer,
    insight,
    onAsk,
    onTrace,
}: {
    answer: ChatAnswer;
    insight?: Insight;
    onAsk: (q: string) => void;
    onTrace: () => void;
}) {
    const firstSource = insight?.sources[0];
    return (
        <div className="ai-answer">
            <div className="badges">
                {answer.origins.includes('ai') && <OriginTag origin="ai" />}
                {answer.origins.includes('bank') && <OriginTag origin="bank" label={answer.origins.includes('ai') ? 'Опирается на позицию банка' : 'Позиция банка'} />}
            </div>
            {answer.paragraphs.slice(0, answer.table ? 1 : undefined).map((p) => (
                <p className="text-primary-14" key={p}>
                    {p}
                </p>
            ))}
            {answer.table && (
                <div className="scenarios" role="table">
                    <div className="scenarios__row scenarios__row_head" role="row">
                        {answer.table.columns.map((c) => (
                            <span key={c} role="columnheader">
                                {c}
                            </span>
                        ))}
                    </div>
                    {answer.table.rows.map((r) => (
                        <div className="scenarios__row" role="row" key={r[0]}>
                            {r.map((c, idx) => (
                                <span key={idx} role="cell">
                                    {c}
                                </span>
                            ))}
                        </div>
                    ))}
                </div>
            )}
            {answer.table &&
                answer.paragraphs.slice(1).map((p) => (
                    <p className="text-primary-14" key={p}>
                        {p}
                    </p>
                ))}
            {answer.clarify && (
                <div className="clarify">
                    <span className="text-primary-14 medium">{answer.clarify.question}</span>
                    <div className="slices">
                        {answer.clarify.options.map((o) => (
                            <button key={o} type="button" className="chip chip_soft" onClick={() => onAsk(o)}>
                                {o}
                            </button>
                        ))}
                    </div>
                </div>
            )}
            {answer.citations.length > 0 && (
                <div className="citations">
                    {answer.citations.map((c) => {
                        const src = insight?.sources.find((s) => s.id === c.source_id);
                        return src ? (
                            <a key={c.n} className="cite" href={src.url} target="_blank" rel="noreferrer">
                                [{c.n}] {c.label}
                            </a>
                        ) : (
                            <span key={c.n} className="cite">
                                [{c.n}] {c.label}
                            </span>
                        );
                    })}
                </div>
            )}
            {answer.slices && (
                <div className="slices">
                    <span className="text-secondary-13">Показать в другом разрезе:</span>
                    {answer.slices.map((s) => (
                        <button key={s} type="button" className="chip chip_soft" onClick={() => onAsk(s)}>
                            {s}
                        </button>
                    ))}
                </div>
            )}
            {!answer.clarify && (
                <div className="ai-answer__footer">
                    <button type="button" className="link-button" onClick={onTrace}>
                        Открыть трассу вывода
                    </button>
                    {firstSource && (
                        <a className="link-button" href={firstSource.url} target="_blank" rel="noreferrer">
                            Перейти к первоисточнику
                        </a>
                    )}
                </div>
            )}
        </div>
    );
}
