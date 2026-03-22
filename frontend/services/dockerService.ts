import { VMStatus, Task, CheckResult, VncStatus, Exam } from '../types';

const API = ''; // same origin when served from Flask

export const getVmStatus = async (): Promise<VMStatus> => {
  const res = await fetch(`${API}/api/vm/status`);
  const data = await res.json();
  return data as VMStatus;
};

export const getTasks = async (): Promise<Task[]> => {
  const res = await fetch(`${API}/api/tasks`);
  const data = await res.json();
  return data as Task[];
};

export const startVM = async (taskId: number): Promise<boolean> => {
  const res = await fetch(`${API}/api/task/${taskId}/start`, { method: 'POST' });
  const data = await res.json();
  return res.ok && data?.ok === true;
};

export const stopVM = async (taskId: number): Promise<boolean> => {
  const res = await fetch(`${API}/api/task/${taskId}/stop`, { method: 'POST' });
  const data = await res.json();
  return res.ok && data?.ok === true;
};

export const resetVM = async (taskId: number): Promise<boolean> => {
  const res = await fetch(`${API}/api/task/${taskId}/reset`, { method: 'POST' });
  const data = await res.json();
  return res.ok && data?.ok === true;
};

export const checkTask = async (taskId: number): Promise<CheckResult> => {
  const res = await fetch(`${API}/api/task/${taskId}/check`, { method: 'POST' });
  const data = await res.json();
  return data as CheckResult;
};

export const getExams = async (): Promise<Exam[]> => {
  const res = await fetch(`${API}/api/exams`);
  const data = await res.json();
  return data as Exam[];
};

export const getActiveExam = async (): Promise<Exam> => {
  const res = await fetch(`${API}/api/exam/active`);
  const data = await res.json();
  return data as Exam;
};

export const setActiveExam = async (examId: string): Promise<boolean> => {
  const res = await fetch(`${API}/api/exam/set/${examId}`, { method: 'POST' });
  const data = await res.json();
  return res.ok && data?.ok === true;
};

export const getVncStatus = async (): Promise<VncStatus> => {
  const res = await fetch(`${API}/api/vnc/status`);
  const data = await res.json();
  return data as VncStatus;
};

export const prepareTask = async (taskId: number, signal?: AbortSignal): Promise<boolean> => {
  const res = await fetch(`${API}/api/task/${taskId}/prepare`, { method: 'POST', signal });
  const data = await res.json();
  return res.ok && data?.ok === true;
};

export const saveCheckpoint = async (hostname?: string): Promise<{ ok: boolean; error?: string }> => {
  const res = await fetch(`${API}/api/vm/save-checkpoint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(hostname ? { hostname } : {}),
  });
  return res.json();
};

export const getCheckpointStatus = async (): Promise<Record<string, boolean>> => {
  const res = await fetch(`${API}/api/vm/checkpoint-status`);
  return res.json();
};
