/**
 * Type definitions for Ralph Cockpit data structures.
 * These align with Ralph Engine file contracts.
 */

export type RunStatus = 'ready' | 'running' | 'paused' | 'completed' | 'failed' | 'unknown';
export type StorySize = 'XS' | 'S' | 'M' | 'L' | 'XL';

export interface Repo {
  id: string;
  name: string;
  path: string;
}

export interface Run {
  id: string;
  repoId: string;
  title: string;
  status: RunStatus;
  phase?: string;
  iteration?: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface RunState {
  runId: string;
  status: RunStatus;
  phase?: string;
  iteration?: number;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
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
}

export interface RunArtifacts {
  runState?: RunState;
  prd?: PRD;
  prdText?: string;
  progressText?: string;
  controlSignals?: ControlSignals;
  events?: EventLogEntry[];
}
