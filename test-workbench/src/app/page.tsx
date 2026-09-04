'use client';

import React, { useState, useEffect } from 'react';
import { Shield, Search, Play, FileText, X, Database, Cpu, CheckCircle2, Loader2, AlertTriangle } from 'lucide-react';

// --- MOCK DATABASE & RBAC TYPES ---
export interface TaskRecord {
  id: string;
  title: string;
  unit: string;
  restrictedToRole: 'Plant Manager' | 'Safety Officer' | 'All';
  status: 'In Progress' | 'Completed' | 'Pending';
}

// Generate 120+ mock projects for concurrent workload simulation
const MOCK_PROJECTS: TaskRecord[] = Array.from({ length: 124 }, (_, i) => ({
  id: `PROJ-${1000 + i}`,
  title: i % 2 === 0 ? `Unit ${(i % 5) + 1} Pressure Anomaly Analysis` : `Unit ${(i % 5) + 1} SOP Compliance Review`,
  unit: `Unit ${(i % 5) + 1}`,
  restrictedToRole: i % 3 === 0 ? 'Plant Manager' : i % 2 === 0 ? 'Safety Officer' : 'All',
  status: i % 4 === 0 ? 'In Progress' : 'Completed',
}));

export interface LogStep {
  id: number;
  label: string;
  detail: string;
  status: 'pending' | 'running' | 'completed';
}

const INITIAL_STEPS: Omit<LogStep, 'status'>[] = [
  { id: 1, label: 'Database Search', detail: 'Querying internal SQL logs for Unit 3...' },
  { id: 2, label: 'Vector Document Retrieval', detail: 'Cross-referencing pressure logs against SOP manuals...' },
  { id: 3, label: 'Report Generation', detail: 'Synthesizing final safety checklist and executive summary...' },
];

