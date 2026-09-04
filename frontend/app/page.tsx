'use client';

import React, { useState } from 'react';
import {
  CheckCircle2,
  Circle,
  Loader2,
  FileText,
  ShieldCheck,
  Play,
  Lock,
  User
} from 'lucide-react';

export default function Dashboard() {
  const [role, setRole] = useState<'Engineer' | 'Manager'>('Manager');
  const [taskInput, setTaskInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);

  // Pre-configured scenario buttons for fast testing
  const scenarios = [
    "Summarize safety incidents in Unit 3 in the last 6 months.",
    "List all SOP violations in Q2 and suggest corrective actions.",
    "Generate a checklist for pre-startup safety review for Unit 3."
  ];

  const handleRunTask = (query: string) => {
    setTaskInput(query);
    setIsRunning(true);
    // Backend API trigger goes here
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">

      {/* 1. TOP HEADER & STATUS BAR */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <ShieldCheck className="w-8 h-8 text-blue-400" />
          <div>
            <h1 className="text-xl font-bold text-white tracking-wide">MRPL Sovereign AI Workbench</h1>
            <p className="text-xs text-slate-400">On-Premise Industrial Task Automation</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Air-Gapped / Offline Badge */}
          <div className="flex items-center gap-2 bg-emerald-950/80 border border-emerald-500/30 text-emerald-400 px-3 py-1.5 rounded-full text-sm font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>Air-Gapped / Offline Node</span>
          </div>

          {/* Role Switcher */}
          <div className="flex items-center gap-2 bg-slate-700/50 p-1 rounded-lg border border-slate-600">
            <User className="w-4 h-4 text-slate-400 ml-2" />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'Engineer' | 'Manager')}
              className="bg-transparent text-sm font-medium text-slate-200 focus:outline-none cursor-pointer pr-2"
            >
              <option value="Engineer" className="bg-slate-800">Role: Field Engineer</option>
              <option value="Manager" className="bg-slate-800">Role: Plant Manager</option>
            </select>
          </div>
        </div>
      </header>

      {/* 2. ONE-CLICK QUICK ACTIONS */}
      <section className="bg-slate-800/50 border-b border-slate-700/60 px-6 py-3">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">
          Quick Task Templates (One-Click)
        </span>
        <div className="flex flex-wrap gap-3">
          {scenarios.map((text, idx) => (
            <button
              key={idx}
              onClick={() => handleRunTask(text)}
              className="bg-slate-700/60 hover:bg-slate-700 border border-slate-600 text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors text-left flex items-center gap-2"
            >
              <Play className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <span>{text}</span>
            </button>
          ))}
        </div>
      </section>

      {/* 3. MAIN WORKSPACE GRID */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 p-6">

        {/* LEFT WORKSPACE PANEL (65% width) */}
        <div className="lg:col-span-8 flex flex-col gap-6">

          {/* Input Box */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-lg">
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Enter High-Level Operational Task
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                placeholder="e.g., Summarize pressure anomaly logs for Unit 3 and cite relevant SOP safety guidelines..."
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-base"
              />
              <button
                onClick={() => setIsRunning(true)}
                disabled={!taskInput.trim() || isRunning}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-6 py-3 rounded-lg flex items-center gap-2 transition-colors shrink-0"
              >
                {isRunning ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
                <span>Run Task</span>
              </button>
            </div>
          </div>

          {/* Generated Output Viewer */}
          <div className="flex-1 bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-lg flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-700 pb-4 mb-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-400" />
                Generated Output & Report
              </h2>
              <span className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded">
                Format: Markdown Safety Summary
              </span>
            </div>

            {/* Content area with high legibility styling */}
            <div className="flex-1 text-slate-200 space-y-4 text-base leading-relaxed overflow-y-auto max-h-[500px] pr-2">
              <div className="bg-slate-900/60 border border-slate-700/80 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-white mb-2">Unit 3 Safety Incident Executive Summary</h3>
                <p className="text-sm text-slate-400 mb-4">Time Window: Last 6 Months | Database: Internal Incident Logs</p>

                <h4 className="font-semibold text-blue-300 mt-4 mb-1">Key Findings</h4>
                <ul className="list-disc list-inside space-y-2 text-slate-300">
                  <li><strong className="text-white">Oct 14, 2025:</strong> Pressure spike noted in Valve 3B (45 bar reached vs 30 bar safe limit).</li>
                  <li><strong className="text-white">Nov 02, 2025:</strong> Temperature sensor latency warning reported during routine startup sequence.</li>
                </ul>

                <h4 className="font-semibold text-blue-300 mt-4 mb-2">Relevant Manual Citations</h4>
                <div className="flex flex-wrap gap-2">
                  <span className="inline-flex items-center gap-1.5 bg-blue-950 border border-blue-500/40 text-blue-300 px-3 py-1 rounded-md text-xs font-medium cursor-pointer hover:bg-blue-900">
                    <FileText className="w-3.5 h-3.5" /> SOP-PR-302.pdf (Page 14)
                  </span>
                  <span className="inline-flex items-center gap-1.5 bg-blue-950 border border-blue-500/40 text-blue-300 px-3 py-1 rounded-md text-xs font-medium cursor-pointer hover:bg-blue-900">
                    <FileText className="w-3.5 h-3.5" /> Incident_Log_Q3_Q4.db
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT PANEL: AGENT EXECUTION LOG (35% width) */}
        <div className="lg:col-span-4 bg-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg flex flex-col">
          <div className="border-b border-slate-700 pb-3 mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold text-white">Agent Progress Log</h2>
            <span className="text-xs text-slate-400">Step-by-Step Tool Trace</span>
          </div>

          {/* Steps List */}
          <div className="space-y-4 flex-1">

            {/* Step 1: Complete */}
            <div className="flex items-start gap-3 bg-slate-900/40 p-3 rounded-lg border border-slate-700/50">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-slate-200">1. Database Search</h4>
                <p className="text-xs text-slate-400 mt-0.5">Queried internal SQL database for Unit 3 records in the past 6 months.</p>
                <span className="inline-block mt-2 text-[10px] bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded font-mono">Found 4 entries</span>
              </div>
            </div>

            {/* Step 2: In Progress */}
            <div className="flex items-start gap-3 bg-slate-900/40 p-3 rounded-lg border border-blue-500/30">
              <Loader2 className="w-5 h-5 text-blue-400 animate-spin shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-blue-300">2. Vector Document Retrieval</h4>
                <p className="text-xs text-slate-400 mt-0.5">Cross-referencing pressure logs against Unit 3 SOP Manuals...</p>
                <span className="inline-block mt-2 text-[10px] bg-blue-950 text-blue-400 px-2 py-0.5 rounded font-mono">Searching SOP-PR-302.pdf</span>
              </div>
            </div>

            {/* Step 3: Pending */}
            <div className="flex items-start gap-3 opacity-50 p-3">
              <Circle className="w-5 h-5 text-slate-500 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-slate-400">3. Report Generation</h4>
                <p className="text-xs text-slate-500 mt-0.5">Synthesizing final safety checklist and action plan.</p>
              </div>
            </div>

          </div>

          {/* Audit Footer */}
          <div className="mt-auto pt-4 border-t border-slate-700 text-xs text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-slate-500" /> Audit Logging Active
            </span>
            <span className="text-slate-500 font-mono">Session ID: #8492</span>
          </div>

        </div>

      </main>
    </div>
  );
}