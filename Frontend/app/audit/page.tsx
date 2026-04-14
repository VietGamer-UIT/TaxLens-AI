'use client'

import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Search, RefreshCw, ScrollText, AlertTriangle,
  CheckCircle2, XCircle, Clock, Wrench,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { getAuditEvents, AuditEvent, extractErrorMessage } from '@/lib/api'
import {
  formatDate, eventTypeLabel, agentLabel, statusLabel, truncate, cn,
} from '@/lib/utils'

// ---------------------------------------------------------------------------
// Status badge colour mapping
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: 'success' | 'destructive' | 'warning' | 'default'; icon: ReactNode }> = {
    ok:      { variant: 'success',     icon: <CheckCircle2 className="h-3 w-3" /> },
    error:   { variant: 'destructive', icon: <XCircle className="h-3 w-3" /> },
    blocked: { variant: 'warning',     icon: <AlertTriangle className="h-3 w-3" /> },
  }
  const cfg = map[status?.toLowerCase()] ?? { variant: 'default', icon: null }
  return (
    <Badge variant={cfg.variant} className="flex w-fit items-center gap-1 text-[10px]">
      {cfg.icon}
      {statusLabel(status)}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Event type colours
// ---------------------------------------------------------------------------
function EventTypeBadge({ type }: { type: string }) {
  const colorMap: Record<string, string> = {
    TOOL_CALLED:          'text-blue-400',
    TOOL_SUCCEEDED:       'text-green-400',
    TOOL_FAILED:          'text-red-400',
    AGENT_STARTED:        'text-cyan-400',
    AGENT_COMPLETED:      'text-cyan-300',
    SUPERVISOR_ROUTED:    'text-purple-400',
    SUPERVISOR_COMPLETED: 'text-purple-300',
    GRAPH_STARTED:        'text-yellow-400',
    GRAPH_COMPLETED:      'text-yellow-300',
  }
  return (
    <span className={cn('font-mono text-[11px]', colorMap[type] ?? 'text-muted-foreground')}>
      {eventTypeLabel(type)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Table skeleton
// ---------------------------------------------------------------------------
function TableSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <ScrollText className="h-10 w-10 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------
export default function AuditPage() {
  const [incidentId, setIncidentId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading]       = useState(false)
  const [events, setEvents]         = useState<AuditEvent[] | null>(null)
  const [count, setCount]           = useState(0)
  const [error, setError]           = useState<string | null>(null)

  async function handleSearch(id?: string) {
    const queryId = (id ?? searchInput).trim()
    if (!queryId) return

    setIncidentId(queryId)
    setLoading(true)
    setError(null)
    setEvents(null)

    try {
      const res = await getAuditEvents(queryId, 200)
      setEvents(res.events ?? [])
      setCount(res.count ?? 0)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">

      {/* ── Header Card ─────────────────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ScrollText className="h-5 w-5 text-primary" />
            Nhật Ký Kiểm Toán Hệ Thống
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Mỗi sự kiện được ghi bất biến vào PostgreSQL với mã băm SHA-256 để đảm bảo
            tính toàn vẹn của bằng chứng theo tiêu chuẩn điều tra số pháp y.
          </p>
          {/* Search Bar */}
          <div className="flex gap-2">
            <Input
              placeholder="Nhập ID Sự Cố (ví dụ: IR-2024-DEMO-001)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              disabled={loading}
              className="font-mono max-w-sm"
            />
            <Button
              onClick={() => handleSearch()}
              disabled={loading || !searchInput.trim()}
              className="gap-2"
            >
              {loading ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Tìm Kiếm
            </Button>
            {events !== null && (
              <Button
                variant="outline"
                onClick={() => handleSearch(incidentId)}
                disabled={loading}
                className="gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                Làm Mới
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Summary row (after search) ──────────────────────────────── */}
      {events !== null && !loading && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 animate-fade-in-up">
          {[
            { label: 'Tổng Sự Kiện',    value: count,                             color: 'text-primary'  },
            { label: 'Thành Công',       value: events.filter(e => e.status === 'ok').length,    color: 'text-green-400'},
            { label: 'Thất Bại',         value: events.filter(e => e.status === 'error').length, color: 'text-red-400'  },
            { label: 'Gọi Công Cụ',      value: events.filter(e => e.event_type.startsWith('TOOL')).length, color: 'text-cyan-400'},
          ].map(({ label, value, color }) => (
            <Card key={label} className="border-border py-1">
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className={`text-2xl font-bold ${color}`}>{value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── Error ─────────────────────────────────────────────────────── */}
      {error && !loading && (
        <Alert variant="destructive" className="animate-fade-in-up">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Lỗi Truy Vấn</AlertTitle>
          <AlertDescription className="font-mono text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Table ────────────────────────────────────────────────────── */}
      <Card className="border-border">
        {/* Table header bar */}
        {events !== null && !loading && (
          <CardHeader className="pb-0">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">
                {count > 0
                  ? `${count} sự kiện cho incident ${incidentId}`
                  : 'Không tìm thấy sự kiện'}
              </CardTitle>
              {count > 0 && (
                <Badge variant="outline" className="font-mono text-[11px]">
                  {incidentId}
                </Badge>
              )}
            </div>
          </CardHeader>
        )}

        <CardContent className={events !== null && !loading ? 'pt-4 p-0' : 'p-0'}>
          {/* Initial state */}
          {events === null && !loading && !error && (
            <EmptyState message="Nhập ID Sự Cố và nhấn Tìm Kiếm để xem nhật ký kiểm toán." />
          )}

          {/* Loading state */}
          {loading && <TableSkeleton />}

          {/* No results */}
          {events?.length === 0 && !loading && (
            <EmptyState message={`Không tìm thấy sự kiện nào cho "${incidentId}".`} />
          )}

          {/* Data table */}
          {events && events.length > 0 && !loading && (
            <div className="animate-fade-in-up overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Thời Gian</TableHead>
                    <TableHead>Loại Sự Kiện</TableHead>
                    <TableHead>Tác Nhân</TableHead>
                    <TableHead>Công Cụ</TableHead>
                    <TableHead>Trạng Thái</TableHead>
                    <TableHead className="text-right">TG (ms)</TableHead>
                    <TableHead>Hash SHA-256</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map((ev) => (
                    <TableRow key={ev.id}>
                      {/* Time */}
                      <TableCell className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          <Clock className="h-3 w-3 flex-shrink-0" />
                          {ev.recorded_at
                            ? ev.recorded_at.slice(0, 19).replace('T', ' ')
                            : '—'}
                        </div>
                      </TableCell>

                      {/* Event Type */}
                      <TableCell>
                        <EventTypeBadge type={ev.event_type} />
                      </TableCell>

                      {/* Agent */}
                      <TableCell className="text-xs">
                        {agentLabel(ev.agent_name)}
                      </TableCell>

                      {/* Tool */}
                      <TableCell>
                        {ev.tool_name ? (
                          <span className="flex items-center gap-1 font-mono text-[11px] text-cyan-400">
                            <Wrench className="h-3 w-3 flex-shrink-0" />
                            {ev.tool_name}
                          </span>
                        ) : (
                          <span className="text-muted-foreground/40 text-xs">—</span>
                        )}
                      </TableCell>

                      {/* Status */}
                      <TableCell>
                        <StatusBadge status={ev.status} />
                        {ev.retry_attempt > 0 && (
                          <span className="ml-1 text-[10px] text-yellow-400">
                            ×{ev.retry_attempt}
                          </span>
                        )}
                      </TableCell>

                      {/* Duration */}
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {ev.duration_ms != null ? `${ev.duration_ms}` : '—'}
                      </TableCell>

                      {/* Hash */}
                      <TableCell className="font-mono text-[10px] text-muted-foreground/60 max-w-[120px] truncate">
                        {ev.sha256_hash ? truncate(ev.sha256_hash, 16) : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  )
}
