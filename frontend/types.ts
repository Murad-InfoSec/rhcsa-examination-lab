
export enum TaskStatus {
  IDLE = 'idle',
  RESETTING = 'resetting',
  RUNNING = 'running',
  STOPPED = 'stopped',
  STARTING = 'starting'
}

export enum NodeGroup {
  STANDARD  = 'standard',
  LVM       = 'lvm',
  BOOT_MENU = 'boot-menu',
}

export interface CheckDetail {
  name: string;
  passed: boolean;
  message: string;
}

export interface CheckResult {
  status: 'PASS' | 'FAIL' | 'ERROR';
  summary: string;
  details: CheckDetail[];
  timestamp: string;
}

export interface Task {
  id: number;
  node: NodeGroup;
  title: string;
  instructions: string;
  status: TaskStatus;
  lastCheck: CheckResult | null;
}

export interface PanelState {
  tasks: boolean;
  instructions: boolean;
  terminal: boolean;
  results: boolean;
}

export interface VMStatus {
  available: boolean;
  scenario?: string;
  ip?: string;
  version?: string;
  error?: string;
}

export interface VncStatus {
  available: boolean;
  ws_port: number;
  vnc_port: number;
  scenario: string;
}

export interface Exam {
  id: string;
  title: string;
  description: string;
  scenario: string;
  task_count: number;
}
