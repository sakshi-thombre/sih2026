/**
 * frontend/lib/api.ts
 *
 * Single place that knows how to talk to the FastAPI backend: base URL,
 * auth header, and error normalization. Every other client (agentClient,
 * documentsClient) goes through `apiRequest` — nothing else in the app
 * should call `fetch()` against the backend directly.
 */

export class ApiError extends Error {
    status: number;
    code: string;

    constructor(status: number, code: string, message: string) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
    }
}

const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

if (!process.env.NEXT_PUBLIC_BACKEND_URL && process.env.NODE_ENV !== 'production') {
    console.warn(
        '[api] NEXT_PUBLIC_BACKEND_URL is not set in .env.local — defaulting to http://localhost:8000'
    );
}

async function getAuthHeader(): Promise<Record<string, string>> {
    const { supabase } = await import('./supabase');
    const {
        data: { session },
    } = await supabase.auth.getSession();

    if (!session) {
        throw new ApiError(401, 'not_authenticated', 'You must be signed in to do this.');
    }
    return { Authorization: `Bearer ${session.access_token}` };
}

interface RequestOptions {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    body?: unknown; // JSON-serializable request body
    formData?: FormData; // mutually exclusive with `body`
    auth?: boolean; // default true — set false for any future public endpoint
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, formData, auth = true } = opts;

    let authHeaders: Record<string, string> = {};
    if (auth) {
        authHeaders = await getAuthHeader(); // throws ApiError(401) if not signed in
    }

    const headers: Record<string, string> = { ...authHeaders };
    if (!formData && body !== undefined) {
        headers['Content-Type'] = 'application/json';
    }
    // NOTE: never set Content-Type manually for FormData — the browser needs
    // to set the multipart boundary itself.

    let res: Response;
    try {
        res = await fetch(`${BASE_URL}${path}`, {
            method,
            headers,
            body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
        });
    } catch {
        // fetch() itself threw — network error, backend down, CORS block, etc.
        throw new ApiError(0, 'backend_unavailable', `Could not reach the backend at ${BASE_URL}.`);
    }

    if (!res.ok) {
        let code = 'unknown_error';
        let message = `Request failed with status ${res.status}`;
        try {
            const data = await res.json();
            if (data?.error?.code) code = data.error.code;
            if (data?.error?.message) message = data.error.message;
        } catch {
            // response wasn't JSON, or didn't match {error:{code,message}} — fall
            // back to the generic message above rather than guessing further.
        }
        throw new ApiError(res.status, code, message);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
}

export { BASE_URL };

