'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  Shield,
  Search,
  Play,
  FileText,
  X,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Copy,
  Check,
  ListChecks,
  Wrench,
  BookOpen,
} from 'lucide-react';
import { createRun, getRun, type AgentRun } from './mockAgentClient';

// ---------------------------------------------------------------------------
// DEMO_MODE: the backend team's auth + real agent API aren't wired up yet
// (see FRONTEND_API_REQUIREMENTS.md — /agent/runs currently always errors
// because auth isn't implemented). Until that lands, this screen runs
// entirely against `mockAgentClient.ts` so the rest of the team has a
// working, presentable UI to build against.
//
// To go live later: set DEMO_MODE to false, and swap `runMockTask` below
// for a real fetch to POST /api/v1/agent/runs + polling GET .../status.
// The `AgentRun` shape already matches the documented API contract, so the
// rest of this component shouldn't need to change.
// ---------------------------------------------------------------------------
const DEMO_MODE = true;

type Role = 'Plant Manager' | 'Safety Officer';

export interface TaskRecord {
  id: string;
  title: string;
  unit: string;
  restrictedToRole: Role | 'All';
  status: 'In Progress' | 'Completed' | 'Pending';
}

const MOCK_PROJECTS: TaskRecord[] = Array.from({ length: 24 }, (_, i) => ({
  id: `PROJ-${1000 + i}`,
  title:
    i % 3 === 0
      ? `Unit ${(i % 5) + 1} pressure anomaly analysis`
      : i % 3 === 1
        ? `Unit ${(i % 5) + 1} SOP compliance review`
        : `Unit ${(i % 5) + 1} pre-startup checklist`,
  unit: `Unit ${(i % 5) + 1}`,
  restrictedToRole: i % 3 === 0 ? 'Plant Manager' : i % 2 === 0 ? 'Safety Officer' : 'All',
  status: i % 4 === 0 ? 'In Progress' : i % 7 === 0 ? 'Pending' : 'Completed',
}));

const QUICK_TASKS = [
  {
    title: 'Summarize safety incidents',
    detail: 'Review Unit 3 incident logs from the last 6 months for SOP compliance.',
    task: 'Summarize safety incidents in Unit 3 in the last 6 months',
  },
  {
    title: 'SOP violation review',
    detail: 'Find Q2 SOP violations across the plant and suggest corrective actions.',
    task: 'List all SOP violations in Q2 and suggest corrective actions',
  },
  {
    title: 'Pre-startup checklist',
    detail: 'Generate a safety checklist ahead of scheduled valve maintenance.',
    task: 'Generate a checklist for pre-startup safety review for this unit',
  },
];

function deriveSteps(run: AgentRun | null) {
  const steps = [
    { id: 1, label: 'Plan & search', detail: 'Breaking the task into steps and querying internal sources.' },
    { id: 2, label: 'Cross-reference sources', detail: 'Matching findings against SOPs and manuals.' },
    { id: 3, label: 'Generate report', detail: 'Synthesizing the final answer with citations.' },
  ] as const;

  return steps.map((step) => {
    let status: 'pending' | 'running' | 'completed' = 'pending';
    if (run) {
      const planReady = run.tools_used.length > 0;
      const sourcesReady = run.sources.length > 0;
      const answerReady = run.answer !== null;

      if (step.id === 1) status = answerReady || planReady ? 'completed' : run.status === 'running' || run.status === 'queued' ? 'running' : 'pending';
      if (step.id === 2) status = answerReady || sourcesReady ? 'completed' : planReady ? 'running' : 'pending';
      if (step.id === 3) status = answerReady ? 'completed' : sourcesReady ? 'running' : 'pending';
    }
    return { ...step, status };
  });
}

