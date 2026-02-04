/**
 * Cockpit client interface for Ralph run management (backend-backed).
 */

import type {
  Project,
  Run,
  RunState,
  PRD,
  ControlSignals,
  EventLogEntry,
  RunArtifacts,
  DoctorResult,
  LiveFeed,
} from '../types/cockpit';

const API_BASE = 'http://127.0.0.1:43145';

export interface CockpitClient {
  listProjects(): Promise<Project[]>;
  addProject(path: string, name?: string): Promise<Project>;
  listRuns(projectId: string): Promise<Run[]>;
  getRunState(projectId: string, runId: string): Promise<RunState | null>;
  getPRD(projectId: string, runId: string): Promise<PRD | null>;
  getProgressText(projectId: string, runId: string): Promise<string | null>;
  getSummaryText(projectId: string, runId: string): Promise<string | null>;
  getControlSignals(projectId: string, runId: string): Promise<ControlSignals>;
  updateControlSignals(projectId: string, runId: string, signals: Partial<ControlSignals>): Promise<void>;
  getEvents(projectId: string, runId: string, limit?: number): Promise<EventLogEntry[]>;
  getRunArtifacts(projectId: string, runId: string): Promise<RunArtifacts>;
  runDoctor(projectId: string, runId: string): Promise<DoctorResult>;
  getLiveFeed(projectId: string, runId: string, limit?: number): Promise<LiveFeed>;
  getLogTail(
    projectId: string,
    runId: string,
    phase: string,
    iteration: number,
    stream: 'stdout' | 'stderr',
    limit?: number,
  ): Promise<{ lines: string[] }>;
}

const requestJson = async <T>(path: string, options?: RequestInit): Promise<T> => {
  try {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Backend unreachable. Is the Algent backend running?');
    }
    throw error;
  }
};

const requestText = async (path: string): Promise<string> => {
  try {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.text();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Backend unreachable. Is the Algent backend running?');
    }
    throw error;
  }
};

class BackendCockpitClient implements CockpitClient {
  async listProjects(): Promise<Project[]> {
    const data = await requestJson<{ projects: Project[] }>('/cockpit/projects');
    return data.projects;
  }

  async addProject(path: string, name?: string): Promise<Project> {
    const data = await requestJson<{ project: Project }>('/cockpit/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, name }),
    });
    return data.project;
  }

  async listRuns(projectId: string): Promise<Run[]> {
    const data = await requestJson<{ runs: Run[] }>(`/cockpit/projects/${projectId}/runs`);
    return data.runs.map((run) => ({ ...run, projectId }));
  }

  async getRunState(projectId: string, runId: string): Promise<RunState | null> {
    const data = await requestJson<{ run: RunState | null }>(
      `/cockpit/runs/${projectId}/${runId}`,
    );
    return data.run;
  }

  async getPRD(projectId: string, runId: string): Promise<PRD | null> {
    const data = await requestJson<{ prd: PRD | null }>(
      `/cockpit/runs/${projectId}/${runId}/prd`,
    );
    return data.prd;
  }

  async getProgressText(projectId: string, runId: string): Promise<string | null> {
    const text = await requestText(`/cockpit/runs/${projectId}/${runId}/progress`);
    return text || null;
  }

  async getSummaryText(projectId: string, runId: string): Promise<string | null> {
    const text = await requestText(`/cockpit/runs/${projectId}/${runId}/summary`);
    return text || null;
  }

  async getControlSignals(projectId: string, runId: string): Promise<ControlSignals> {
    const data = await requestJson<{ control: ControlSignals }>(
      `/cockpit/runs/${projectId}/${runId}/control`,
    );
    return data.control;
  }

  async updateControlSignals(
    projectId: string,
    runId: string,
    signals: Partial<ControlSignals>,
  ): Promise<void> {
    await requestJson(`/cockpit/runs/${projectId}/${runId}/control`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(signals),
    });
  }

  async getEvents(projectId: string, runId: string, limit: number = 50): Promise<EventLogEntry[]> {
    const data = await requestJson<{ events: EventLogEntry[] }>(
      `/cockpit/runs/${projectId}/${runId}/events?limit=${limit}`,
    );
    return data.events;
  }

  async getRunArtifacts(projectId: string, runId: string): Promise<RunArtifacts> {
    const data = await requestJson<{ artifacts: RunArtifacts }>(
      `/cockpit/runs/${projectId}/${runId}/artifacts`,
    );
    return data.artifacts;
  }

  async runDoctor(projectId: string, runId: string): Promise<DoctorResult> {
    const data = await requestJson<{ doctor: DoctorResult }>(
      `/cockpit/runs/${projectId}/${runId}/doctor`,
      { method: 'POST' },
    );
    return data.doctor;
  }

  async getLiveFeed(projectId: string, runId: string, limit: number = 200): Promise<LiveFeed> {
    const data = await requestJson<{ live: LiveFeed }>(
      `/cockpit/runs/${projectId}/${runId}/live?limit=${limit}`,
    );
    return data.live;
  }

  async getLogTail(
    projectId: string,
    runId: string,
    phase: string,
    iteration: number,
    stream: 'stdout' | 'stderr',
    limit: number = 200,
  ): Promise<{ lines: string[] }> {
    const data = await requestJson<{ lines: string[] }>(
      `/cockpit/runs/${projectId}/${runId}/logs?phase=${encodeURIComponent(
        phase,
      )}&iteration=${iteration}&stream=${stream}&limit=${limit}`,
    );
    return data;
  }
}

export const cockpitClient: CockpitClient = new BackendCockpitClient();
