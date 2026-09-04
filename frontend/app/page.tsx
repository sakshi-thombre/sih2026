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
  XCircle,
  Upload,
  WifiOff,
  LogIn,
} from 'lucide-react';
import {
  createRun,
  getRun,
  getRunStatus,
  cancelRun,
  getRunActions,
  ApiError,
  TERMINAL_STATUSES,
  type AgentRun,
  type RunAction,
} from '@/lib/agentClient';
import { uploadDocument, searchDocuments, type SearchResult } from '@/lib/documentsClient';

type Role = 'Plant Manager' | 'Safety Officer';

type UIState =
  | 'idle'
  | 'submitting'
  | 'polling'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'backend_unavailable'
  | 'auth_failed';

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

const POLL_INTERVAL_MS = 1500;

function sourceLabel(source: Record<string, unknown>): string {
  const title = source.title ?? source.document ?? source.filename ?? source.name;
  const location = source.location ?? source.page ?? source.section;
  if (title && location) return `${String(title)} — ${String(location)}`;
  if (title) return String(title);
  return JSON.stringify(source);
}

function resultLocation(result: SearchResult): string {
  const parts: string[] = [];
  if (result.page_number != null) parts.push(`page ${result.page_number}`);
  parts.push(`chunk ${result.chunk_index}`);
  parts.push(`score ${result.score.toFixed(2)}`);
  return parts.join(' · ');
}

