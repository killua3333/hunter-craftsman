const configuredUrl = import.meta.env.VITE_BACKEND_URL?.trim();

export const BACKEND_URL = configuredUrl || 'http://10.0.2.2:8791';
