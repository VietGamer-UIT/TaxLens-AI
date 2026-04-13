'use client'

import { useState, useEffect, useRef } from 'react'
import {
  Search, AlertTriangle, CheckCircle2, Clock, RefreshCw,
  Shield, Network, Database, Brain, ChevronDown, ChevronUp,
  FileText, Layers
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { ResultSkeleton } from '@/components/ui/skeleton'
import {
  investigate,
  InvestigateResponse,
  SupervisorReport,
  extractErrorMessage,
} from '@/lib/api'
import {
  cn, formatDate, severityColor, severityLabel, statusLabel, truncate,
} from '@/lib/utils'

// ---------------------------------------------------------------------------
// Loading step definitions (Vietnamese UI text)
// ---------------------------------------------------------------------------
const LOADING_STEPS = [
  { icon: Brain,    label: 'Khởi động hệ thống đa tác nhân...',  delay: 0   },
  { icon: Shield,   label: 'Phân tích bộ nhớ RAM và nhật ký...',  delay: 4000 },
  { icon: Network,  label: 'Truy vấn dữ liệu mạng Splunk...',     delay: 9000 },
  { icon: Database, label: 'Tra cứu IOC và Threat Intelligence...', delay: 14000},
  { icon: FileText, label: 'Tổng hợp báo cáo cuối cùng...',       delay: 19000},
]

// ---------------------------------------------------------------------------
// LoadingAnimation component
// ---------------------------------------------------------------------------
function LoadingAnimation() {
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const timers = LOADING_STEPS.map((step, i) =>
      setTimeout(() => setActiveStep(i), step.delay)
    )
    return () => timers.forEach(clearTimeout)
  }, [])

  const { icon: Icon, label } = LOADING_STEPS[activeStep]

  return (
    <Card className="border-primary/20 bg-primary/5 animate-fade-in-up">
      <CardContent className="py-10">
        <div className="flex flex-col items-center gap-5 text-center">
          {/* Animated icon */}
          <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-primary/30 bg-primary/10">
            <Icon className="h-7 w-7 text-primary animate-pulse" />
            <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-primary animate-ping" />
          </div>

          {/* Step label */}
          <div>
            <p className="text-sm font-medium text-foreground">{label}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Bước {activeStep + 1} / {LOADING_STEPS.length}
            </p>
          </div>

          {/* Dots */}
          <div className="dot-pulse flex gap-1.5">
            <span /><span /><span />
          </div>

          {/* Progress bar */}
          <div className="w-full max-w-xs rounded-full bg-secondary h-1.5 overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-1000"
              style={{ width: `${((activeStep + 1) / LOADING_STEPS.length) * 100}%` }}
            />
          </div>

          {/* Step pipeline */}
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            {['Pháp Y', 'Mạng', 'Threat Intel', 'Giám Sát'].map((s, i) => (
              <span key={s} className="flex items-center gap-1">
                <span className={cn(
                  'rounded px-1.5 py-0.5',
                  activeStep > i ? 'text-green-400' : activeStep === i ? 'text-primary' : ''
                )}>{s}</span>
                {i < 3 && <span>→</span>}
              </span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Severity badge helper
// ---------------------------------------------------------------------------
function SeverityBadge({ severity }: { severity: string }) {
  const variantMap: Record<string, 'critical' | 'high' | 'medium' | 'low' | 'default'> = {
    critical: 'critical', high: 'high', medium: 'medium', low: 'low',
  }
  return (
    <Badge variant={variantMap[severity?.toLowerCase()] ?? 'default'} className="text-xs font-bold uppercase tracking-wide">
      {severityLabel(severity)}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// ReportPanel — renders the full supervisor report
// ---------------------------------------------------------------------------
function ReportPanel({ result }: { result: InvestigateResponse }) {
  const [showTech, setShowTech] = useState(false)
  const report: SupervisorReport = result.supervisor_report
  const sc = severityColor(result.severity)

  return (
    <div className="space-y-4 animate-fade-in-up">

      {/* ── Report Header ─────────────────────────────────────────────── */}
      <Card className={cn('border', sc.border, sc.bg)}>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={result.severity} />
                <Badge variant={result.status === 'complete' ? 'success' : 'warning'}>
                  {statusLabel(result.status)}
                </Badge>
              </div>
              <p className="font-mono text-xs text-muted-foreground">
                ID: {result.incident_id}
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                Run: {result.graph_run_id}
              </p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <div className="flex items-center gap-1 justify-end">
                <Clock className="h-3 w-3" />
                {formatDate(result.completed_at)}
              </div>
              <p className="mt-0.5">{result.iteration_count} vòng lặp · {report.agents_invoked.length} tác nhân</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Summary ───────────────────────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            Tóm Tắt Điều Tra
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground leading-relaxed">{report.summary}</p>
        </CardContent>
      </Card>

      {/* ── Timeline ─────────────────────────────────────────────────── */}
      {report.timeline?.length > 0 && (
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="h-4 w-4 text-cyan-400" />
              Dòng Thời Gian ({report.timeline.length} sự kiện)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Thời Điểm</TableHead>
                  <TableHead>Nguồn</TableHead>
                  <TableHead>Mô Tả</TableHead>
                  <TableHead>Mức Độ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.timeline.map((ev, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {ev.timestamp?.slice(0, 19).replace('T', ' ')}
                    </TableCell>
                    <TableCell className="text-xs">{ev.source}</TableCell>
                    <TableCell className="text-xs max-w-xs">{ev.description}</TableCell>
                    <TableCell>
                      <SeverityBadge severity={ev.severity} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── IOC Table ────────────────────────────────────────────────── */}
      {report.ioc_table?.length > 0 && (
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Shield className="h-4 w-4 text-red-400" />
              Phân Tích IOC ({report.ioc_table.length} chỉ số)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>IOC</TableHead>
                  <TableHead>Loại</TableHead>
                  <TableHead>Kết Quả</TableHead>
                  <TableHead>Điểm</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.ioc_table.map((ioc, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs">{truncate(ioc.ioc ?? '', 36)}</TableCell>
                    <TableCell className="text-xs">{ioc.type}</TableCell>
                    <TableCell>
                      <Badge
                        variant={ioc.verdict === 'MALICIOUS' ? 'critical' : ioc.verdict === 'SUSPICIOUS' ? 'warning' : 'success'}
                        className="text-[10px]"
                      >
                        {ioc.verdict}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {ioc.score != null ? ioc.score : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Notable Events ───────────────────────────────────────────── */}
      {report.notable_events?.length > 0 && (
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Network className="h-4 w-4 text-orange-400" />
              Sự Kiện Nổi Bật Splunk ({report.notable_events.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tiêu Đề</TableHead>
                  <TableHead>Mức Độ</TableHead>
                  <TableHead>Điểm Rủi Ro</TableHead>
                  <TableHead>Quy Tắc</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.notable_events.map((ev, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs max-w-xs">{ev.title}</TableCell>
                    <TableCell><SeverityBadge severity={ev.severity} /></TableCell>
                    <TableCell className="font-mono text-xs">{ev.risk_score}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{ev.rule_name}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Recommendations ──────────────────────────────────────────── */}
      {report.recommendations?.length > 0 && (
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              Khuyến Nghị ({report.recommendations.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {report.recommendations.map((rec, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="flex-shrink-0 font-mono text-xs text-primary mt-0.5">
                    {String(i + 1).padStart(2, '0')}.
                  </span>
                  <span className="text-muted-foreground">{rec}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* ── Technical Details (collapsible) ─────────────────────────── */}
      <Card className="border-border">
        <button
          className="flex w-full items-center justify-between p-5 text-left"
          onClick={() => setShowTech((v) => !v)}
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            <Layers className="h-4 w-4 text-muted-foreground" />
            Thông Tin Kỹ Thuật
          </span>
          {showTech ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>
        {showTech && (
          <CardContent className="pt-0">
            <Separator className="mb-4" />
            <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
              {[
                ['Graph Run ID', result.graph_run_id],
                ['Vòng lặp', String(result.iteration_count)],
                ['Tác nhân', report.agents_invoked.join(', ')],
                ['Lỗi phát sinh', String(report.error_count)],
                ['Trạng thái', statusLabel(result.status)],
                ['Hoàn tất lúc', formatDate(result.completed_at)],
              ].map(([label, val]) => (
                <div key={label}>
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-mono text-foreground break-all">{val}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        )}
      </Card>

    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------
export default function InvestigatePage() {
  const [incidentId, setIncidentId]     = useState('IR-2024-DEMO-001')
  const [evidencePaths, setEvidencePaths] = useState('/evidence/dc01_mem.raw\n/evidence/fw01.pcap')
  const [loading, setLoading]           = useState(false)
  const [result, setResult]             = useState<InvestigateResponse | null>(null)
  const [error, setError]               = useState<string | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!incidentId.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const paths = evidencePaths.split('\n').map((p) => p.trim()).filter(Boolean)
      const res = await investigate({
        incident_id: incidentId.trim(),
        evidence_paths: paths.length ? paths : ['/evidence/sample_mem.raw'],
      })
      setResult(res)
      // Scroll to result after render
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  function handleReset() {
    setResult(null)
    setError(null)
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">

      {/* ── Investigation Form ───────────────────────────────────────── */}
      <Card className={cn('border-border transition-all', loading && 'border-primary/30')}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Search className="h-5 w-5 text-primary" />
            Khởi Động Điều Tra Sự Cố
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">

            {/* Incident ID */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                ID Sự Cố (Incident ID) *
              </label>
              <Input
                placeholder="ví dụ: IR-2024-001"
                value={incidentId}
                onChange={(e) => setIncidentId(e.target.value)}
                disabled={loading}
                required
                className="font-mono"
              />
            </div>

            {/* Evidence paths */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Đường Dẫn Bằng Chứng (mỗi dòng một đường dẫn)
              </label>
              <Textarea
                placeholder="/evidence/dc01_mem.raw&#10;/evidence/fw01.pcap&#10;/evidence/dc01_disk.E01"
                value={evidencePaths}
                onChange={(e) => setEvidencePaths(e.target.value)}
                disabled={loading}
                rows={3}
                className="font-mono text-xs"
              />
              <p className="text-[11px] text-muted-foreground">
                💡 Môi trường Demo: để nguyên giá trị mặc định — toàn bộ công cụ chạy ở chế độ mock.
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <Button
                type="submit"
                disabled={loading || !incidentId.trim()}
                className="gap-2"
              >
                {loading ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Đang phân tích...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    Bắt Đầu Điều Tra
                  </>
                )}
              </Button>

              {(result || error) && !loading && (
                <Button type="button" variant="outline" onClick={handleReset}>
                  Điều Tra Mới
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {/* ── Loading ──────────────────────────────────────────────────── */}
      {loading && <LoadingAnimation />}

      {/* ── Error ────────────────────────────────────────────────────── */}
      {error && !loading && (
        <Alert variant="destructive" className="animate-fade-in-up">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Điều Tra Thất Bại</AlertTitle>
          <AlertDescription className="font-mono text-xs mt-1">{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Result ───────────────────────────────────────────────────── */}
      {result && !loading && (
        <div ref={resultRef}>
          <div className="mb-4 flex items-center gap-2">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground px-3">KẾT QUẢ ĐIỀU TRA</span>
            <div className="h-px flex-1 bg-border" />
          </div>
          <ReportPanel result={result} />
        </div>
      )}

    </div>
  )
}
