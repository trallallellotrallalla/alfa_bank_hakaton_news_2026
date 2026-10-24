import { Outlet } from 'react-router-dom';
import { API_MODE } from '../api';
import { useApp } from '../context/AppContext';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export function Layout() {
    const { company } = useApp();
    return (
        <div className="app">
            <Sidebar />
            <div className="main">
                <Topbar />
                <main className="content">{company ? <Outlet /> : <div className="loading">Загрузка…</div>}</main>
            </div>
            {API_MODE === 'mock' && <div className="mode-badge">Демо-данные · синтетические клиенты</div>}
        </div>
    );
}
