import type { Api } from './types';
import { mockApi } from './mock';
import { createHttpApi } from './http';

/**
 * Единственный флаг переключения: VITE_API_MODE = mock | http.
 * В режиме http запросы уходят на VITE_API_BASE_URL (по умолчанию /api).
 */
export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock';

export const api: Api = API_MODE === 'http' ? createHttpApi(import.meta.env.VITE_API_BASE_URL || '/api') : mockApi;

export type { Api };
