import { useNavigate } from 'react-router-dom';
import { Button } from '@alfalab/core-components-button';
import { api } from '../api';
import { useApp } from '../context/AppContext';
import { useAsync } from '../context/useAsync';
import { Icon } from '../components/Icon';
import { Panel } from '../components/Panel';
import { ImpactTag, Tag } from '../components/Tag';
import { plural } from '../utils/format';

const MARKET = [
    ['Ключевая ставка', '14,00%'],
    ['USD/RUB ЦБ', '92,41'],
    ['CNY/RUB ЦБ', '12,87'],
    ['Brent', '$71,8'],
];

export function HomePage() {
    const { company, role } = useApp();
    const navigate = useNavigate();
    const feed = useAsync(() => (company ? api.getFeed(company.id, role) : null), [company?.id, role]);
    if (!company) return null;

    const top = feed.data?.items.slice(0, 3) ?? [];
    const total = feed.data?.items.length ?? 0;
    const askQuestion = top[0]?.suggested_questions[0];

    return (
        <div className="page">
            <h1 className="h-medium">Добрый день, {company.user_name}</h1>
            <div className="columns">
                <div className="columns__main">
                    <div className="accounts">
                        {company.accounts.map((a) => (
                            <div className="account" key={a.title}>
                                <span className="text-secondary-13">{a.title}</span>
                                <span className="account__amount">{a.amount}</span>
                                <span className="text-tertiary-12">{a.note}</span>
                            </div>
                        ))}
                    </div>

                    <section className="entry" aria-label="Новости и аналитика">
                        <div className="entry__head">
                            <div className="entry__titles">
                                <Tag color="red">Новое · AI-аналитика</Tag>
                                <h2 className="entry__title">Что сегодня важно для {company.short}</h2>
                                <p className="entry__lead">
                                    {feed.loading && !feed.data
                                        ? 'Агент подбирает события для вашей компании…'
                                        : `${total} ${plural(total, 'событие может', 'события могут', 'событий могут')} повлиять на ваш бизнес: ${leadTopics(top.map((t) => t.topics).flat())}. С оценкой экспертов Альфа-Банка.`}
                                </p>
                            </div>
                            <Button view="accent" size={56} onClick={() => navigate('/news')}>
                                Открыть ленту
                            </Button>
                        </div>
                        <div className="entry__events">
                            {top.map((i) => (
                                <button key={i.event_id} type="button" className="entry-event" onClick={() => navigate(`/news/${i.event_id}`)}>
                                    <ImpactTag impact={i.impact} />
                                    <span className="entry-event__text">
                                        <span className="entry-event__title">{shortTitle(i.title)}</span>
                                        <span className="entry-event__why">Почему вам: {i.why_you}</span>
                                    </span>
                                    <Icon name="chevronRightInverted" size={20} />
                                </button>
                            ))}
                        </div>
                    </section>

                    <Panel title="Последние операции" className="panel_l">
                        {company.operations.map((o) => (
                            <div className="row" key={o.title}>
                                <span className="row__label text-primary-14">{o.title}</span>
                                <span className={`row__value${o.incoming ? ' text-positive' : ''}`}>{o.amount}</span>
                            </div>
                        ))}
                    </Panel>
                </div>

                <div className="columns__side">
                    <Panel title="На подпись">
                        {company.tasks.map((t) => (
                            <p className="text-secondary-14" key={t}>
                                {t}
                            </p>
                        ))}
                        <div>
                            <Button view="primary" size={48}>
                                Подписать
                            </Button>
                        </div>
                    </Panel>
                    <Panel title="Спросите аналитика">
                        <p className="text-secondary-14">«{askQuestion ?? 'Как последние решения ЦБ повлияют на мой бизнес?'}»</p>
                        <div>
                            <Button
                                view="secondary"
                                size={48}
                                onClick={() =>
                                    navigate(
                                        `/chat?${new URLSearchParams({ ...(top[0] ? { event: top[0].event_id } : {}), ...(askQuestion ? { q: askQuestion } : {}) })}`,
                                    )
                                }
                            >
                                Задать вопрос
                            </Button>
                        </div>
                    </Panel>
                    <Panel title="Рынок">
                        {MARKET.map(([k, v]) => (
                            <div className="row" key={k}>
                                <span className="row__label text-secondary-14">{k}</span>
                                <span className="row__value">{v}</span>
                            </div>
                        ))}
                    </Panel>
                </div>
            </div>
        </div>
    );
}

const TOPIC_PHRASE: Record<string, string> = {
    rates: 'стоимость кредита',
    fx: 'валютный курс',
    commodities: 'цены на сырьё и маржа',
    counterparty: 'контрагенты',
    regulation: 'регулирование',
    trade: 'ВЭД',
};

function leadTopics(topics: string[]) {
    const uniq = [...new Set(topics)].map((t) => TOPIC_PHRASE[t]).filter(Boolean);
    return uniq.slice(0, 3).join(', ') || 'рынок';
}

/** Короткий заголовок для точки входа: до двоеточия или тире */
function shortTitle(title: string) {
    return title.split(/: | — /)[0];
}
