/**
 * Type definitions for Ralph Cockpit data structures.
 * These align with Ralph Engine file contracts.
 */

export type RunStatus = 'ready' | 'running' | 'paused' | 'completed' | 'failed' | 'unknown';
export type StorySize = 'XS' | 'S' | 'M' | 'L' | 'XL';

export interface Project {
  id: string;
  name: string;
  path: string;
  adapter?: string;
}

export interface Run {
  id: string;
  title?: string | null;
  projectId?: string;
  status: RunStatus;
  phase?: string;
  iteration?: number;
  maxIterations?: number;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  finishedAt?: string;
  error?: string | null;
  storyCounts?: {
    total: number;
    passed: number;
  };
  artifacts?: {
    hasProgress?: boolean;
    hasSummary?: boolean;
    hasEvents?: boolean;
    hasControl?: boolean;
    transcriptCount?: number;
  };
  isTemplateRun?: boolean;
}

export interface RunState {
  runId: string;
  status: RunStatus;
  phase?: string;
  iteration?: number;
  maxIterations?: number;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  finishedAt?: string;
  error?: string | null;
  gitBranch?: string;
  gitBaseBranch?: string;
  gitBaseCommit?: string;
}

export interface Story {
  id: string;
  title: string;
  size: StorySize;
  passes: boolean;
  acceptance_criteria: string[];
  verification_commands: string[];
  depends_on: string[];
  files_expected: string[];
  notes?: string;
}

export interface PRD {
  run_id: string;
  title: string;
  repo_context?: string;
  global_verification: string[];
  loop_settings?: {
    review_every_n_iterations?: number;
    steer_every_n_iterations?: number;
    global_verify_every_n_stories?: number;
  };
  stories: Story[];
}

export interface ControlSignals {
  pause?: boolean;
  stop_soft?: boolean;
  stop_hard?: boolean;
  skip_iteration?: boolean;
  review_now?: boolean;
  review_next?: boolean;
}

export interface EventLogEntry {
  timestamp: string;
  level: string;
  message: string;
  phase?: string;
  iteration?: number;
  type?: string;
  data?: Record<string, unknown>;
}

export interface RunArtifacts {
  runState?: RunState;
  prd?: PRD;
  progressText?: string;
  summaryText?: string;
  controlSignals?: ControlSignals;
  events?: EventLogEntry[];
}

export interface DoctorResult {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
}

export interface LiveFeed {
  phase: string | null;
  iteration: number | null;
  stdout: string[];
  stderr: string[];
}
