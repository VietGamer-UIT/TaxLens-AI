// =============================================================================
// TaxLens-AI :: API Client
// Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
// =============================================================================
// Smart API base URL resolution (3 priorities):
//
//   P1 — NEXT_PUBLIC_API_URL env var (baked in at `next build` time)
//   P2 — Browser hostname auto-detection (Codespaces *.app.github.dev trick)
//   P3 — localhost:8000 fallback
// =============================================================================

import axios, { AxiosError } from 'axios'

// ---------------------------------------------------------------------------
// Smart base URL — resolved once at module load time (client side)
// ---------------------------------------------------------------------------
function resolveApiBase(): string {
  // P1: explicit env var — works when baked in at build time
  const fromEnv = process.env.NEXT_PUBLIC_API_URL
  if (fromEnv && fromEnv.trim() !== '') return fromEnv.trim()

  // P2: browser-based hostname detection — runs only in browser (not SSR)
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location

    // GitHub Codespaces: <name>-3000.app.github.dev → <name>-8000.app.github.dev
    if (hostname.endsWith('.app.github.dev')) {
      const backendHost = hostname.replace(/-\d+\.app\.github\.dev$/, '-8000.app.github.dev')
      return `${protocol}//${backendHost}`
    }

    // Standard localhost or local Docker
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return `${protocol}//${hostname}:8000`
    }

    // Generic: same host, port 8000
    return `${protocol}//${hostname}:8000`
  }

  // P3: SSR / build-time fallback
  return 'http://localhost:8000'
}

/** Resolved once — avoids re-parsing on every call */
export const API_BASE = resolveApiBase()

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------
const client = axios.create({
  baseURL: API_BASE,
  timeout: 180_000, // 3 minutes — IR graph can take 60-90 seconds
  headers: { 'Content-Type': 'application/json' },
})

if (process.env.NODE_ENV === 'development' && typeof window !== 'undefined') {
  console.info(`[TaxLens-AI] API base resolved → ${API_BASE}`)
}

// ---------------------------------------------------------------------------
// Type Definitions — mirror FastAPI Pydantic response models exactly
// ---------------------------------------------------------------------------

export interface IocEntry {
  ioc: string
  type: string
  verdict: string
  score?: number
  source?: string
  details?: Record<string, unknown>
}

export interface TimelineEntry {
  timestamp: string
  source: string
  artifact: string
  description: string
  severity: string
}

export interface NotableEvent {
  event_id: string
  title: string
  severity: string
  risk_score: number
  src: string
  dest: string
  owner: string
  status: string
  rule_name: string
  time: string
}

export interface SupervisorReport {
  incident_id: string
  status: string
  severity: string
  summary: string
  ioc_table: IocEntry[]
  timeline: TimelineEntry[]
  notable_events: NotableEvent[]
  recommendations: string[]
  agents_invoked: string[]
  error_count: number
  iteration_count: number
  completed_at: string
}

export interface InvestigateRequest {
  incident_id: string
  evidence_paths: string[]
}

export interface InvestigateResponse {
  graph_run_id: string
  incident_id: string
  status: string
  severity: string
  summary: string
  iteration_count: number
  completed_at: string
  supervisor_report: SupervisorReport
}

export interface AuditEvent {
  id: string
  event_type: string
  agent_name: string
  status: string
  tool_name: string | null
  retry_attempt: number
  duration_ms: number | null
  sha256_hash: string | null
  recorded_at: string | null
}

export interface AuditEventsResponse {
  incident_id: string
  count: number
  events: AuditEvent[]
}

export interface HealthResponse {
  status: string
  service: string
}

// ---------------------------------------------------------------------------
// Error extraction — uses duck-typing instead of AxiosError class guard
// so it works correctly even when axios types are temporarily unavailable.
// ---------------------------------------------------------------------------
export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    // Duck-type an AxiosError shape: it is an Error with a `response` property
    const maybeAxios = err as Error & {
      response?: { data?: { detail?: unknown }; status?: number }
      code?: string
    }

    const detail = maybeAxios.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return (detail as Array<{ msg?: string }>)
        .map((d) => d.msg ?? JSON.stringify(d))
        .join('; ')
    }

    // Network error: no response received (CORS block, backend down, etc.)
    if (maybeAxios.code === 'ERR_NETWORK' || maybeAxios.response?.status === 0) {
      return `Không thể kết nối tới backend (${API_BASE}). Kiểm tra backend đang chạy và CORS đã cấu hình đúng.`
    }

    return err.message
  }
  if (typeof err === 'string') return err
  return 'Lỗi không xác định'
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health')
  return data
}

export async function investigate(
  req: InvestigateRequest
): Promise<InvestigateResponse> {
  const { data } = await client.post<InvestigateResponse>(
    '/api/v1/ir/investigate',
    req,
    { headers: { 'X-Incident-ID': req.incident_id } }
  )
  return data
}

export async function getAuditEvents(
  incidentId: string,
  limit = 200
): Promise<AuditEventsResponse> {
  const { data } = await client.get<AuditEventsResponse>('/api/v1/audit/events', {
    params: { incident_id: incidentId, limit },
  })
  return data
}

// Re-export AxiosError for consumers that want to narrow catch blocks
export { AxiosError }
