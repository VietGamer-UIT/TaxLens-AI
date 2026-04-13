// =============================================================================
// TaxLens-AI :: API Client
// Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
// =============================================================================
// All functions are typed to match Backend/FastAPI response schemas exactly.
// Base URL is read from NEXT_PUBLIC_API_URL environment variable.
// =============================================================================

import axios, { AxiosError } from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------
const client = axios.create({
  baseURL: API_BASE,
  timeout: 180_000, // 3 minutes — IR graph can run for ~60-90 seconds
  headers: { 'Content-Type': 'application/json' },
})

// ---------------------------------------------------------------------------
// Type Definitions — mirror FastAPI Pydantic response models
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
// API Error helper
// ---------------------------------------------------------------------------
export function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    // FastAPI returns {detail: "..."} on 422/500
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ')
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Lỗi không xác định'
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/**
 * POST /health — liveness check
 */
export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health')
  return data
}

/**
 * POST /api/v1/ir/investigate — trigger multi-agent IR investigation
 */
export async function investigate(
  req: InvestigateRequest
): Promise<InvestigateResponse> {
  const { data } = await client.post<InvestigateResponse>(
    '/api/v1/ir/investigate',
    req,
    {
      headers: { 'X-Incident-ID': req.incident_id },
    }
  )
  return data
}

/**
 * GET /api/v1/audit/events — retrieve audit trail for an incident
 */
export async function getAuditEvents(
  incidentId: string,
  limit = 200
): Promise<AuditEventsResponse> {
  const { data } = await client.get<AuditEventsResponse>(
    '/api/v1/audit/events',
    { params: { incident_id: incidentId, limit } }
  )
  return data
}
