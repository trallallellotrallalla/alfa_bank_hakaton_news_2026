import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@alfalab/core-components-button';
import { api } from '../api';
import { useApp } from '../context/AppContext';
import { useAsync } from '../context/useAsync';
import { Icon } from '../components/Icon';
import { ErrorBox, Loading, Panel } from '../components/Panel';
import { Tag } from '../components/Tag';
import type { TraceStep } from '../types/insight';
import { sec } from '../utils/format';

const GUARDRAILS = [
    'Доступ к данным только выбранного клиента и роли',
    'Журнал всех вызовов инструментов',
    'Инструменты только на чтение — без платежей',
    'Персональные данные маскируются',
];

export function TracePage() {
    const { eventId = '' } = useParams();
    const { company, role } = useApp();
    const trace = useAsync(async () => {
        if (!company) return null;
        const insight = await api.getEvent(eventId, company.id, role);
        return api.getTrace(insight.run_id);
    }, [eventId, company?.id, role]);

    // Воспроизведение прогона: шаги появляются по очереди, текущий — в состоянии running
    const [shown, setShown] = useState(0);
    const total = trace.data?.steps.length ?? 0;
    useEffect(() => {
        if (!total) return;
        setShown(0);
        const t = setInterval(() => setShown((s) => (s >= total ? s : s + 1)), 350);
        return () => clearInterval(t);
    }, [total, trace.data?.run_id]);

    if (trace.error) return <ErrorBox error={trace.error} />;
    if (!trace.data) return <Loading text="Загружаем трассу агента…" />;
    const t = trace.data;
    const i = t.insight;

    const exportJson = () => {
        const blob = new Blob([JSON.stringify({ ...i, trace: t.steps }, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `insight.v1_${i.event_id}_${i.company_id}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
    };

    const preview = {
        event_id: i.event_id,
        relevance: i.relevance,
        impact: i.impact,
        facts: i.facts.map((f) => ({ text: '…', src: f.src })),
        bank_view: i.bank_view.map((b) => ({ text: '…', src: b.src })),
        ai_inference: i.ai_inference.map((x) => ({ text: '…', features: x.features })),
        actions: i.actions.map(() => '…'),
        confidence: i.confidence,
    };

    return (
        <div className="page page_tight">
            <nav className="breadcrumbs" aria-label="Навигация">
                <Link to={`/news/${i.event_id}`}>← Событие</Link>
                <span>/</span>
                <span>Трасса вывода</span>
            </nav>
            <div className="page-header">
                <div>
                    <h1 className="h-medium">Трасса вывода</h1>
                    <p className="text-secondary-14">
                        Как агент пришёл к инсайту «{i.title}» для {t.company_id} · run_id {t.run_id}
                    </p>
                </div>
                <Button view="outlined" size={48} onClick={exportJson}>
                    Экспорт JSON
                </Button>
            </div>

            <div className="metrics">
                <Metric label="Шагов" value={String(t.steps.length)} />
                <Metric label="Повторных поисков" value={String(t.retries)} />
                <Metric label="Время" value={t.duration_s ? sec(t.duration_s) : '—'} />
                <Metric label="Токены" value={t.tokens ? t.tokens.toLocaleString('ru-RU') : '—'} />
                <Metric label="Модели" value={t.models} />
            </div>

            <div className="columns">
                <div className="columns__main">
                    <Panel title="Шаги агента" className="steps panel_l">
                        {t.steps.slice(0, Math.min(shown + 1, total)).map((s, idx) => (
                            <AgentStep key={s.title} step={idx === shown && shown < total ? { ...s, state: 'running' } : s} />
                        ))}
                    </Panel>
                </div>
                <div className="columns__side columns__side_wide">
                    <Panel title="Признаки, повлиявшие на вывод">
                        {t.features.map((f) => (
                            <div className="feature-bar" key={f.code}>
                                <div className="row">
                                    <span className="row__label text-primary-14">{f.label}</span>
                                    <span className="text-secondary-14 medium">{f.weight.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}</span>
                                </div>
                                <div className="bar" title={f.code}>
                                    <div className="bar__fill" style={{ width: `${f.weight * 100}%` }} />
                                </div>
                            </div>
                        ))}
                    </Panel>
                    <Panel title={`Ответ агента (${i.schema})`}>
                        <pre className="code">{compactJson(preview)}</pre>
                    </Panel>
                    <Panel title="Контроль и безопасность">
                        {GUARDRAILS.map((g) => (
                            <div className="rule" key={g}>
                                <Tag color="green">✓</Tag>
                                <span className="text-primary-14">{g}</span>
                            </div>
                        ))}
                    </Panel>
                </div>
            </div>
        </div>
    );
}

function Metric({ label, value }: { label: string; value: string }) {
    return (
        <div className="metric">
            <span className="text-secondary-13">{label}</span>
            <span className="metric__value">{value}</span>
        </div>
    );
}

function AgentStep({ step }: { step: TraceStep }) {
    return (
        <div className={`agent-step agent-step_${step.state}`}>
            <span className="agent-step__dot">
                {step.state === 'running' ? <span className="spinner" /> : <Icon name={step.state === 'retry' ? 'stepRetry' : 'stepDone'} size={18} />}
            </span>
            <div className="agent-step__content">
                <div className="row">
                    <span className="row__label text-primary-14 medium">{step.title}</span>
                    <span className="text-tertiary-12">{step.state === 'running' ? 'выполняется…' : step.time ? sec(step.time) : ''}</span>
                </div>
                <span className="agent-step__tool">tool: {step.tool}</span>
                <span className="text-secondary-13">{step.detail}</span>
            </div>
        </div>
    );
}

/** Каждое поле верхнего уровня — в одну строку, как в макете */
function compactJson(obj: Record<string, unknown>) {
    const lines = Object.entries(obj).map(([k, v]) => `  "${k}": ${JSON.stringify(v).replace(/,"/g, ', "').replace(/":/g, '": ')}`);
    return ['{', lines.join(',\n'), '}'].join('\n');
}
