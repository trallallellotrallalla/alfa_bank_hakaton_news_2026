import { useApp } from '../context/AppContext';
import { ROLE_LABEL, type Role } from '../types/insight';
import { capitalize } from '../utils/format';
import { Dropdown } from './Dropdown';
import { Icon } from './Icon';

const ROLES = Object.keys(ROLE_LABEL) as Role[];

export function Topbar() {
    const { companies, company, role, setCompanyId, setRole } = useApp();
    if (!company) return <header className="topbar" />;
    return (
        <header className="topbar">
            <Dropdown
                label="Выбор компании"
                trigger={
                    <span className="company">
                        <span className="company__avatar">{company.initials}</span>
                        <span className="company__names">
                            <span className="company__name">
                                {company.name} · {company.id}
                            </span>
                            <span className="company__meta">
                                {capitalize(company.okved_title)} (ОКВЭД {company.okved}) · выручка {company.revenue}
                            </span>
                        </span>
                        <Icon name="chevronDown" size={16} className="chevron-down" />
                    </span>
                }
            >
                {(close) => (
                    <>
                        <div className="dropdown__title">Компании, доступные вам</div>
                        {companies.map((c) => (
                            <button
                                key={c.id}
                                type="button"
                                role="option"
                                aria-selected={c.id === company.id}
                                className={`dropdown__item${c.id === company.id ? ' dropdown__item_active' : ''}`}
                                onClick={() => {
                                    setCompanyId(c.id);
                                    close();
                                }}
                            >
                                <span className="company__avatar company__avatar_s">{c.initials}</span>
                                <span className="company__names">
                                    <span className="company__name">
                                        {c.name} · {c.id}
                                    </span>
                                    <span className="company__meta">
                                        ОКВЭД {c.okved} · {c.region} · группа {c.group_id}
                                    </span>
                                </span>
                            </button>
                        ))}
                    </>
                )}
            </Dropdown>
            <div className="topbar__spacer" />
            <Dropdown
                label="Выбор роли"
                trigger={
                    <span className="role-chip">
                        Роль: {ROLE_LABEL[role]}
                        <Icon name="chevronDown" size={14} className="chevron-down" />
                    </span>
                }
            >
                {(close) => (
                    <>
                        <div className="dropdown__title">Роль влияет на ранжирование и действия</div>
                        {ROLES.map((r) => (
                            <button
                                key={r}
                                type="button"
                                role="option"
                                aria-selected={r === role}
                                className={`dropdown__item${r === role ? ' dropdown__item_active' : ''}`}
                                onClick={() => {
                                    setRole(r);
                                    close();
                                }}
                            >
                                {capitalize(ROLE_LABEL[r])}
                            </button>
                        ))}
                    </>
                )}
            </Dropdown>
            <button type="button" className="icon-button" aria-label="Поиск">
                <Icon name="search" />
            </button>
            <button type="button" className="icon-button" aria-label="Уведомления">
                <Icon name="bell" />
            </button>
            <span className="user-avatar">{company.user_initials}</span>
        </header>
    );
}
