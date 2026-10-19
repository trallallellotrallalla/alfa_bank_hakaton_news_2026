import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@alfalab/core-components-button';
import { api } from '../api';
import { useApp } from '../context/AppContext';
import { useAsync } from '../context/useAsync';
import { Icon } from '../components/Icon';
import { ErrorBox, Loading, Panel } from '../components/Panel';
import { ImpactTag, OriginTag } from '../components/Tag';
import { ProfileModal } from '../components/ProfileModal';
import type { Insight } from '../types/insight';
import { ROLE_LABEL } from '../types/insight';
import { formatShortDate, pct, plural } from '../utils/format';

type FilterId = 'all' | 'risk' | 'opportunity' | 'bank' | 'counterparty' | 'rates_fx';

const FILTERS: { id: FilterId; label: string; test: (i: Insight) => boolean }[] = [
    { id: 'all', label: 'Все', test: () => true },
    { id: 'risk', label: 'Риски', test: (i) => i.impact === 'risk' },
    { id: 'opportunity', label: 'Возможности', test: (i) => i.impact === 'opportunity' },
    { id: 'bank', label: 'Позиция банка', test: (i) => i.bank_view.length > 0 },
    { id: 'counterparty', label: 'Контрагенты', test: (i) => i.topics.includes('counterparty') },
    { id: 'rates_fx', label: 'Ставки и валюта', test: (i) => i.topics.includes('rates') || i.topics.includes('fx') },
];

export function FeedPage() {
    const { company, role, prefs } = useApp();
    const navigate = useNavigate();
    const [filter, setFilter] = useState<FilterId>('all');
    const [profileOpen, setProfileOpen] = useState(false);
    const feed = useAsync(() => (company ? api.getFeed(company.id, role) : null), [company?.id, role]);

    // Уточнения профиля сужают ленту на клиенте; на бэкенде те же поля уходят в /feed
    const items = useMemo(
        () =>
            (feed.data?.items ?? []).filter(
                (i) => i.topics.some((t) => prefs.topics.includes(t)) && (!prefs.onlyBankView || i.bank_view.length > 0),
            ),
        [feed.data, prefs],
    );
    const visible = items.filter(FILTERS.find((f) => f.id === filter)!.test);

    if (!company) return null;
    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <h1 className="h-medium">Новости и аналитика</h1>
                    <p className="text-secondary-14">
                        Подобрано для {company.name} по {company.features_count} признакам компании и роли «{ROLE_LABEL[role]}» · обновлено{' '}
                        {feed.data ? formatShortDate(feed.data.updated_at) : '…'}
                    </p>
                </div>
                <Button view="primary" size={48} onClick={() => navigate('/chat')}>
                    Спросить AI-аналитика
                </Button>
            </div>

            <div className="chips" role="tablist" aria-label="Фильтры ленты">
                {FILTERS.map((f) => {
                    const count = items.filter(f.test).length;
                    return (
                        <button
                            key={f.id}
                            type="button"
                            role="tab"
                            aria-selected={filter === f.id}
                            className={`chip${filter === f.id ? ' chip_active' : ''}`}
                            onClick={() => setFilter(f.id)}
                        >
                            {f.label} · {count}
                        </button>
                    );
                })}
            </div>

            <div className="columns">
                <div className="columns__main feed">
                    {feed.error && <ErrorBox error={feed.error} />}
                    {feed.loading && !feed.data && <Loading text="Агент подбирает события для вашей компании…" />}
                    <div className={`feed__list${feed.loading && feed.data ? ' feed__list_updating' : ''}`}>
                        {visible.map((i) => (
                            <NewsCard key={i.event_id} insight={i} onOpen={() => navigate(`/news/${i.event_id}`)} />
                        ))}
                        {feed.data && !visible.length && (
                            <div className="panel empty">По выбранному фильтру событий нет. Попробуйте другой фильтр или уточните профиль.</div>
                        )}
                    </div>
                </div>

                <div className="columns__side">
                    <Panel title="Профиль компании">
                        <p className="text-secondary-13">Признаки, по которым отбираются и интерпретируются события</p>
                        <Feature label="Отрасль" value={`ОКВЭД ${company.okved} · ${company.okved_title}`} />
                        <Feature label="Масштаб" value={`Выручка ${company.revenue} · ${company.staff}`} />
                        <Feature label="Продукты в Альфа-Банке" value={capFirst(company.products.join(', '))} />
                        <Feature label="ВЭД" value={company.foreign_trade} />
                        <Feature label="Регион" value={company.region} />
                        <Feature label="Группа компаний" value={`${company.group_id} · ${company.group_size} ${plural(company.group_size, 'юрлицо', 'юрлица', 'юрлиц')}`} />
                        <Feature label="Ключевые контрагенты" value={company.top_counterparties} />
                        <div>
                            <Button view="secondary" size={48} onClick={() => setProfileOpen(true)}>
                                Уточнить профиль
                            </Button>
                        </div>
                    </Panel>
                    <Panel title="Как устроен отбор">
                        <p className="text-secondary-13">
                            Новости и материалы Центра макроэкономических исследований Альфа-Банка сопоставляются с признаками компании и
                            ролью пользователя. Метка «Позиция банка» — вывод опирается на аналитику банка. События с релевантностью ниже 50% в
                            ленту не попадают.
                        </p>
                    </Panel>
                </div>
            </div>
            {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
        </div>
    );
}

function NewsCard({ insight: i, onOpen }: { insight: Insight; onOpen: () => void }) {
    const publishers = [...new Set(i.sources.map((s) => s.publisher))];
    return (
        <article
            className="news-card"
            tabIndex={0}
            role="link"
            onClick={onOpen}
            onKeyDown={(e) => e.key === 'Enter' && onOpen()}
            aria-label={i.title}
        >
            <div className="news-card__top">
                <ImpactTag impact={i.impact} />
                {i.bank_view.length > 0 && <OriginTag origin="bank" />}
                <span className="news-card__spacer" />
                <span className="text-secondary-13 medium">Релевантность {pct(i.relevance)}</span>
            </div>
            <h3 className="news-card__title">{i.title}</h3>
            <p className="text-secondary-14">{i.summary}</p>
            <div className="why">
                <Icon name="sparkle" size={16} />
                <span>Почему вам: {i.why_you}</span>
            </div>
            <p className="text-tertiary-12">
                {publishers.length} {plural(publishers.length, 'источник', 'источника', 'источников')} ·{' '}
                {publishers.join(', ')} · {formatShortDate(i.published_at)}
            </p>
        </article>
    );
}

function Feature({ label, value }: { label: string; value: string }) {
    return (
        <div className="feature">
            <span className="text-tertiary-12">{label}</span>
            <span className="text-primary-14">{value}</span>
        </div>
    );
}

const capFirst = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
