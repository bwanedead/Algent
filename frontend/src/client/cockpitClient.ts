/**
 * Cockpit client interface for Ralph run management.
 *
 * This module provides typed functions for:
 * - Listing repos and runs
 * - Reading run artifacts (run.json, prd.json, progress.md, events.ndjson)
 * - Writing control signals (control.json)
 *
 * Currently uses a mock provider. Will be replaced with real file I/O
 * via Tauri commands or backend endpoints in later stories.
 */

import type {
  Repo,
  Run,
  RunState,
  PRD,
  ControlSignals,
  EventLogEntry,
  RunArtifacts,
} from '../types/cockpit';

// ============================================================================
// Client Interface
// ============================================================================

export interface CockpitClient {
  listRepos(): Promise<Repo[]>;
  listRuns(repoId: string): Promise<Run[]>;
  getRunState(runId: string): Promise<RunState | null>;
  getPRD(runId: string): Promise<PRD | null>;
  getProgressText(runId: string): Promise<string | null>;
  getPRDText(runId: string): Promise<string | null>;
  getControlSignals(runId: string): Promise<ControlSignals>;
  updateControlSignals(runId: string, signals: Partial<ControlSignals>): Promise<void>;
  getEvents(runId: string, limit?: number): Promise<EventLogEntry[]>;
  getRunArtifacts(runId: string): Promise<RunArtifacts>;
}

// ============================================================================
// Mock Provider
// ============================================================================

const MOCK_REPOS: Repo[] = [
  {
    id: 'algent',
    name: 'Algent',
    path: 'C:\\projects\\Algent',
  },
  {
    id: 'ralph-engine',
    name: 'Ralph Engine',
    path: 'C:\\projects\\ralph-engine',
  },
];

const MOCK_RUNS: Run[] = [
  {
    id: '2026-01-29__cockpit-3',
    repoId: 'algent',
    title: 'Ralph Cockpit UI in Algent',
    status: 'running',
    phase: 'worker',
    iteration: 3,
    createdAt: '2026-01-29T10:00:00Z',
    updatedAt: '2026-01-29T14:30:00Z',
  },
  {
    id: '2026-01-28__agent-system',
    repoId: 'algent',
    title: 'Agent System Foundation',
    status: 'completed',
    phase: 'worker',
    iteration: 12,
    createdAt: '2026-01-28T08:00:00Z',
    updatedAt: '2026-01-28T18:45:00Z',
  },
  {
    id: '2026-01-27__cli-refactor',
    repoId: 'ralph-engine',
    title: 'CLI Refactor for Control Plane',
    status: 'paused',
    phase: 'review',
    iteration: 5,
    createdAt: '2026-01-27T09:30:00Z',
    updatedAt: '2026-01-27T16:20:00Z',
  },
];

const MOCK_PRD: PRD = {
  run_id: '2026-01-29__cockpit-3',
  title: 'Ralph Cockpit UI in Algent',
  repo_context: 'Algent is a React + Vite UI with a Tauri wrapper; cockpit must be local-only and file-contract driven.',
  global_verification: [],
  loop_settings: {
    review_every_n_iterations: 4,
    steer_every_n_iterations: 8,
  },
  stories: [
    {
      id: 'S1',
      title: 'Add Cockpit entry point and view switch',
      size: 'XS',
      passes: true,
      acceptance_criteria: [
        'A cockpit button/link labeled "Cockpit" or "Ralph Cockpit" appears on the home view',
        'Clicking the cockpit entry point renders a cockpit view with a clear heading',
        'There is a way to return to the original home view without a full reload',
      ],
      verification_commands: [],
      depends_on: [],
      files_expected: ['frontend/src/App.tsx', 'frontend/src/styles/index.css'],
      notes: 'Keep changes minimal; no full routing refactor.',
    },
    {
      id: 'S2',
      title: 'Cockpit page skeleton layout',
      size: 'S',
      passes: true,
      acceptance_criteria: [
        'A dedicated cockpit component renders a sidebar, main detail panel, and control/events area placeholders',
        'Cockpit layout uses existing HUD style tokens (colors/spacing/typography)',
      ],
      verification_commands: [],
      depends_on: ['S1'],
      files_expected: ['frontend/src/components/Cockpit/CockpitPage.tsx', 'frontend/src/styles/cockpit.css'],
      notes: 'Keep the layout calm and operator-focused.',
    },
    {
      id: 'S3',
      title: 'Cockpit data client interface with mock provider',
      size: 'S',
      passes: false,
      acceptance_criteria: [
        'A typed client module exposes functions for listing repos, listing runs, reading run artifacts, and writing control signals',
        'Cockpit consumes this client and renders mock run data in the UI',
      ],
      verification_commands: [],
      depends_on: ['S2'],
      files_expected: ['frontend/src/client/cockpitClient.ts', 'frontend/src/types/cockpit.ts'],
      notes: 'Keep mock data aligned with Ralph file contracts.',
    },
  ],
};

const MOCK_CONTROL_SIGNALS: Record<string, ControlSignals> = {
  '2026-01-29__cockpit-3': {
    pause: false,
    stop_soft: false,
    stop_hard: false,
    skip_iteration: false,
    review_now: false,
    review_next: false,
  },
};

