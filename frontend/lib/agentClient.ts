/**
 * frontend/lib/agentClient.ts
 *
 * Real backend calls for the five frontend-facing agent endpoints.
 * Deliberately does NOT include tools/execute — that's internal-only,
 * backend-service-to-agent-service, and must never be called from here.
 */

import { apiRequest, ApiError } from './api';

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'cancelled'];

// Citation/source shape wasn't published as of this integration — kept
// intentionally loose and rendered defensively in the UI. Tighten this once
// confirmed with the backend team.
export type RunSource = Record<string, unknown>;

export interface AgentRun {
    run_id: string;
    status: RunStatus;
    task: string;
    created_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    answer: string | null;
    plan_summary: string[] | string | null;
    tools_used: string[] | null;
    sources: RunSource[] | null;
    error_code: string | null;
    error_message: string | null;
}

export interface RunAction {
    event_type: string;
    timestamp: string;
    metadata?: Record<string, unknown>;
}

export async function createRun(
    task: string,
    context: Record<string, unknown> = {}
): Promise<{ run_id: string; status: RunStatus }> {
    return apiRequest('/api/v1/agent/runs', { method: 'POST', body: { task, context } });
}

export async function getRunStatus(runId: string): Promise<{ run_id: string; status: RunStatus }> {
    return apiRequest(`/api/v1/agent/runs/${runId}/status`);
}

export async function getRun(runId: string): Promise<AgentRun> {
    return apiRequest(`/api/v1/agent/runs/${runId}`);
}

export async function cancelRun(runId: string): Promise<{ run_id: string; status: RunStatus }> {
    return apiRequest(`/api/v1/agent/runs/${runId}/cancel`, { method: 'POST' });
}

export async function getRunActions(runId: string): Promise<RunAction[]> {
    const data = await apiRequest<{ run_id: string; actions: RunAction[] }>(
        `/api/v1/agent/runs/${runId}/actions`
    );
    return data.actions;
}

export { ApiError };