export default function Workbench() {
  const [activeTab, setActiveTab] = useState<'templates' | 'input' | 'progress'>('input');
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [taskInput, setTaskInput] = useState('');
  const [selectedRole, setSelectedRole] = useState<'Plant Manager' | 'Safety Officer'>('Plant Manager');

  // Real-time Simulation States
  const [isExecuting, setIsExecuting] = useState(false);
  const [hasReportGenerated, setHasReportGenerated] = useState(false);
  const [steps, setSteps] = useState<LogStep[]>(
    INITIAL_STEPS.map((s) => ({ ...s, status: 'pending' }))
  );

  // Role-Based Access Control Filtering
  const visibleProjects = MOCK_PROJECTS.filter((proj) => {
    if (selectedRole === 'Plant Manager') return true;
    return proj.restrictedToRole === 'All' || proj.restrictedToRole === 'Safety Officer';
  });

  // Handle Task Execution & Animated Stream
  const handleRunTask = () => {
    setIsExecuting(true);
    setHasReportGenerated(false);
    setIsLogOpen(true);

    setSteps(INITIAL_STEPS.map((s, idx) => ({ ...s, status: idx === 0 ? 'running' : 'pending' })));

    setTimeout(() => {
      setSteps((prev) =>
        prev.map((s) => (s.id === 1 ? { ...s, status: 'completed' } : s.id === 2 ? { ...s, status: 'running' } : s))
      );
    }, 1200);

    setTimeout(() => {
      setSteps((prev) =>
        prev.map((s) => (s.id === 2 ? { ...s, status: 'completed' } : s.id === 3 ? { ...s, status: 'running' } : s))
      );
    }, 2800);

    setTimeout(() => {
      setSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' })));
      setIsExecuting(false);
      setHasReportGenerated(true);
    }, 4200);
  };

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
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Air Gapped / Offline
          </span>
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value as any)}
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
          <button
            onClick={() => setActiveTab('templates')}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 ${activeTab === 'templates'
                ? 'border-slate-800 text-slate-900 bg-slate-50'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            QUICK TASK TEMPLATES
          </button>
          <button
            onClick={() => setActiveTab('input')}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 ${activeTab === 'input'
                ? 'border-slate-800 text-slate-900 bg-slate-50'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            ENTER HIGH LEVEL OP TASK
          </button>
          <button
            onClick={() => setActiveTab('progress')}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 ${activeTab === 'progress'
                ? 'border-slate-800 text-slate-900 bg-slate-50'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            PROJECT PROGRESS ({visibleProjects.length})
          </button>
        </nav>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 p-8 max-w-5xl w-full mx-auto space-y-8">

        {activeTab === 'input' && (
          <>
            {/* Centered Task Input Section */}
            <div className="text-center space-y-4 pt-4">
              <h2 className="text-xl font-bold uppercase tracking-wide text-slate-800">
                Enter High Level Operational Task
              </h2>
              <div className="flex items-center gap-3 max-w-2xl mx-auto">
                <div className="relative flex-1">
                  <Search className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={taskInput}
                    onChange={(e) => setTaskInput(e.target.value)}
                    placeholder="e.g. Summarize pressure anomaly logs for Unit 3..."
                    className="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 bg-white/70 backdrop-blur-sm shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-slate-800 transition"
                  />
                </div>
                <button
                  onClick={handleRunTask}
                  disabled={isExecuting}
                  className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white font-medium text-sm px-6 py-3 rounded-xl shadow transition active:scale-95 whitespace-nowrap"
                >
                  {isExecuting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                  {isExecuting ? 'RUNNING...' : 'RUN TASK'}
                </button>
              </div>
            </div>

            {/* Generated Output & Report Section */}
            <div className="bg-white/80 backdrop-blur-sm border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2 text-slate-700 font-semibold border-b border-slate-100 pb-3">
                <FileText className="w-5 h-5 text-slate-500" />
                <span>GENERATED OUTPUT & REPORT</span>
              </div>
              <div className="p-6 bg-slate-50 rounded-xl border border-slate-100 min-h-[220px] text-slate-600 text-sm leading-relaxed">
                {hasReportGenerated ? (
                  <div className="space-y-4">
                    <h3 className="text-lg font-bold text-slate-900">Unit 3 Safety Incident Executive Summary</h3>
                    <p className="text-xs text-slate-500">Time Window: Last 6 Months | Scope: Internal Incident Logs</p>
                    <div className="border-t border-slate-200 pt-3 space-y-2">
                      <p className="font-semibold text-slate-800">Key Findings:</p>
                      <ul className="list-disc pl-5 space-y-1 text-slate-700">
                        <li><strong>Oct 14, 2025:</strong> Pressure spike noted in Valve 3B (45 bar reached vs 30 bar safe limit).</li>
                        <li><strong>Nov 02, 2025:</strong> Temperature sensor warning reported during routine startup sequence.</li>
                      </ul>
                    </div>
                  </div>
                ) : isExecuting ? (
                  <div className="flex items-center justify-center h-40 gap-3 text-slate-500">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Analyzing operational logs and building report...</span>
                  </div>
                ) : (
                  <p className="italic text-slate-400">Output report will appear here after executing a task...</p>
                )}
              </div>
            </div>
          </>
        )}

        {activeTab === 'templates' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div
              onClick={() => { setTaskInput('Summarize safety incidents in Unit 3 in the last 6 months'); setActiveTab('input'); }}
              className="p-5 bg-white border border-slate-200 rounded-xl hover:border-slate-400 transition cursor-pointer"
            >
              <h3 className="font-semibold text-slate-800 mb-1">Summarize Safety Incidents</h3>
              <p className="text-xs text-slate-500">Analyze Unit 3 logs over the last 6 months for SOP compliance.</p>
            </div>
            <div
              onClick={() => { setTaskInput('Generate pre-startup checklist for valve maintenance'); setActiveTab('input'); }}
              className="p-5 bg-white border border-slate-200 rounded-xl hover:border-slate-400 transition cursor-pointer"
            >
              <h3 className="font-semibold text-slate-800 mb-1">Pre-startup Checklist</h3>
              <p className="text-xs text-slate-500">Generate a safety audit checklist for scheduled valve maintenance.</p>
            </div>
          </div>
        )}

        {activeTab === 'progress' && (
          <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-800">Active & Historical Projects</h3>
                <p className="text-xs text-slate-500">Showing projects accessible to: <strong>{selectedRole}</strong></p>
              </div>
              <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full font-mono">
                Total System Loads: {MOCK_PROJECTS.length} concurrent workflows
              </span>
            </div>

            <div className="divide-y divide-slate-100 max-h-[350px] overflow-y-auto">
              {visibleProjects.slice(0, 10).map((proj) => (
                <div key={proj.id} className="py-3 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-mono text-slate-400 mr-3">{proj.id}</span>
                    <span className="font-medium text-slate-800">{proj.title}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-slate-400">{proj.unit}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${proj.status === 'Completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                      }`}>
                      {proj.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </main>

      {/* Slide-out Agent Progress Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-80 bg-white border-l border-slate-200 shadow-xl transition-transform duration-300 ease-in-out z-20 ${isLogOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h3 className="font-semibold text-sm text-slate-800">Agent Progress Log</h3>
          <button onClick={() => setIsLogOpen(false)} className="p-1 rounded-lg hover:bg-slate-100">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="p-4 space-y-4 text-xs">
          {steps.map((step) => (
            <div key={step.id} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
              {step.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />}
              {step.status === 'running' && <Loader2 className="w-4 h-4 text-amber-600 mt-0.5 animate-spin shrink-0" />}
              {step.status === 'pending' && <div className="w-4 h-4 rounded-full border-2 border-slate-300 mt-0.5 shrink-0" />}

              <div>
                <p className={`font-medium ${step.status === 'running' ? 'text-slate-900' : 'text-slate-700'}`}>
                  {step.id}. {step.label}
                </p>
                <p className="text-slate-500 mt-0.5">{step.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Drawer Toggle Tab on Right Side */}
      {!isLogOpen && (
        <button
          onClick={() => setIsLogOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 bg-slate-900 text-white text-xs font-semibold py-3 px-1 rounded-l-md shadow-md [writing-mode:vertical-rl] tracking-wider hover:bg-slate-800 transition"
        >
          AGENT PROGRESS LOG
        </button>
      )}

    </div>
  );
}