export default function Workbench() {
  const [activeTab, setActiveTab] = useState<'templates' | 'input' | 'progress'>('input');
  const [taskInput, setTaskInput] = useState('');
  const [selectedRole, setSelectedRole] = useState<Role>('Plant Manager');
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const [run, setRun] = useState<AgentRun | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isExecuting = run !== null && (run.status === 'queued' || run.status === 'running');
  const steps = deriveSteps(run);

  const visibleProjects = MOCK_PROJECTS.filter((proj) => {
    if (selectedRole === 'Plant Manager') return true;
    return proj.restrictedToRole === 'All' || proj.restrictedToRole === 'Safety Officer';
  });

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function getAccessToken(): Promise<string> {
    if (DEMO_MODE) return 'demo-mock-token';
    // Loaded dynamically so a missing/unconfigured @/lib/supabase never
    // breaks the build while DEMO_MODE is on.
    const { supabase } = await import('@/lib/supabase');
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) throw new Error('Authentication required. Please log in to run tasks.');
    return session.access_token;
  }

  async function handleRunTask() {
    if (!taskInput.trim() || isExecuting) return;

    setErrorMessage(null);
    setRun(null);
    setIsLogOpen(true);
    setCopied(false);

    try {
      await getAccessToken(); // will throw in non-demo mode if not logged in

      const started = DEMO_MODE
        ? createRun(taskInput, selectedRole)
        : null; // real API call goes here once DEMO_MODE is false

      if (!started) throw new Error('Real backend integration not wired up yet.');
      setRun(started);

      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(() => {
        const latest = getRun(started.run_id);
        if (!latest) return;
        setRun(latest);
        if (latest.status === 'completed' || latest.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          if (latest.status === 'failed') {
            setErrorMessage(latest.error_message ?? 'The task failed to complete.');
          }
        }
      }, 400);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'An error occurred while executing the task.');
    }
  }

  function handleCopyReport() {
    if (!run?.answer) return;
    navigator.clipboard.writeText(run.answer).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans relative overflow-x-hidden">
      {DEMO_MODE && (
        <div className="bg-amber-50 border-b border-amber-200 text-amber-800 text-xs text-center py-1.5 px-4">
          Demo mode — running against a simulated backend. Timings and report content are illustrative.
        </div>
      )}

      {/* Top Navigation Bar */}
      <header className="flex items-center justify-between px-6 py-4 bg-white/80 backdrop-blur-md border-b border-slate-200 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Shield className="w-6 h-6 text-slate-700" />
          <h1 className="font-semibold text-lg tracking-tight text-slate-900">MRPL Sovereign AI Workbench</h1>
        </div>

        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Air-gapped / offline
          </span>
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value as Role)}
            className="bg-slate-100 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="Plant Manager">Role: Plant Manager</option>
            <option value="Safety Officer">Role: Safety Officer</option>
          </select>
        </div>
      </header>

      {/* Main Navigation Tabs */}
      <div className="bg-white border-b border-slate-200 px-6 pt-2">
        <nav className="flex gap-2">
          {([
            ['templates', 'Task templates'],
            ['input', 'New task'],
            ['progress', `Project progress (${visibleProjects.length})`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 ${activeTab === key
                ? 'border-slate-800 text-slate-900 bg-slate-50'
                : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 p-8 max-w-5xl w-full mx-auto space-y-8">
        {activeTab === 'input' && (
          <>
            <div className="text-center space-y-4 pt-4">
              <h2 className="text-xl font-semibold text-slate-800">Enter a high-level operational task</h2>
              <div className="flex items-center gap-3 max-w-2xl mx-auto">
                <div className="relative flex-1">
                  <Search className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={taskInput}
                    onChange={(e) => setTaskInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRunTask()}
                    placeholder="e.g. Summarize pressure anomaly logs for Unit 3..."
                    className="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 bg-white/70 backdrop-blur-sm shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-slate-800 transition"
                  />
                </div>
                <button
                  onClick={handleRunTask}
                  disabled={isExecuting || !taskInput.trim()}
                  className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white font-medium text-sm px-6 py-3 rounded-xl shadow transition active:scale-95 whitespace-nowrap cursor-pointer disabled:cursor-not-allowed"
                >
                  {isExecuting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                  {isExecuting ? 'Running…' : 'Run task'}
                </button>
              </div>
            </div>

            {/* Output & Report View */}
            <div className="bg-white/80 backdrop-blur-sm border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2 text-slate-700 font-semibold">
                  <FileText className="w-5 h-5 text-slate-500" />
                  <span>Generated report</span>
                </div>
                {run?.status === 'completed' && run.answer && (
                  <button
                    onClick={handleCopyReport}
                    className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition"
                  >
                    {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? 'Copied' : 'Copy report'}
                  </button>
                )}
              </div>

              <div className="p-6 bg-slate-50 rounded-xl border border-slate-100 min-h-[220px] text-slate-600 text-sm leading-relaxed">
                {errorMessage ? (
                  <div className="flex items-center gap-2 text-red-600">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    <span>{errorMessage}</span>
                  </div>
                ) : isExecuting ? (
                  <div className="flex items-center justify-center h-40 gap-3 text-slate-500">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Running the agent pipeline…</span>
                  </div>
                ) : run?.status === 'completed' && run.answer ? (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                      <span>Run {run.run_id.slice(0, 8)}</span>
                      <span>·</span>
                      <span>{run.role}</span>
                      {run.completed_at && (
                        <>
                          <span>·</span>
                          <span>{new Date(run.completed_at).toLocaleTimeString()}</span>
                        </>
                      )}
                    </div>

                    <div className="prose prose-slate text-sm max-w-none">
                      {run.answer.split('\n\n').map((para, i) => (
                        <p key={i} className="mb-3 last:mb-0 whitespace-pre-line">
                          {para}
                        </p>
                      ))}
                    </div>

                    {run.tools_used.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {run.tools_used.map((tool) => (
                          <span
                            key={tool}
                            className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200"
                          >
                            <Wrench className="w-3 h-3" />
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}

                    {run.sources.length > 0 && (
                      <div className="pt-3 border-t border-slate-200 space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                          <BookOpen className="w-3.5 h-3.5" />
                          Sources
                        </div>
                        <ul className="space-y-1">
                          {run.sources.map((s, i) => (
                            <li key={i} className="text-xs text-slate-500">
                              {s.title}
                              <span className="text-slate-400"> — {s.location}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-400">A generated report will appear here after you run a task.</p>
                )}
              </div>
            </div>
          </>
        )}

        {activeTab === 'templates' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {QUICK_TASKS.map((qt) => (
              <div
                key={qt.title}
                onClick={() => {
                  setTaskInput(qt.task);
                  setActiveTab('input');
                }}
                className="p-5 bg-white border border-slate-200 rounded-xl hover:border-slate-400 transition cursor-pointer"
              >
                <h3 className="font-semibold text-slate-800 mb-1">{qt.title}</h3>
                <p className="text-xs text-slate-500">{qt.detail}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'progress' && (
          <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-800">Active & historical projects</h3>
                <p className="text-xs text-slate-500">
                  Showing projects visible to <strong>{selectedRole}</strong>
                </p>
              </div>
              <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full">
                {visibleProjects.length} of {MOCK_PROJECTS.length} projects
              </span>
            </div>

            <div className="divide-y divide-slate-100 max-h-[350px] overflow-y-auto">
              {visibleProjects.map((proj) => (
                <div key={proj.id} className="py-3 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-mono text-slate-400 mr-3">{proj.id}</span>
                    <span className="font-medium text-slate-800">{proj.title}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-slate-400">{proj.unit}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-medium ${proj.status === 'Completed'
                        ? 'bg-emerald-100 text-emerald-800'
                        : proj.status === 'In Progress'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-500'
                        }`}
                    >
                      {proj.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Side Log Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-80 bg-white border-l border-slate-200 shadow-xl transition-transform duration-300 z-20 ${isLogOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-slate-500" />
            <h3 className="font-semibold text-sm text-slate-800">Agent progress</h3>
          </div>
          <button onClick={() => setIsLogOpen(false)} className="p-1 rounded-lg hover:bg-slate-100">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="p-4 space-y-4 text-xs">
          {run ? (
            steps.map((step) => (
              <div key={step.id} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
                {step.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />}
                {step.status === 'running' && <Loader2 className="w-4 h-4 text-amber-600 mt-0.5 animate-spin shrink-0" />}
                {step.status === 'pending' && <div className="w-4 h-4 rounded-full border-2 border-slate-300 mt-0.5 shrink-0" />}
                <div>
                  <p className={`font-medium ${step.status === 'running' ? 'text-slate-900' : 'text-slate-700'}`}>
                    {step.label}
                  </p>
                  <p className="text-slate-500 mt-0.5">{step.detail}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-slate-400">Run a task to see the agent's plan and progress here.</p>
          )}
        </div>
      </div>

      {!isLogOpen && (
        <button
          onClick={() => setIsLogOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 bg-slate-900 text-white text-xs font-semibold py-3 px-1 rounded-l-md shadow-md [writing-mode:vertical-rl] tracking-wider hover:bg-slate-800 transition cursor-pointer"
        >
          Agent progress
        </button>
      )}
    </div>
  );
}
