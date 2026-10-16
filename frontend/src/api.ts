export type AuthSession = {
  authenticated: boolean;
  login_required: boolean;
  configured: boolean;
  needs_configuration: boolean;
  username?: string | null;
  public_read_only?: boolean;
  admin_authenticated?: boolean;
  admin_username?: string | null;
  admin_configured?: boolean;
  admin_needs_configuration?: boolean;
};


export type DemoStoreStatus = {
  session_exists: boolean;
  sample_rows: number;
  loss_records: number;
  results: number;
  pending_samples: number;
};

export type DemoStatus = {
  enabled: boolean;
  seeded: boolean;
  session_id: string;
  seed: number;
  sample_rate_hz: number;
  duration_seconds: number;
  sample_rows: number;
  sensor_1_sample_count: number;
  sensor_2_sample_count: number;
  window_count: number;
  controlled_gap: { sensor: number; from_index: number; to_index: number };
  offline_windows: number[];
  dataset_file: string;
  dataset_file_exists: boolean;
  bundled_fixture_available: boolean;
  cloud: DemoStoreStatus;
  device: DemoStoreStatus;
  notice: string;
};

export type DemoSeedResponse = {
  ok: boolean;
  already_present: boolean;
  enabled: boolean;
  session_id: string;
  seed: number;
  sample_rate_hz: number;
  duration_seconds: number;
  sample_rows: number;
  sensor_1_sample_count: number;
  sensor_2_sample_count: number;
  loss_records: number;
  window_count: number;
  online_windows: number;
  offline_windows: number;
  sha256: string;
  dataset_file: string;
  cloud: { sample_rows: number; loss_records: number; results: number; pending_samples: number };
  device: { sample_rows: number; loss_records: number; results: number; pending_samples: number };
  notice: string;
};

export type Summary = {
  generated_at: number;
  service: { name: string; version: string };
  device: {
    available: boolean;
    mode: string;
    samples?: number | null;
    losses?: number | null;
    sessions?: number | null;
    results?: number | null;
    backlog?: number | null;
    events?: number | null;
    last_sample_at?: number | null;
    last_event_at?: number | null;
    latest_session_id?: string | null;
  };
  cloud: {
    samples: number;
    losses: number;
    sessions: number;
    results: number;
    events: number;
    last_sample_at: number | null;
    last_event_at: number | null;
    latest_session_id: string | null;
  };
  data_notice: string;
};

export type SessionRow = {
  session_id: string;
  samples_cloud: number;
  samples_device: number | null;
  losses: number;
  results: number;
  latest_sample_index: number | null;
  created_at: number | null;
  last_seen_at: number | null;
  ended: boolean;
};

export type WindowResult = {
  session_id: string;
  window_index: number;
  start_index: number;
  end_index: number;
  missing_1: number;
  missing_2: number;
  complete: boolean;
  mean: { sensor_1?: (number | null)[]; sensor_2?: (number | null)[] };
  min: { sensor_1?: (number | null)[]; sensor_2?: (number | null)[] };
  max: { sensor_1?: (number | null)[]; sensor_2?: (number | null)[] };
  magnitude: number | null;
  heart_rate: number | null;
  mode: 'online' | 'offline';
};

export type LossRecord = {
  sensor: number;
  from_index: number;
  to_index: number | null;
  reason: string;
  recorded_at?: number;
  source: 'cloud' | 'device';
};

export type IntegrityEvent = {
  id: string;
  session_id: string | null;
  sensor: number | null;
  sample_index: number | null;
  event_type: string;
  detail: string;
  created_at: number;
  source: 'cloud' | 'device';
};

export type ResourceSnapshot = {
  observed_at: number;
  scope: string;
  cpu_percent: number;
  memory: { total_bytes: number; used_bytes: number; percent: number };
  disk: { total_bytes: number; used_bytes: number; free_bytes: number; percent: number };
  pid: number;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string; message?: string };
      detail = body.detail || body.message || detail;
    } catch {
      // Keep the status-based message if the server did not return JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const getAuthSession = () => apiFetch<AuthSession>('/api/auth/session');
export const getSummary = () => apiFetch<Summary>('/api/dashboard/summary');
export const getSessions = (search = '') =>
  apiFetch<{ items: SessionRow[]; total: number; limit: number; offset: number }>(
    `/api/dashboard/sessions?limit=100&search=${encodeURIComponent(search)}`,
  );
export const getResults = (sessionId: string) =>
  apiFetch<{ items: WindowResult[]; total: number }>(
    `/api/dashboard/sessions/${encodeURIComponent(sessionId)}/results?limit=1000`,
  );
export const getLosses = (sessionId: string) =>
  apiFetch<LossRecord[]>(`/api/dashboard/sessions/${encodeURIComponent(sessionId)}/losses`);
export const getEvents = () => apiFetch<IntegrityEvent[]>('/api/dashboard/events?limit=100');
export const getResources = () => apiFetch<ResourceSnapshot>('/api/dashboard/resources');

export const getDemoStatus = () => apiFetch<DemoStatus>('/api/dashboard/demo/status');
export const seedDemoDataset = () => apiFetch<DemoSeedResponse>('/api/dashboard/demo/seed', { method: 'POST' });
export const resetDemoDataset = () => apiFetch<{ ok: boolean; session_id: string; notice: string }>('/api/dashboard/demo/reset', { method: 'POST' });


export type AdminDataset = {
  dataset_id: string;
  name: string;
  description: string;
  source_type: 'hardware_export' | 'external_dataset' | 'synthetic_test';
  source_filename: string;
  file_format: 'CSV' | 'JSONL';
  sha256: string;
  sample_count: number;
  loss_count: number;
  result_count: number;
  session_count: number;
  session_ids: string[];
  imported_at: number;
  imported_by: string;
};

export type AdminOverview = {
  dataset_count: number;
  session_count: number;
  sample_count: number;
  loss_count: number;
  result_count: number;
  datasets: AdminDataset[];
  notice: string;
};

export type AdminDatasetPreview = {
  dataset_id: string;
  session_id: string;
  samples: Array<{ sensor: number; index: number; values: number[]; received_at: number }>;
  results: WindowResult[];
  losses: number;
  notice: string;
};

export type AdminImportRequest = {
  name: string;
  description: string;
  source_type: AdminDataset['source_type'];
  filename: string;
  content: string;
};

export const getAdminOverview = () => apiFetch<AdminOverview>('/api/admin/overview');
export const importAdminDataset = (payload: AdminImportRequest) =>
  apiFetch<{ ok: boolean; dataset: AdminDataset; inserted_samples: number; inserted_losses: number; processing_results: number; sha256: string; notice: string }>(
    '/api/admin/datasets/import', { method: 'POST', body: JSON.stringify(payload) },
  );
export const getAdminDatasetPreview = (datasetId: string, sessionId: string) =>
  apiFetch<AdminDatasetPreview>(`/api/admin/datasets/${encodeURIComponent(datasetId)}/sessions/${encodeURIComponent(sessionId)}/preview`);
export const deleteAdminDataset = (datasetId: string) =>
  apiFetch<{ ok: boolean; deleted_sessions: number }>(`/api/admin/datasets/${encodeURIComponent(datasetId)}`, { method: 'DELETE' });
