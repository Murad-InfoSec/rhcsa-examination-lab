import React, { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { Task, TaskStatus, NodeGroup } from '../types';

interface TerminalProps {
  activeTask: Task | null;
  clearKey?: number;
  statusMsg?: string;
}

const WELCOME = '\x1b[32mRHCSA Examination Lab Terminal\x1b[0m';
const IDLE_HINT = 'Select a task and click Start to connect to the Virtual Machine.';

const Terminal: React.FC<TerminalProps> = ({ activeTask, clearKey = 0, statusMsg = '' }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const connectedTaskIdRef = useRef<number | null>(null);
  const activeTaskRef = useRef<Task | null>(null);

  useEffect(() => {
    activeTaskRef.current = activeTask;
  }, [activeTask]);

  // ── boot xterm once ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!terminalRef.current) return;

    const term = new XTerm({
      cursorBlink: true,
      scrollback: 5000,
      theme: {
        background: '#0f172a',
        foreground: '#f8fafc',
        cursor: '#f8fafc',
        selectionBackground: '#475569',
        scrollbarSliderBackground: '#334155',
        scrollbarSliderHoverBackground: '#475569',
        scrollbarSliderActiveBackground: '#64748b',
      },
      fontFamily: 'Fira Code, monospace',
      fontSize: 14,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    fitAddon.fit();

    term.writeln(WELCOME);
    term.writeln(IDLE_HINT);
    term.write('\r\n');

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    const handleResize = () => {
      fitAddon.fit();
      const cols = term.cols;
      const rows = term.rows;
      if (socketRef.current?.connected && connectedTaskIdRef.current != null) {
        socketRef.current.emit('terminal:resize', { taskId: connectedTaskIdRef.current, cols, rows });
      }
    };
    window.addEventListener('resize', handleResize);

    term.onData((data) => {
      const currentTask = activeTaskRef.current;
      if (currentTask?.status !== TaskStatus.RUNNING) return;
      if (socketRef.current && connectedTaskIdRef.current === currentTask.id) {
        socketRef.current.emit('terminal:input', { taskId: currentTask.id, data });
      }
    });

    return () => {
      window.removeEventListener('resize', handleResize);
      term.dispose();
    };
  }, []);

  // ── clear + optional status message ─────────────────────────────────────
  // Fires when clearKey increments. Writes statusMsg if set, else the idle hint.
  useEffect(() => {
    if (clearKey === 0) return;
    const term = xtermRef.current;
    if (!term) return;
    term.clear();
    term.writeln(WELCOME);
    if (statusMsg) {
      term.writeln(`\x1b[33m${statusMsg}\x1b[0m`);
    } else {
      term.writeln(IDLE_HINT);
    }
    term.write('\r\n');
  }, [clearKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── socket: connect when task is RUNNING, disconnect otherwise ───────────
  useEffect(() => {
    const taskId = activeTask?.id ?? null;
    const running = activeTask?.status === TaskStatus.RUNNING && activeTask?.node !== NodeGroup.BOOT_MENU;

    if (!running || taskId == null) {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
      connectedTaskIdRef.current = null;
      return;
    }

    const socket = io({ path: '/socket.io', transports: ['polling'] });
    socketRef.current = socket;
    connectedTaskIdRef.current = taskId;

    socket.on('connect', () => {
      // Clear any "Reverting…" or previous content before the SSH session begins
      if (xtermRef.current) {
        xtermRef.current.clear();
        xtermRef.current.write('\r\n');
      }
      socket.emit('terminal:connect', { taskId });
      if (fitAddonRef.current) fitAddonRef.current.fit();
      if (xtermRef.current) {
        socket.emit('terminal:resize', { taskId, cols: xtermRef.current.cols, rows: xtermRef.current.rows });
        xtermRef.current.focus();
      }
    });

    socket.on('terminal:output', (payload: { taskId: number; data: string }) => {
      if (payload.taskId === taskId && xtermRef.current) {
        xtermRef.current.write(payload.data, () => { xtermRef.current?.scrollToBottom(); });
      }
    });

    socket.on('terminal:exit', (payload: { taskId: number; code: number }) => {
      if (payload.taskId === taskId && xtermRef.current) {
        xtermRef.current.writeln(`\r\n\x1b[33m[Process exited with code ${payload.code}]\x1b[0m`);
        xtermRef.current.scrollToBottom();
      }
    });

    socket.on('terminal:error', (payload: { taskId: number; message: string }) => {
      if (payload.taskId === taskId && xtermRef.current) {
        xtermRef.current.writeln(`\r\n\x1b[31m[Error] ${payload.message}\x1b[0m`);
        xtermRef.current.scrollToBottom();
      }
    });

    return () => {
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
      connectedTaskIdRef.current = null;
    };
  }, [activeTask?.id, activeTask?.status]);

  // ── fit + focus when task becomes running ────────────────────────────────
  useEffect(() => {
    if (activeTask?.status === TaskStatus.RUNNING && xtermRef.current && fitAddonRef.current) {
      fitAddonRef.current.fit();
      const cols = xtermRef.current.cols;
      const rows = xtermRef.current.rows;
      if (socketRef.current?.connected && connectedTaskIdRef.current === activeTask.id) {
        socketRef.current.emit('terminal:resize', { taskId: activeTask.id, cols, rows });
      }
      xtermRef.current.focus();
    }
  }, [activeTask?.id, activeTask?.status]);

  const isRunning = activeTask?.status === TaskStatus.RUNNING;

  return (
    <div className="flex flex-col h-full bg-slate-900 overflow-hidden rounded-b-lg border-x border-b border-slate-700 shadow-2xl">
      <div className="bg-slate-800/60 px-3 py-1 flex items-center gap-2 border-b border-slate-700/40">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/70 hover:bg-red-400 transition-colors cursor-pointer" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70 hover:bg-yellow-400 transition-colors cursor-pointer" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/70 hover:bg-green-400 transition-colors cursor-pointer" />
        </div>
        <span className="flex-1 text-center text-[10px] font-mono text-slate-300 truncate select-none">
          {activeTask ? `bash — ${activeTask.title}` : 'bash'}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-green-500' : 'bg-slate-400'}`} />
          <span className={`text-[9px] font-bold uppercase ${isRunning ? 'text-green-500' : 'text-slate-400'}`}>
            {isRunning ? 'ssh' : 'idle'}
          </span>
        </div>
      </div>
      <div ref={terminalRef} className="flex-1 w-full overflow-hidden" />
    </div>
  );
};

export default Terminal;
