import { NavLink, useLocation } from 'react-router-dom';
import { Icon, type IconName } from './Icon';

const STUB: { label: string; icon: IconName }[] = [
    { label: 'Счета', icon: 'navAccounts' },
    { label: 'Платежи', icon: 'navPayments' },
    { label: 'Кредиты и гарантии', icon: 'navCredits' },
    { label: 'Документы', icon: 'navDocs' },
];

export function Sidebar() {
    const { pathname } = useLocation();
    const newsActive = pathname.startsWith('/news') || pathname.startsWith('/chat');
    return (
        <aside className="sidebar">
            <NavLink to="/" className="sidebar__logo" aria-label="Альфа-Бизнес, главная">
                <span className="sidebar__mark">A</span>
                <span className="sidebar__brand">Бизнес</span>
            </NavLink>
            <nav className="sidebar__nav">
                <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? ' nav-item_active' : ''}`}>
                    <Icon name="home" />
                    <span>Главная</span>
                </NavLink>
                {STUB.map((i) => (
                    <button key={i.label} type="button" className="nav-item" title="Не входит в прототип">
                        <Icon name={i.icon} />
                        <span>{i.label}</span>
                    </button>
                ))}
                <NavLink to="/news" className={`nav-item${newsActive ? ' nav-item_active' : ''}`}>
                    <Icon name="navNews" />
                    <span>Новости и аналитика</span>
                </NavLink>
                <button type="button" className="nav-item" title="Не входит в прототип">
                    <Icon name="navReports" />
                    <span>Отчёты</span>
                </button>
            </nav>
            <div className="sidebar__spacer" />
            <button type="button" className="nav-item" title="Не входит в прототип">
                <Icon name="navSettings" />
                <span>Настройки</span>
            </button>
        </aside>
    );
}