const MOCK_EVENTS: EventLogEntry[] = [
  {
    timestamp: '2026-01-29T14:30:15Z',
    level: 'INFO',
    message: 'Worker iteration 3 started',
    phase: 'worker',
    iteration: 3,
  },
  {
    timestamp: '2026-01-29T14:30:10Z',
    level: 'INFO',
    message: 'Story S2 marked as PASS',
    phase: 'worker',
    iteration: 2,
  },
  {
    timestamp: '2026-01-29T14:25:45Z',
    level: 'INFO',
    message: 'Worker iteration 2 started',
    phase: 'worker',
    iteration: 2,
  },
  {
    timestamp: '2026-01-29T14:20:30Z',
    level: 'INFO',
    message: 'Story S1 marked as PASS',
    phase: 'worker',
    iteration: 1,
  },
  {
    timestamp: '2026-01-29T14:15:00Z',
    level: 'INFO',
    message: 'Run initialized',
    phase: 'prep',
    iteration: 0,
  },
];

const MOCK_PROGRESS_TEXT = `# Progress — 2026-01-29__cockpit-3

(append entries per iteration)

- Iteration: 1
- Story: S1 Add Cockpit entry point and view switch
- Result: PASS
- Files changed: frontend/src/App.tsx, frontend/src/styles/index.css
- Commands run: None (manual verification via code inspection)
- Notes:
  - Added showCockpit state toggle to App.tsx
  - Added "Cockpit" button to header actions
  - All acceptance criteria met

---

- Iteration: 2
- Story: S2 Cockpit page skeleton layout
- Result: PASS
- Files changed: frontend/src/components/Cockpit/CockpitPage.tsx, frontend/src/styles/cockpit.css
- Commands run: None (manual verification via code inspection)
- Notes:
  - Created CockpitPage.tsx with three-column grid layout
  - Created cockpit.css using existing HUD style tokens
  - All acceptance criteria met

---
`;

const MOCK_PRD_TEXT = `# PRD: Ralph Cockpit

## Context
Ralph Engine runs are currently driven by CLI commands and manual inspection of files in \`ralph/runs/<run_id>/\`. This is slow, error-prone, and difficult to operate across multiple repos. We need a dedicated cockpit inside Algent that can observe and control runs using the file-based contracts Ralph Engine already uses.

## Goal
Deliver a local, calm operator cockpit in the Algent UI that lists Ralph runs, inspects their state/artifacts, and writes control signals to guide execution.
`;

class MockCockpitClient implements CockpitClient {
  async listRepos(): Promise<Repo[]> {
    // Simulate async delay
    await new Promise((resolve) => setTimeout(resolve, 100));
    return MOCK_REPOS;
  }

  async listRuns(repoId: string): Promise<Run[]> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    return MOCK_RUNS.filter((run) => run.repoId === repoId);
  }

  async getRunState(runId: string): Promise<RunState | null> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    const run = MOCK_RUNS.find((r) => r.id === runId);
    if (!run) return null;

    return {
      runId: run.id,
      status: run.status,
      phase: run.phase,
      iteration: run.iteration,
      createdAt: run.createdAt,
      updatedAt: run.updatedAt,
    };
  }

  async getPRD(runId: string): Promise<PRD | null> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (runId === MOCK_PRD.run_id) {
      return MOCK_PRD;
    }
    return null;
  }

  async getProgressText(runId: string): Promise<string | null> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (runId === '2026-01-29__cockpit-3') {
      return MOCK_PROGRESS_TEXT;
    }
    return null;
  }

  async getPRDText(runId: string): Promise<string | null> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (runId === '2026-01-29__cockpit-3') {
      return MOCK_PRD_TEXT;
    }
    return null;
  }

  async getControlSignals(runId: string): Promise<ControlSignals> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    return (
      MOCK_CONTROL_SIGNALS[runId] || {
        pause: false,
        stop_soft: false,
        stop_hard: false,
        skip_iteration: false,
        review_now: false,
        review_next: false,
      }
    );
  }

  async updateControlSignals(runId: string, signals: Partial<ControlSignals>): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    const current = MOCK_CONTROL_SIGNALS[runId] || {};
    MOCK_CONTROL_SIGNALS[runId] = { ...current, ...signals };
  }

  async getEvents(runId: string, limit: number = 50): Promise<EventLogEntry[]> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (runId === '2026-01-29__cockpit-3') {
      return MOCK_EVENTS.slice(0, limit);
    }
    return [];
  }

  async getRunArtifacts(runId: string): Promise<RunArtifacts> {
    const [runState, prd, prdText, progressText, controlSignals, events] = await Promise.all([
      this.getRunState(runId),
      this.getPRD(runId),
      this.getPRDText(runId),
      this.getProgressText(runId),
      this.getControlSignals(runId),
      this.getEvents(runId),
    ]);

    return {
      runState: runState || undefined,
      prd: prd || undefined,
      prdText: prdText || undefined,
      progressText: progressText || undefined,
      controlSignals,
      events,
    };
  }
}

// ============================================================================
// Default Export
// ============================================================================

export const cockpitClient: CockpitClient = new MockCockpitClient();
