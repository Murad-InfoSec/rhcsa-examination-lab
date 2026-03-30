
import React, { useState, useEffect, useRef } from 'react';
import {
  Task,
  TaskStatus,
  PanelState,
  VMStatus,
  VncStatus,
  Exam,
  NodeGroup,
  CheckResult
} from './types';
import {
  getVmStatus,
  getTasks,
  startVM,
  stopVM,
  resetVM,
  checkTask,
  prepareTask,
  getExams,
  getActiveExam,
  setActiveExam,
  getVncStatus,
  saveCheckpoint,
  getCheckpointStatus,
} from './services/dockerService';
import {
  TerminalIcon,
  ListIcon,
  BookOpenIcon,
  CheckCircleIcon,
  PlayIcon,
  SquareIcon,
  RotateCcwIcon,
  RedHatIcon,
  AlertTriangleIcon,
  LayoutIcon
} from './components/Icon';
import Terminal from './components/Terminal';
import VncPanel from './components/VncPanel';
import Instructions from './components/Instructions';

const App: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<number | null>(1);
  const [vmStatus, setVmStatus] = useState<VMStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [exams, setExams] = useState<Exam[]>([]);
  const [activeExam, setActiveExamState] = useState<Exam | null>(null);
  const [vncStatus, setVncStatus] = useState<VncStatus | null>(null);
  const [terminalClearKey, setTerminalClearKey] = useState(0);
  const [terminalMsg, setTerminalMsg] = useState('');
  const [examModalOpen, setExamModalOpen] = useState(false);
  const [checkpointSaving, setCheckpointSaving] = useState(false);
  const [checkpointStatus, setCheckpointStatus] = useState<Record<string, boolean>>({});

  const [panels, setPanels] = useState<PanelState>(() => {
    const saved = localStorage.getItem('ui.panels');
    return saved ? JSON.parse(saved) : {
      tasks: true,
      instructions: true,
      terminal: true,
      results: true
    };
  });
  const [panelsOpen, setPanelsOpen] = useState(false);
  const panelsMenuRef = useRef<HTMLDivElement>(null);

  // Resizable split — instructions vs terminal row
  const [instrPct, setInstrPct] = useState(45);
  const workAreaRef = useRef<HTMLDivElement>(null);

  const startVertDrag = (e: React.PointerEvent) => {
    e.preventDefault();
    const startY   = e.clientY;
    const startPct = instrPct;
    const totalH   = workAreaRef.current?.offsetHeight ?? 1;
    document.body.style.cursor     = 'row-resize';
    document.body.style.userSelect = 'none';
    const onMove = (ev: PointerEvent) => {
      const next = startPct + ((ev.clientY - startY) / totalH) * 100;
      setInstrPct(Math.min(80, Math.max(15, next)));
    };
    const onUp = () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup',   onUp);
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup',   onUp);
  };


  const activeTask = tasks.find(t => t.id === activeTaskId) || null;
  const isBootMenu = activeTask?.node === NodeGroup.BOOT_MENU;

  // Restart backend on every page load, then initialise state.
  useEffect(() => {
    const init = async () => {
      try {
        await fetch('/api/restart', { method: 'POST' });
        await new Promise(r => setTimeout(r, 3000));
      } catch { /* backend already restarting */ }

      try {
        const [status, taskList, examList, activeExamData, cpStatus] = await Promise.all([
          getVmStatus(),
          getTasks(),
          getExams(),
          getActiveExam(),
          getCheckpointStatus(),
        ]);
        setVmStatus(status);
        setTasks(taskList);
        setExams(examList);
        setActiveExamState(activeExamData);
        setCheckpointStatus(cpStatus);
        if (taskList.length > 0 && !activeTaskId) setActiveTaskId(taskList[0].id);
      } catch (_) {
        setVmStatus({ available: false, error: 'Failed to load' });
        setTasks([]);
      } finally {
        setIsLoading(false);
      }
    };
    init();
  }, []);

  // Poll VNC status when active task is boot-menu, until the proxy is available.
  // Re-runs on terminalClearKey so reset/start/stop restart the poll and remount VncPanel.
  // Stops after 30 attempts (60 s) to avoid infinite polling when VNC never becomes available.
  useEffect(() => {
    if (!isBootMenu) {
      setVncStatus(null);
      return;
    }
    setVncStatus(null);
    let cancelled = false;
    const MAX_ATTEMPTS = 30;
    const poll = async () => {
      for (let attempt = 0; attempt < MAX_ATTEMPTS && !cancelled; attempt++) {
        try {
          const status = await getVncStatus();
          if (cancelled) break;
          setVncStatus(status);
          if (status?.available) break;
        } catch {
          if (cancelled) break;
          setVncStatus(null);
        }
        await new Promise(r => setTimeout(r, 2000));
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [isBootMenu, activeTask?.id, terminalClearKey]);

  useEffect(() => {
    localStorage.setItem('ui.panels', JSON.stringify(panels));
  }, [panels]);

  const togglePanel = (panel: keyof PanelState) => {
    setPanels(prev => ({ ...prev, [panel]: !prev[panel] }));
  };

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelsMenuRef.current && !panelsMenuRef.current.contains(e.target as Node)) {
        setPanelsOpen(false);
      }
    };
    if (panelsOpen) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [panelsOpen]);

  const handleExamSelect = async (examId: string) => {
    await setActiveExam(examId);
    const [taskList, activeExamData] = await Promise.all([getTasks(), getActiveExam()]);
    setTasks(taskList);
    setActiveExamState(activeExamData);
    setActiveTaskId(taskList[0]?.id ?? null);
    setTerminalClearKey(k => k + 1);
  };

  const handleTaskAction = async (taskId: number, action: 'start' | 'stop' | 'reset' | 'check') => {
    if (!vmStatus?.available) return;

    if (action === 'reset') {
      setTerminalMsg("Reverting VM to snapshot 'initial'...");
      setTerminalClearKey(k => k + 1);
    } else if (action === 'start' || action === 'stop') {
      setTerminalMsg('');
      setTerminalClearKey(k => k + 1);
    }

    setTasks(prev => prev.map(t =>
      t.id === taskId ? { ...t, status: TaskStatus.STARTING } : t
    ));

    let success = false;
    let newStatus = TaskStatus.IDLE;
    let checkResult: CheckResult | null = null;

    try {
      switch (action) {
        case 'start':
          success = await startVM(taskId);
          newStatus = success ? TaskStatus.RUNNING : TaskStatus.IDLE;
          break;
        case 'stop':
          success = await stopVM(taskId);
          newStatus = TaskStatus.STOPPED;
          break;
        case 'reset':
          success = await resetVM(taskId);
          newStatus = success ? TaskStatus.RUNNING : TaskStatus.IDLE;
          break;
        case 'check':
          checkResult = await checkTask(taskId);
          newStatus = TaskStatus.RUNNING;
          success = true;
          break;
      }
    } catch (e) {
      console.error(e);
      success = false;
    }

    setTasks(prev => prev.map(t =>
      t.id === taskId ? {
        ...t,
        status: newStatus,
        lastCheck: checkResult || t.lastCheck
      } : t
    ));
  };

  const handleSaveCheckpoint = async () => {
    if (checkpointSaving) return;
    setCheckpointSaving(true);
    try {
      const result = await saveCheckpoint();
      if (result.ok) {
        const cpStatus = await getCheckpointStatus();
        setCheckpointStatus(cpStatus);
      }
    } finally {
      setCheckpointSaving(false);
    }
  };

  // Only one reset at a time. Selecting a new task aborts the current reset immediately.
  const prepareAbortRef = React.useRef<AbortController | null>(null);

  const handleTaskSelect = async (taskId: number) => {
    if (taskId === activeTaskId) return;

    // Abort any in-flight reset.
    prepareAbortRef.current?.abort();

    const selectedTask = tasks.find(t => t.id === taskId);
    const isBootMenuTask = selectedTask?.node === NodeGroup.BOOT_MENU;

    setActiveTaskId(taskId);
    setTerminalClearKey(k => k + 1);
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) return { ...t, status: TaskStatus.IDLE, lastCheck: null };
      if (t.status === TaskStatus.RUNNING || t.status === TaskStatus.STARTING || t.status === TaskStatus.RESETTING || t.status === TaskStatus.STOPPED) return { ...t, status: TaskStatus.IDLE };
      return t;
    }));

    // Boot-menu VM is only started/stopped/reset by explicit button actions.
    if (isBootMenuTask) {
      setTerminalMsg('');
      return;
    }

    const controller = new AbortController();
    prepareAbortRef.current = controller;

    setTerminalMsg("Reverting VM to snapshot 'initial'...");
    setTasks(prev => prev.map(t =>
      t.id === taskId ? { ...t, status: TaskStatus.RESETTING } : t
    ));

    try {
      await prepareTask(taskId, controller.signal);
    } catch (_) { /* aborted or network error */ }

    if (controller.signal.aborted) return;
    setTerminalMsg('');
    setTerminalClearKey(k => k + 1);
    setTasks(prev => prev.map(t =>
      t.id === taskId ? { ...t, status: TaskStatus.IDLE } : t
    ));
  };


  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-900 flex-col gap-4">
        <div className="w-16 h-16 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-indigo-300 font-medium animate-pulse">Initializing RHCSA Examination Lab...</p>
      </div>
    );
  }

  // Derive node groups in stable order, deduplicated by display label
  const nodeGroups = Array.from(new Set(tasks.map(t => NODE_DISPLAY[t.node] ?? t.node)));

  return (
    <>
    <div className="h-screen flex flex-col bg-slate-900 text-slate-100 overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b border-slate-800 flex items-center justify-between px-6 bg-slate-900/50 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="p-0.5 rounded-lg">
            <RedHatIcon className="w-8 h-8" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">
            RHCSA <span className="text-red-500">Examination Lab</span>
          </h1>

          {/* Exam selector button */}
          {exams.length > 0 && (
            <button
              onClick={() => setExamModalOpen(true)}
              className="ml-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider transition-colors bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700 flex items-center gap-1"
            >
              <BookOpenIcon className="w-3 h-3" />
              {activeExam ? activeExam.title : 'Select Exam'}
            </button>
          )}
        </div>


        {/* Panels dropdown */}
        <div className="relative" ref={panelsMenuRef}>
          <button
            onClick={() => setPanelsOpen(o => !o)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors duration-150 border ${
              panelsOpen
                ? 'bg-slate-700/80 text-slate-200 border-slate-600/60'
                : 'bg-slate-800/50 text-slate-400 border-slate-700/50 hover:text-slate-200 hover:bg-slate-700/50'
            }`}
          >
            <LayoutIcon className="w-3.5 h-3.5" />
            <span>Panels</span>
            <svg className={`w-3 h-3 transition-transform duration-150 ${panelsOpen ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </button>

          {panelsOpen && (
            <div className="absolute right-0 top-full mt-1.5 w-44 bg-slate-900 border border-slate-700/60 rounded-xl shadow-2xl shadow-black/40 overflow-hidden z-50">
              <div className="p-1 flex flex-col gap-0.5">
                {([
                  { key: 'tasks',        label: 'Tasks',        icon: <ListIcon className="w-3.5 h-3.5" /> },
                  { key: 'instructions', label: 'Instructions', icon: <BookOpenIcon className="w-3.5 h-3.5" /> },
                  { key: 'terminal',     label: isBootMenu ? 'Console' : 'Terminal', icon: <TerminalIcon className="w-3.5 h-3.5" /> },
                  { key: 'results',      label: 'Results',      icon: <CheckCircleIcon className="w-3.5 h-3.5" /> },
                ] as { key: keyof PanelState; label: string; icon: React.ReactNode }[]).map(({ key, label, icon }) => (
                  <button
                    key={key}
                    onClick={() => togglePanel(key)}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-colors duration-100 ${
                      panels[key]
                        ? 'bg-slate-700/60 text-slate-100'
                        : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/60'
                    }`}
                  >
                    <span className={panels[key] ? 'text-slate-300' : 'text-slate-600'}>{icon}</span>
                    <span className="flex-1 text-left">{label}</span>
                    <span className={`w-1.5 h-1.5 rounded-full ${panels[key] ? 'bg-emerald-400' : 'bg-slate-700'}`} />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      {!vmStatus?.available ? (
        <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
          <div className="max-w-md w-full p-8 bg-slate-800 rounded-2xl border border-red-500/20 shadow-2xl flex flex-col items-center text-center">
            <AlertTriangleIcon className="w-16 h-16 text-red-500 mb-6" />
            <h2 className="text-2xl font-bold mb-4">VM Unreachable</h2>
            <p className="text-slate-400 mb-8 leading-relaxed">
              We couldn't connect to the VM. Please ensure the VM is running and reachable over the VM network.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors w-full"
            >
              Retry Connection
            </button>
          </div>
        </div>
      ) : (
        <main className="flex-1 overflow-hidden grid grid-cols-12 gap-0 p-0">
          {/* Tasks Panel */}
          {panels.tasks && (
            <section className="col-span-12 md:col-span-3 border-r border-slate-800 bg-slate-900/30 flex flex-col h-full overflow-hidden transition-all duration-300">
              <div className="p-4 border-b border-slate-800 flex items-center justify-between sticky top-0 bg-slate-900/80 backdrop-blur">
                <h3 className="font-bold flex items-center gap-2">
                  <ListIcon className="w-4 h-4 text-red-400" />
                  Task Registry
                </h3>
                <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-400">{tasks.length} Total</span>
              </div>
              <div className="flex-1 overflow-y-auto scrollbar-thin tasks-panel-scroll" tabIndex={0}>
                <div className="p-2 flex flex-col gap-1">
                  {nodeGroups.map(group => (
                    <React.Fragment key={group}>
                      <NodeGroupHeader group={group} count={tasks.filter(t => (NODE_DISPLAY[t.node] ?? t.node) === group).length} />
                      {tasks.filter(t => (NODE_DISPLAY[t.node] ?? t.node) === group).map(task => (
                        <TaskItem
                          key={task.id}
                          task={task}
                          active={activeTaskId === task.id}
                          onClick={() => handleTaskSelect(task.id)}
                        />
                      ))}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* Core Workflow Area */}
          <div className={`col-span-12 flex flex-col h-full overflow-hidden ${panels.tasks ? 'md:col-span-9' : 'md:col-span-12'}`}>
            <div ref={workAreaRef} className="flex-1 flex flex-col overflow-hidden">

              {/* Instructions Panel */}
              {panels.instructions && (
                <section
                  style={{ height: `${instrPct}%`, minHeight: 0 }}
                  className="border-b border-slate-800 p-6 overflow-y-auto bg-slate-900 flex flex-col shrink-0"
                  tabIndex={0}
                >
                  {activeTask ? (
                    <div className="animate-panel-enter-active">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <span className="px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20 text-xs font-bold font-mono">
                            TASK {activeTask.id}
                          </span>
                          <h2 className="text-2xl font-bold">{activeTask.title}</h2>
                        </div>
                        <div className="flex items-center gap-2">
                          <ActionButton
                            label="Start"
                            icon={<PlayIcon className="w-4 h-4" />}
                            onClick={() => handleTaskAction(activeTask.id, 'start')}
                            disabled={activeTask.status === TaskStatus.RUNNING || activeTask.status === TaskStatus.STARTING || activeTask.status === TaskStatus.RESETTING}
                            variant="green"
                          />
                          <ActionButton
                            label="Stop"
                            icon={<SquareIcon className="w-4 h-4" />}
                            onClick={() => handleTaskAction(activeTask.id, 'stop')}
                            disabled={activeTask.status !== TaskStatus.RUNNING}
                            variant="red"
                          />
                          <ActionButton
                            label="Reset"
                            icon={<RotateCcwIcon className="w-4 h-4" />}
                            onClick={() => handleTaskAction(activeTask.id, 'reset')}
                            variant="blue"
                          />
                        </div>
                      </div>
                      <div className="bg-slate-800/50 p-5 rounded-xl border border-slate-700">
                        <Instructions text={activeTask.instructions} />
                      </div>
                      <div className="mt-6 flex justify-end">
                        <VerifyButton
                          onClick={() => handleTaskAction(activeTask.id, 'check')}
                          disabled={activeTask.status !== TaskStatus.RUNNING}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center text-slate-400 italic">
                      Select a task from the list to begin
                    </div>
                  )}
                </section>
              )}

              {/* Horizontal resize handle — only when both instructions and bottom row are visible */}
              {panels.instructions && (panels.terminal || panels.results) && (
                <div
                  onPointerDown={startVertDrag}
                  className="h-px shrink-0 bg-slate-700/60 hover:bg-indigo-500/60 cursor-row-resize transition-colors duration-150 group relative z-10 flex items-center justify-center"
                >
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                    <span className="block w-6 h-[2px] rounded-full bg-indigo-400/70" />
                  </div>
                </div>
              )}

              {/* Middle Section: Terminal/Console and Results */}
              <div className="flex overflow-hidden" style={{ flex: 1, minHeight: 0 }}>
                {/* Terminal / Console Panel */}
                {panels.terminal && (
                  <section
                    className="h-full p-4 flex flex-col bg-slate-900/50 overflow-hidden border-r border-slate-800"
                    style={{ width: panels.results ? '66%' : '100%', minWidth: 0 }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-300 flex items-center gap-2">
                        <TerminalIcon className="w-3 h-3" />
                        {isBootMenu ? 'VNC Console' : 'Live Terminal'}
                      </h4>
                      {activeTask?.status === TaskStatus.RUNNING && (
                        <div className="flex items-center gap-1.5">
                          <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
                          <span className="text-[10px] text-green-500 font-bold uppercase">Online</span>
                        </div>
                      )}
                    </div>
                    {isBootMenu ? (
                      vncStatus?.available ? (
                        <VncPanel
                          key={terminalClearKey}
                          wsPort={vncStatus.ws_port}
                          hostname={window.location.hostname}
                          vmHostname="boot-menu-001"
                        />
                      ) : (
                        <div className="flex-1 flex items-center justify-center text-slate-300 text-xs gap-2">
                          <div className="w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                          Waiting for VNC console…
                        </div>
                      )
                    ) : (
                      <Terminal activeTask={activeTask} clearKey={terminalClearKey} statusMsg={terminalMsg} />
                    )}
                  </section>
                )}

                {/* Results Panel */}
                {panels.results && (
                  <section
                    className="h-full flex flex-col bg-slate-900/30 overflow-y-auto scrollbar-thin border-l border-slate-800"
                    style={{ flex: 1, minWidth: 0 }}
                    tabIndex={0}
                  >
                    <div className="p-4 border-b border-slate-800 sticky top-0 bg-slate-900/80 backdrop-blur z-10 flex items-center justify-between">
                      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-300 flex items-center gap-2">
                        <CheckCircleIcon className="w-3 h-3" />
                        Validation Results
                      </h4>
                    </div>
                    <div className="p-4">
                      {activeTask?.lastCheck ? (
                        <div className="space-y-4 animate-panel-enter-active">
                          <div className={`p-4 rounded-xl border flex flex-col gap-1 ${
                            activeTask.lastCheck.status === 'PASS'
                              ? 'bg-green-500/10 border-green-500/20 text-green-400'
                              : 'bg-red-500/10 border-red-500/20 text-red-400'
                          }`}>
                            <div className="flex items-center justify-between font-bold">
                              <span>Result: {activeTask.lastCheck.status}</span>
                              <span className="text-[10px] opacity-70">
                                {new Date(activeTask.lastCheck.timestamp).toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="text-sm opacity-90">{activeTask.lastCheck.summary}</p>
                          </div>
                          <div className="space-y-2">
                            {activeTask.lastCheck.details.map((detail, idx) => (
                              <div key={idx} className="flex items-start gap-3 p-3 rounded-lg bg-slate-800 border border-slate-700/50">
                                <div className={`mt-0.5 p-0.5 rounded-full ${detail.passed ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'}`}>
                                  {detail.passed ? (
                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                                  ) : (
                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
                                  )}
                                </div>
                                <div className="flex-1">
                                  <div className="text-xs font-bold text-slate-200">{detail.name}</div>
                                  <div className="text-[10px] text-slate-300 leading-tight">{detail.message}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-400 gap-2">
                          <CheckCircleIcon className="w-8 h-8 opacity-20" />
                          <p className="text-xs italic">No validation performed yet.</p>
                        </div>
                      )}
                    </div>
                  </section>
                )}
              </div>
            </div>
          </div>
        </main>
      )}
    </div>

      {/* Exam Selection Modal */}
      {examModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setExamModalOpen(false)}>
          <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
              <div className="flex items-center gap-2">
                <BookOpenIcon className="w-5 h-5 text-red-500" />
                <h2 className="text-base font-bold text-slate-100 tracking-tight">Select Exam</h2>
              </div>
              <button onClick={() => setExamModalOpen(false)} className="text-slate-300 hover:text-slate-100 transition-colors text-lg leading-none">&times;</button>
            </div>
            {/* Exam list */}
            <div className="p-4 flex flex-col gap-3 max-h-[60vh] overflow-y-auto">
              {exams.map(exam => {
                const isActive = activeExam?.id === exam.id;
                return (
                  <button
                    key={exam.id}
                    onClick={() => { handleExamSelect(exam.id); setExamModalOpen(false); }}
                    className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                      isActive
                        ? 'bg-red-600/15 border-red-500/40 text-slate-100'
                        : 'bg-slate-800/60 border-slate-700 text-slate-300 hover:bg-slate-800 hover:border-slate-500'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-sm">{exam.title}</span>
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${isActive ? 'bg-red-500/20 text-red-400' : 'bg-slate-700 text-slate-400'}`}>
                        {isActive ? 'Active' : `${exam.task_count} tasks`}
                      </span>
                    </div>
                    {exam.description && (
                      <p className="text-xs text-slate-400 leading-relaxed">{exam.description}</p>
                    )}
                    {!isActive && (
                      <p className="text-[10px] text-slate-400 mt-1">{exam.task_count} task{exam.task_count !== 1 ? 's' : ''}</p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

// Sub-components
const NODE_DISPLAY: Record<string, string> = {
  'standard':  'Node 1',
  'lvm':       'Node 2',
  'boot-menu': 'Node 2',
};

const NodeGroupHeader: React.FC<{ group: string, count: number }> = ({ group, count }) => (
  <div className="px-3 py-2 mt-4 mb-1 flex items-center justify-between">
    <span className="text-[10px] font-black tracking-widest text-slate-400 uppercase">{NODE_DISPLAY[group] ?? group}</span>
    <span className="w-4 h-4 flex items-center justify-center bg-slate-800 text-[9px] font-bold text-slate-300 rounded-full">{count}</span>
  </div>
);

const TaskItem: React.FC<{ task: Task, active: boolean, onClick: () => void }> = ({ task, active, onClick }) => (
  <button
    onClick={onClick}
    className={`w-full text-left p-3 rounded-lg flex items-center gap-3 transition-all ${
      active
        ? 'bg-red-600/10 border border-red-500/30 text-red-100 shadow-md shadow-red-600/5'
        : 'hover:bg-slate-800/50 border border-transparent text-slate-400 hover:text-slate-300'
    }`}
  >
    <div className={`flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-md font-mono text-[10px] font-bold ${
      active ? 'bg-red-600 text-white' : 'bg-slate-800 text-slate-300'
    }`}>
      {task.id < 10 ? `0${task.id}` : task.id}
    </div>
    <div className="flex-1 min-w-0">
      <div className="text-sm font-semibold truncate leading-tight">{task.title}</div>
      <div className="flex items-center gap-2 mt-1">
        <StatusBadge status={task.status} />
        {task.lastCheck && (
          <div className={`w-1.5 h-1.5 rounded-full ${task.lastCheck.status === 'PASS' ? 'bg-green-500' : 'bg-red-500'}`} />
        )}
      </div>
    </div>
  </button>
);

const StatusBadge: React.FC<{ status: TaskStatus }> = ({ status }) => {
  const styles = {
    [TaskStatus.IDLE]: 'text-slate-400',
    [TaskStatus.RESETTING]: 'text-blue-400 animate-pulse',
    [TaskStatus.RUNNING]: 'text-green-500',
    [TaskStatus.STOPPED]: 'text-amber-500',
    [TaskStatus.STARTING]: 'text-red-400 animate-pulse'
  };

  return (
    <span className={`text-[9px] font-black uppercase tracking-widest ${styles[status]}`}>
      {status}
    </span>
  );
};

const ACTION_RAIN_TICK = 5;

// slate-900 = #0f172a
const SLATE9 = '#0f172a';
const FADE   = 'rgba(15,23,42,0.22)';

const ACTION_PALETTE = {
  green: {
    bg:        SLATE9,
    head:      'rgba(74,222,128,0.75)',   // green-400
    sub:       'rgba(34,197,94,0.42)',    // green-500
    highlight: 'rgba(187,247,208,0.88)', // green-200
    border:    'border-green-700/40 group-hover:border-green-500/60',
    glow:      'rgba(74,222,128,0.16)',
    text:      'text-green-400 group-hover:text-green-300',
    dimText:   'text-slate-600',
    dimBorder: 'border-slate-700/30',
    fade:      FADE,
  },
  red: {
    bg:        SLATE9,
    head:      'rgba(248,113,113,0.75)',  // red-400
    sub:       'rgba(239,68,68,0.42)',    // red-500
    highlight: 'rgba(254,202,202,0.88)', // red-200
    border:    'border-red-700/40 group-hover:border-red-500/60',
    glow:      'rgba(248,113,113,0.16)',
    text:      'text-red-400 group-hover:text-red-300',
    dimText:   'text-slate-600',
    dimBorder: 'border-slate-700/30',
    fade:      FADE,
  },
  blue: {
    bg:        SLATE9,
    head:      'rgba(148,163,184,0.75)',  // slate-400
    sub:       'rgba(100,116,139,0.42)',  // slate-500
    highlight: 'rgba(203,213,225,0.88)', // slate-300
    border:    'border-slate-600/40 group-hover:border-slate-500/60',
    glow:      'rgba(148,163,184,0.16)',
    text:      'text-slate-300 group-hover:text-slate-200',
    dimText:   'text-slate-600',
    dimBorder: 'border-slate-700/30',
    fade:      FADE,
  },
} as const;

const ActionButton: React.FC<{
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant: 'green' | 'red' | 'blue';
}> = ({ label, icon, onClick, disabled, variant }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const btnRef    = useRef<HTMLButtonElement>(null);
  const frameRef  = useRef<number>(0);
  const tickRef   = useRef<number>(0);
  const pal       = ACTION_PALETTE[variant];

  useEffect(() => {
    const canvas = canvasRef.current;
    const btn    = btnRef.current;
    if (!canvas || !btn) return;

    const FONT = 8;
    const W    = btn.offsetWidth;
    const H    = btn.offsetHeight;
    canvas.width  = W;
    canvas.height = H;

    const ctx  = canvas.getContext('2d')!;
    const cols = Math.floor(W / FONT);

    const drops = Array.from({ length: cols }, () => ({
      y:         Math.random() * -(H / FONT) * 2,
      speed:     0.10 + Math.random() * 0.16,
      highlight: Math.random() < 0.15,
      hlTimer:   Math.floor(Math.random() * 100),
    }));

    const draw = () => {
      tickRef.current++;
      if (tickRef.current % ACTION_RAIN_TICK !== 0) {
        frameRef.current = requestAnimationFrame(draw);
        return;
      }

      ctx.fillStyle = pal.fade;
      ctx.fillRect(0, 0, W, H);
      ctx.font = `${FONT}px "Courier New", monospace`;

      drops.forEach((col, i) => {
        const px = i * FONT;
        const py = col.y * FONT;

        col.hlTimer--;
        if (col.hlTimer <= 0) {
          col.highlight = Math.random() < 0.15;
          col.hlTimer   = 50 + Math.floor(Math.random() * 100);
        }

        const ch = CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)];

        if (disabled) {
          ctx.fillStyle = 'rgba(50,50,50,0.5)';
          ctx.fillText(ch, px, py);
        } else if (col.highlight) {
          ctx.fillStyle = pal.highlight;
          ctx.fillText(ch, px, py);
          if (py > FONT) {
            ctx.fillStyle = pal.head;
            ctx.fillText(CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)], px, py - FONT);
          }
        } else {
          ctx.fillStyle = pal.head;
          ctx.fillText(ch, px, py);
          if (py > FONT) {
            ctx.fillStyle = pal.sub;
            ctx.fillText(CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)], px, py - FONT);
          }
        }

        col.y += col.speed;
        if (py > H + FONT * 5 && Math.random() > 0.97) {
          col.y     = Math.random() * -(H / FONT);
          col.speed = 0.10 + Math.random() * 0.16;
        }
      });

      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameRef.current);
  }, [disabled, variant]);

  return (
    <button
      ref={btnRef}
      onClick={onClick}
      disabled={disabled}
      className="relative overflow-hidden flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold disabled:cursor-not-allowed transition-all duration-200 hover:-translate-y-px group"
      style={{ background: pal.bg }}
    >
      <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />

      {/* vignette */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#0f172a]/65 via-[#0f172a]/15 to-[#0f172a]/65 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#0f172a]/50 via-transparent to-[#0f172a]/50 pointer-events-none" />

      {/* border */}
      <div className={`absolute inset-0 rounded-lg border pointer-events-none transition-colors duration-300 ${
        disabled ? pal.dimBorder : pal.border
      }`} />

      {/* hover glow */}
      {!disabled && (
        <div className="absolute -inset-px rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
          style={{ boxShadow: `0 0 14px 3px ${pal.glow}` }} />
      )}

      {/* content */}
      <span className={`relative z-10 shrink-0 transition-colors duration-200 ${disabled ? pal.dimText : pal.text}`}>
        {icon}
      </span>
      <span className={`relative z-10 font-mono transition-colors duration-200 ${disabled ? pal.dimText : pal.text}`}>
        {label}
      </span>
    </button>
  );
};

const CODE_CHARS = '01{}[]<>=>/\\;:+-*&|!?#%ABCDEFabcdef0110100111001011';

// How many rAF ticks to skip between canvas updates (higher = slower fall)
const RAIN_TICK_INTERVAL = 4;

const VerifyButton: React.FC<{ onClick: () => void; disabled: boolean }> = ({ onClick, disabled }) => {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const btnRef     = useRef<HTMLButtonElement>(null);
  const frameRef   = useRef<number>(0);
  const tickRef    = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    const btn    = btnRef.current;
    if (!canvas || !btn) return;

    const FONT = 11;
    const W    = btn.offsetWidth;
    const H    = btn.offsetHeight;
    canvas.width  = W;
    canvas.height = H;

    const ctx  = canvas.getContext('2d')!;
    const cols = Math.floor(W / FONT);

    // Each column: current head row, fall speed, and a random "highlight" timer
    const drops = Array.from({ length: cols }, () => ({
      y:         Math.random() * -(H / FONT) * 2,
      speed:     0.12 + Math.random() * 0.18,   // slower
      highlight: Math.random() < 0.15,           // ~15 % of columns glow bright
      hlTimer:   Math.floor(Math.random() * 120),
    }));

    const draw = () => {
      tickRef.current++;
      if (tickRef.current % RAIN_TICK_INTERVAL !== 0) {
        frameRef.current = requestAnimationFrame(draw);
        return;
      }

      // slate-900 fade — controls trail length
      ctx.fillStyle = disabled ? 'rgba(15,23,42,0.28)' : 'rgba(15,23,42,0.20)';
      ctx.fillRect(0, 0, W, H);

      ctx.font = `${FONT}px "Courier New", monospace`;

      drops.forEach((col) => {
        const x = Math.floor(col.y) * 0; // suppress lint — x is computed below
        const px = drops.indexOf(col) * FONT;
        const py = col.y * FONT;

        // Randomly flip highlight state
        col.hlTimer--;
        if (col.hlTimer <= 0) {
          col.highlight = Math.random() < 0.15;
          col.hlTimer   = 60 + Math.floor(Math.random() * 120);
        }

        const ch = CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)];

        if (disabled) {
          ctx.fillStyle = 'rgba(71,85,105,0.40)';   // slate-600
          ctx.fillText(ch, px, py);
        } else if (col.highlight) {
          // Dynamic highlight column: soft indigo-200
          ctx.fillStyle = 'rgba(199,210,254,0.88)';  // indigo-200
          ctx.fillText(ch, px, py);
          if (py > FONT) {
            ctx.fillStyle = 'rgba(129,140,248,0.72)'; // indigo-400
            ctx.fillText(
              CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)],
              px, py - FONT,
            );
          }
        } else {
          // Normal column: indigo-400
          ctx.fillStyle = 'rgba(129,140,248,0.78)';
          ctx.fillText(ch, px, py);
          // Sub-head: indigo-600
          if (py > FONT) {
            ctx.fillStyle = 'rgba(79,70,229,0.48)';
            ctx.fillText(
              CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)],
              px, py - FONT,
            );
          }
        }

        col.y += col.speed;

        if (py > H + FONT * 6 && Math.random() > 0.97) {
          col.y     = Math.random() * -(H / FONT);
          col.speed = 0.12 + Math.random() * 0.18;
        }
      });

      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameRef.current);
  }, [disabled]);

  return (
    <button
      ref={btnRef}
      onClick={onClick}
      disabled={disabled}
      className="relative overflow-hidden flex items-center gap-2.5 px-7 py-2.5 rounded-xl font-semibold text-sm disabled:cursor-not-allowed transition-all duration-200 hover:-translate-y-px group"
      style={{ background: SLATE9 }}
    >
      {/* Canvas code rain */}
      <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />

      {/* Centre vignette — keeps label readable */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#0f172a]/70 via-[#0f172a]/20 to-[#0f172a]/70 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#0f172a]/50 via-transparent to-[#0f172a]/50 pointer-events-none" />

      {/* Border */}
      <div className={`absolute inset-0 rounded-xl border pointer-events-none transition-colors duration-300 ${
        disabled ? 'border-slate-700/30' : 'border-indigo-600/40 group-hover:border-indigo-500/65'
      }`} />

      {/* Outer glow on hover */}
      {!disabled && (
        <div className="absolute -inset-px rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
          style={{ boxShadow: '0 0 18px 3px rgba(129,140,248,0.18)' }} />
      )}

      {/* Content */}
      <CheckCircleIcon className={`w-4 h-4 relative z-10 shrink-0 transition-colors duration-200 ${
        disabled ? 'text-slate-600' : 'text-indigo-300 group-hover:text-indigo-200'
      }`} />
      <span className={`relative z-10 tracking-wide font-mono transition-colors duration-200 ${
        disabled ? 'text-slate-600' : 'text-indigo-300 group-hover:text-indigo-200'
      }`}>
        Verify Task Completion
      </span>
    </button>
  );
};

export default App;
