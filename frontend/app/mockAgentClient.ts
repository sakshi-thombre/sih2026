export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface RunSource {
    title: string;
    location: string; // e.g. "SOP-114, §4.2" — where in the source this came from
}

export interface AgentRun {
    run_id: string;
    status: RunStatus;
    task: string;
    role: string;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
    plan_summary: string[];
    tools_used: string[];
    sources: RunSource[];
    answer: string | null;
    error_message: string | null;
}

const RUN_STORE = new Map<string, AgentRun>();

function newRunId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
        return crypto.randomUUID();
    }
    return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Picks a report template based on task keywords, mirroring the three
 * example tasks in the problem statement. Falls back to a generic
 * document-review template for anything else. */
function buildPlan(task: string): {
    plan_summary: string[];
    tools_used: string[];
    sources: RunSource[];
    answer: string;
} {
    const t = task.toLowerCase();

    if (t.includes('incident') || t.includes('safety')) {
        return {
            plan_summary: [
                'Query the incident log for the specified unit and time range.',
                'Cross-reference each incident against the relevant SOP sections.',
                'Summarize findings and flag any recurring root causes.',
            ],
            tools_used: ['SQL Query Runner', 'Document Search', 'Report Generator'],
            sources: [
                { title: 'Unit 3 Incident Log — FY2025–26', location: 'Q1–Q2 entries' },
                { title: 'SOP-114: Valve Isolation Procedure', location: '§4.2' },
                { title: 'SOP-089: Confined Space Entry', location: '§2.1' },
            ],
            answer:
                'Six incidents were logged for Unit 3 in the last two quarters, four of ' +
                'which were minor near-misses during routine valve isolation. Two share ' +
                'a common root cause: isolation tags were removed before the second ' +
                'verification step in SOP-114 §4.2 was completed.\n\n' +
                'Recommended follow-up: reinforce the two-person verification step in ' +
                'the next shift briefing, and consider adding a physical interlock ' +
                'checkpoint until adherence improves.',
        };
    }

    if (t.includes('sop') || t.includes('violation') || t.includes('compliance')) {
        return {
            plan_summary: [
                'Search SOP compliance records for the specified quarter.',
                'Filter for confirmed violations and group by procedure.',
                'Draft corrective-action recommendations for each group.',
            ],
            tools_used: ['Document Search', 'SQL Query Runner', 'Report Generator'],
            sources: [
                { title: 'Q2 Compliance Audit — Unit 3', location: 'Findings §3' },
                { title: 'SOP-114: Valve Isolation Procedure', location: '§4.2' },
                { title: 'SOP-201: Permit-to-Work System', location: '§1.4' },
            ],
            answer:
                'Three confirmed SOP violations were logged in Q2, all related to ' +
                'permit-to-work sign-off delays under SOP-201 §1.4.\n\n' +
                'Corrective actions: (1) add a mandatory permit-status check to the ' +
                'shift handover checklist, (2) route overdue permits to the shift ' +
                'supervisor automatically after 30 minutes, (3) re-brief the Unit 3 ' +
                'crew on SOP-201 within the next two weeks.',
        };
    }

    if (t.includes('checklist') || t.includes('startup') || t.includes('pre-startup')) {
        return {
            plan_summary: [
                'Retrieve the pre-startup safety review template.',
                'Match it against equipment-specific SOPs for the target unit.',
                'Assemble a checklist ordered by criticality.',
            ],
            tools_used: ['Document Search', 'Report Generator'],
            sources: [
                { title: 'Pre-Startup Safety Review Template', location: 'Master copy' },
                { title: 'SOP-114: Valve Isolation Procedure', location: '§4.2' },
                { title: 'Unit 3 Equipment Register', location: 'Valves & rotating equipment' },
            ],
            answer:
                'Pre-startup checklist generated for the requested unit:\n\n' +
                '1. Confirm all isolation tags from the prior shutdown are logged and cleared.\n' +
                '2. Verify valve lineup against the current P&ID revision.\n' +
                '3. Confirm relief valve set points match SOP-114 §4.2.\n' +
                '4. Check that all permit-to-work entries for the shutdown are closed.\n' +
                '5. Walk the unit perimeter for housekeeping and obstruction checks.\n' +
                '6. Obtain sign-off from the shift supervisor before startup.',
        };
    }

    return {
        plan_summary: [
            'Search the internal document index for records relevant to the task.',
            'Cross-reference retrieved records against applicable SOPs.',
            'Synthesize findings into a structured, cited report.',
        ],
        tools_used: ['Document Search', 'Report Generator'],
        sources: [
            { title: 'Unit Operations Manual', location: 'Relevant sections' },
            { title: 'SOP Index', location: 'Cross-reference' },
        ],
        answer:
            'This is a demo response generated from a mock backend so the team can ' +
            'build against a realistic contract before the real agent pipeline is ' +
            'wired up. Try a task mentioning "incident", "SOP", or "checklist" to ' +
            'see a more tailored example report.',
    };
}

const STEP_DELAYS_MS = [700, 1100, 1300, 900]; // queued -> running x2 -> completed

/** Starts a simulated run and returns immediately with a queued run,
 * mirroring the real API's `202 Accepted` + background-execution pattern.
 * The run updates in the background; poll it with `getRun`. */
export function createRun(task: string, role: string): AgentRun {
    const run_id = newRunId();
    const now = new Date().toISOString();

    const run: AgentRun = {
        run_id,
        status: 'queued',
        task,
        role,
        created_at: now,
        started_at: null,
        completed_at: null,
        plan_summary: [],
        tools_used: [],
        sources: [],
        answer: null,
        error_message: null,
    };
    RUN_STORE.set(run_id, run);

    const plan = buildPlan(task);

    // queued -> running (plan visible)
    setTimeout(() => {
        const current = RUN_STORE.get(run_id);
        if (!current) return;
        RUN_STORE.set(run_id, {
            ...current,
            status: 'running',
            started_at: new Date().toISOString(),
            plan_summary: plan.plan_summary,
            tools_used: plan.tools_used,
        });
    }, STEP_DELAYS_MS[0]);

    // running -> running (sources gathered)
    setTimeout(() => {
        const current = RUN_STORE.get(run_id);
        if (!current) return;
        RUN_STORE.set(run_id, { ...current, sources: plan.sources });
    }, STEP_DELAYS_MS[0] + STEP_DELAYS_MS[1]);

    // running -> completed
    setTimeout(() => {
        const current = RUN_STORE.get(run_id);
        if (!current) return;
        RUN_STORE.set(run_id, {
            ...current,
            status: 'completed',
            completed_at: new Date().toISOString(),
            answer: plan.answer,
        });
    }, STEP_DELAYS_MS[0] + STEP_DELAYS_MS[1] + STEP_DELAYS_MS[2]);

    return run;
}

/** Mirrors `GET /agent/runs/{run_id}`. */
export function getRun(runId: string): AgentRun | null {
    return RUN_STORE.get(runId) ?? null;
}