export default function Workbench() {
  const [activeTab, setActiveTab] = useState<'templates' | 'input' | 'progress' | 'documents'>('input');
  const [taskInput, setTaskInput] = useState('');
  const [selectedRole, setSelectedRole] = useState<Role>('Plant Manager');
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const [run, setRun] = useState<AgentRun | null>(null);
  const [uiState, setUiState] = useState<UIState>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actions, setActions] = useState<RunAction[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- Documents tab state ---
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchStatus, setSearchStatus] = useState<'idle' | 'searching' | 'done' | 'error'>('idle');
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function handleApiError(err: unknown): void {
    if (err instanceof ApiError) {
      if (err.status === 401 || err.code === 'not_authenticated') {
        setUiState('auth_failed');
        setErrorMessage('You need to be signed in to run tasks.');
      } else if (err.status === 0 || err.code === 'backend_unavailable') {
        setUiState('backend_unavailable');
        setErrorMessage(err.message);
      } else {
        setUiState('failed');
        setErrorMessage(err.message);
      }
    } else {
      setUiState('failed');
      setErrorMessage(err instanceof Error ? err.message : 'An unexpected error occurred.');
    }
  }

  async function handleRunTask() {
    if (!taskInput.trim() || uiState === 'submitting' || uiState === 'polling') return;

    setErrorMessage(null);
    setRun(null);
    setActions([]);
    setCopied(false);
    setIsLogOpen(true);
    setUiState('submitting');

    try {
      const started = await createRun(taskInput, { role: selectedRole });
      setRun({
        run_id: started.run_id,
        status: started.status,
        task: taskInput,
        answer: null,
        plan_summary: null,
        tools_used: null,
        sources: null,
        error_code: null,
        error_message: null,
      });
      setUiState('polling');

      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await getRunStatus(started.run_id);
          setRun((prev) => (prev ? { ...prev, status: statusRes.status } : prev));

          // Best-effort — the actions endpoint may briefly 404 before the
          // run starts producing events, so failures here don't stop polling.
          getRunActions(started.run_id)
            .then(setActions)
            .catch(() => { });

          if (TERMINAL_STATUSES.includes(statusRes.status)) {
            stopPolling();
            const full = await getRun(started.run_id);
            setRun(full);
            setUiState(
              full.status === 'completed' ? 'completed' : full.status === 'cancelled' ? 'cancelled' : 'failed'
            );
            if (full.error_message) setErrorMessage(full.error_message);
          }
        } catch (err) {
          stopPolling();
          handleApiError(err);
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      handleApiError(err);
    }
  }

  async function handleCancel() {
    if (!run) return;
    try {
      const res = await cancelRun(run.run_id);
      setRun((prev) => (prev ? { ...prev, status: res.status } : prev));
      if (TERMINAL_STATUSES.includes(res.status)) {
        stopPolling();
        setUiState('cancelled');
      }
    } catch (err) {
      handleApiError(err);
    }
  }

  function handleCopyReport() {
    if (!run?.answer) return;
    navigator.clipboard.writeText(run.answer).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  async function handleUpload() {
    if (!uploadFile) return;
    setUploadStatus('uploading');
    setUploadError(null);
    try {
      await uploadDocument(uploadFile);
      setUploadStatus('done');
    } catch (err) {
      setUploadStatus('error');
      setUploadError(err instanceof ApiError ? err.message : 'Upload failed.');
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return;
    setSearchStatus('searching');
    setSearchError(null);
    try {
      const results = await searchDocuments(searchQuery);
      setSearchResults(results);
      setSearchStatus('done');
    } catch (err) {
      setSearchStatus('error');
      setSearchError(err instanceof ApiError ? err.message : 'Search failed.');
    }
  }

  const isBusy = uiState === 'submitting' || uiState === 'polling';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans relative overflow-x-hidden">
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
            ['documents', 'Documents'],
            ['progress', 'Project progress'],
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
                  disabled={isBusy || !taskInput.trim()}
                  className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white font-medium text-sm px-6 py-3 rounded-xl shadow transition active:scale-95 whitespace-nowrap cursor-pointer disabled:cursor-not-allowed"
                >
                  {isBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                  {isBusy ? 'Running…' : 'Run task'}
                </button>
                {uiState === 'polling' && (
                  <button
                    onClick={handleCancel}
                    className="flex items-center gap-1.5 text-xs font-medium text-red-600 hover:text-red-700 px-3 py-3 whitespace-nowrap"
                  >
                    <XCircle className="w-4 h-4" />
                    Cancel
                  </button>
                )}
              </div>
            </div>

            <div className="bg-white/80 backdrop-blur-sm border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2 text-slate-700 font-semibold">
                  <FileText className="w-5 h-5 text-slate-500" />
                  <span>Generated report</span>
                </div>
                {uiState === 'completed' && run?.answer && (
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
                {uiState === 'backend_unavailable' ? (
                  <div className="flex items-center gap-2 text-red-600">
                    <WifiOff className="w-5 h-5 shrink-0" />
                    <span>{errorMessage ?? 'Could not reach the backend. Confirm it is running.'}</span>
                  </div>
                ) : uiState === 'auth_failed' ? (
                  <div className="flex items-center gap-2 text-amber-700">
                    <LogIn className="w-5 h-5 shrink-0" />
                    <span>{errorMessage ?? 'Please sign in to run tasks.'}</span>
                  </div>
                ) : uiState === 'failed' ? (
                  <div className="flex items-center gap-2 text-red-600">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    <span>{errorMessage ?? run?.error_message ?? 'The task failed.'}</span>
                  </div>
                ) : uiState === 'cancelled' ? (
                  <div className="flex items-center gap-2 text-slate-500">
                    <XCircle className="w-5 h-5 shrink-0" />
                    <span>Task cancelled.</span>
                  </div>
                ) : isBusy ? (
                  <div className="flex items-center justify-center h-40 gap-3 text-slate-500">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>{run?.status ? `Status: ${run.status}…` : 'Submitting task…'}</span>
                  </div>
                ) : uiState === 'completed' && run?.answer ? (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                      <span>Run {run.run_id.slice(0, 8)}</span>
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

                    {run.plan_summary &&
                      (Array.isArray(run.plan_summary)
                        ? run.plan_summary.length > 0
                        : run.plan_summary.trim().length > 0) && (
                        <div className="pt-3 border-t border-slate-200 space-y-1.5">
                          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                            <ListChecks className="w-3.5 h-3.5" />
                            Plan
                          </div>
                          {Array.isArray(run.plan_summary) ? (
                            <ol className="list-decimal list-inside space-y-1">
                              {run.plan_summary.map((step, i) => (
                                <li key={i} className="text-xs text-slate-500">
                                  {step}
                                </li>
                              ))}
                            </ol>
                          ) : (
                            <p className="text-xs text-slate-500 whitespace-pre-line">
                              {run.plan_summary}
                            </p>
                          )}
                        </div>
                      )}

                    {!!run.tools_used?.length && (
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

                    {!!run.sources?.length && (
                      <div className="pt-3 border-t border-slate-200 space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                          <BookOpen className="w-3.5 h-3.5" />
                          Sources
                        </div>
                        <ul className="space-y-1">
                          {run.sources.map((s, i) => (
                            <li key={i} className="text-xs text-slate-500">
                              {sourceLabel(s)}
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

        {activeTab === 'documents' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-slate-700 font-semibold">
                <Upload className="w-4 h-4 text-slate-500" />
                Upload a document
              </div>
              <input
                type="file"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="text-xs w-full"
              />
              <button
                onClick={handleUpload}
                disabled={!uploadFile || uploadStatus === 'uploading'}
                className="text-xs font-medium bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg transition"
              >
                {uploadStatus === 'uploading' ? 'Uploading…' : 'Upload'}
              </button>
              {uploadStatus === 'done' && (
                <p className="text-xs text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Uploaded.
                </p>
              )}
              {uploadStatus === 'error' && (
                <p className="text-xs text-red-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> {uploadError}
                </p>
              )}
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-slate-700 font-semibold">
                <Search className="w-4 h-4 text-slate-500" />
                Search documents
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search indexed documents…"
                  className="flex-1 text-xs px-3 py-2 rounded-lg border border-slate-300"
                />
                <button
                  onClick={handleSearch}
                  disabled={!searchQuery.trim() || searchStatus === 'searching'}
                  className="text-xs font-medium bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg transition"
                >
                  {searchStatus === 'searching' ? '…' : 'Search'}
                </button>
              </div>
              {searchStatus === 'error' && (
                <p className="text-xs text-red-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> {searchError}
                </p>
              )}
              {searchStatus === 'done' && (
                <ul className="space-y-2 max-h-60 overflow-y-auto">
                  {searchResults.length === 0 && <li className="text-xs text-slate-400">No results.</li>}
                  {searchResults.map((r) => (
                    <li key={r.chunk_id} className="text-xs border border-slate-100 rounded-lg p-2 bg-slate-50">
                      <div className="flex items-center justify-between">
                        <p className="font-medium text-slate-700">{r.filename}</p>
                        <span className="text-[10px] text-slate-400">{resultLocation(r)}</span>
                      </div>
                      {r.text && <p className="text-slate-500 mt-0.5 line-clamp-2">{r.text}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {activeTab === 'progress' && (
          <div className="bg-white p-6 rounded-xl border border-slate-200 text-sm text-slate-500">
            Project progress will connect to a real projects endpoint once one exists — not part of this
            integration pass.
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
            <h3 className="font-semibold text-sm text-slate-800">Agent actions</h3>
          </div>
          <button onClick={() => setIsLogOpen(false)} className="p-1 rounded-lg hover:bg-slate-100">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="p-4 space-y-3 text-xs">
          {run && (
            <div className="text-slate-500 pb-2 border-b border-slate-100">
              Status: <span className="font-medium text-slate-700">{run.status}</span>
            </div>
          )}
          {actions.length > 0 ? (
            actions.map((a, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium text-slate-700">{a.event_type}</p>
                  <p className="text-slate-400 mt-0.5">{new Date(a.timestamp).toLocaleTimeString()}</p>
                </div>
              </div>
            ))
          ) : run && !TERMINAL_STATUSES.includes(run.status) ? (
            <div className="flex items-center gap-2 text-slate-400 p-3">
              <Loader2 className="w-4 h-4 animate-spin" />
              Waiting for the first action…
            </div>
          ) : (
            <p className="text-slate-400">Run a task to see the agent&apos;s action trail here.</p>
          )}
        </div>
      </div>

      {!isLogOpen && (
        <button
          onClick={() => setIsLogOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 bg-slate-900 text-white text-xs font-semibold py-3 px-1 rounded-l-md shadow-md [writing-mode:vertical-rl] tracking-wider hover:bg-slate-800 transition cursor-pointer"
        >
          Agent actions
        </button>
      )}
    </div>
  );
}
