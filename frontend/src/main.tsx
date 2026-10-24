import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

// Токены core-ds: палитра bluetint, радиусы, отступы, системный шрифт
import '@alfalab/core-components-vars/colors-bluetint.css';
import '@alfalab/core-components-vars/border-radius.css';
import '@alfalab/core-components-vars/gaps.css';
import '@alfalab/core-components-vars/typography-vars.css';
import '@alfalab/core-components-vars/common.css';
import './styles/app.css';

import { AppProvider } from './context/AppContext';
import { Layout } from './components/Layout';
import { HomePage } from './pages/HomePage';
import { FeedPage } from './pages/FeedPage';
import { EventPage } from './pages/EventPage';
import { ChatPage } from './pages/ChatPage';
import { TracePage } from './pages/TracePage';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <AppProvider>
            <BrowserRouter>
                <Routes>
                    <Route element={<Layout />}>
                        <Route index element={<HomePage />} />
                        <Route path="news" element={<FeedPage />} />
                        <Route path="news/:eventId" element={<EventPage />} />
                        <Route path="news/:eventId/trace" element={<TracePage />} />
                        <Route path="chat" element={<ChatPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Route>
                </Routes>
            </BrowserRouter>
        </AppProvider>
    </StrictMode>,
);
