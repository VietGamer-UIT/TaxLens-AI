'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  ShieldCheck, Search, ScrollText, Zap,
  Database, Cpu, Server, ArrowRight, CheckCircle2, XCircle,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { checkHealth, API_BASE } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type SystemStatus = 'checking' | 'online' | 'offline'

// ---------------------------------------------------------------------------
// Stat cards data (static demo — Vietnamese labels)
// ---------------------------------------------------------------------------
const STATS = [
  { icon: ShieldCheck, label: 'Điều Tra Hoàn Tất',   value: '—',         color: 'text-blue-400'   },
  { icon: Zap,         label: 'Mức Nghiêm Trọng TB', value: 'CRITICAL', color: 'text-red-400'    },
  { icon: Cpu,         label: 'Tác Nhân AI Đang Chạy',value: '4',        color: 'text-cyan-400'   },
  { icon: Database,    label: 'Sự Kiện Trong DB',     value: '—',        color: 'text-green-400'  },
]

// ---------------------------------------------------------------------------
// Feature cards (Vietnamese UI)
// ---------------------------------------------------------------------------
const FEATURES = [
  {
    icon: Search,
    title: '🔎 Chat Điều Tra',
    desc:  'Nhập ID sự cố và đường dẫn bằng chứng. Bộ tác nhân AI (Forensics → Network → ThreatIntel) sẽ tự động phân tích và tổng hợp báo cáo.',
    href:  '/investigate',
    cta:   'Bắt đầu điều tra',
  },
  {
    icon: ScrollText,
    title: '📋 Nhật Ký Kiểm Toán',
    desc:  'Xem toàn bộ nhật ký bất biến từ PostgreSQL — mỗi lần gọi công cụ, quyết định định tuyến, và lượng token tiêu thụ đều được ghi lại.',
    href:  '/audit',
    cta:   'Xem nhật ký',
  },
]

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const [status, setStatus] = useState<SystemStatus>('checking')
  const [serviceName, setServiceName] = useState('')

  // Ping backend health on mount
  useEffect(() => {
    checkHealth()
      .then((res) => {
        setStatus('online')
        setServiceName(res.service)
      })
      .catch(() => setStatus('offline'))
  }, [])

  return (
    <div className="space-y-8 animate-fade-in-up">

      {/* ── Hero Banner ──────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 via-card to-card p-8 glow-blue">
        <div className="absolute right-8 top-8 opacity-10">
          <ShieldCheck className="h-32 w-32 text-primary" />
        </div>
        <div className="relative">
          <Badge variant="cyan" className="mb-3 text-[11px]">
            Nền Tảng Điều Tra Sự Cố Đa Tác Nhân AI
          </Badge>
          <h2 className="mb-2 text-3xl font-bold tracking-tight text-foreground">
            TaxLens-<span className="text-primary">AI</span>
          </h2>
          <p className="max-w-xl text-muted-foreground text-sm leading-relaxed">
            Nền tảng điều tra sự cố bảo mật đa tác nhân AI thế hệ mới. Được xây dựng
            với <strong className="text-foreground">LangGraph</strong>, <strong className="text-foreground">MCP Servers</strong> và{' '}
            <strong className="text-foreground">PostgreSQL Audit Trail</strong> bất biến chuẩn SANS.
          </p>
          <p className="mt-2 text-xs text-muted-foreground/70">
            by Đoàn Hoàng Việt (Việt Gamer) — Principal Developer
          </p>
          <div className="mt-5 flex gap-3">
            <Button asChild size="lg">
              <Link href="/investigate" className="gap-2">
                <Search className="h-4 w-4" /> Bắt Đầu Điều Tra
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/audit" className="gap-2">
                <ScrollText className="h-4 w-4" /> Xem Nhật Ký
              </Link>
            </Button>
          </div>
        </div>
      </div>

      {/* ── System Status ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STATS.map(({ icon: Icon, label, value, color }) => (
          <Card key={label} className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                <Icon className={`h-4 w-4 ${color}`} />
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Backend Connectivity ─────────────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Server className="h-4 w-4 text-primary" />
            Kết Nối Backend
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            {status === 'checking' && (
              <>
                <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-yellow-400" />
                <span className="text-sm text-yellow-400">Đang kiểm tra kết nối...</span>
              </>
            )}
            {status === 'online' && (
              <>
                <CheckCircle2 className="h-5 w-5 text-green-400" />
                <span className="text-sm text-green-400">
                  Kết nối thành công — <span className="font-mono text-xs">{serviceName}</span>
                </span>
              </>
            )}
            {status === 'offline' && (
              <>
                <XCircle className="h-5 w-5 text-red-400" />
                <div>
                  <p className="text-sm text-red-400">Không thể kết nối tới Backend API</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Hãy chắc chắn backend đang chạy tại{' '}
                    <code className="font-mono text-xs">
                      {API_BASE}
                    </code>
                  </p>
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Feature Cards ─────────────────────────────────────────────────── */}
      <div className="grid gap-5 lg:grid-cols-2">
        {FEATURES.map(({ icon: Icon, title, desc, href, cta }) => (
          <Card key={href} className="group border-border transition-colors hover:border-primary/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                {title}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
              <Button asChild variant="outline" size="sm">
                <Link href={href} className="gap-2">
                  {cta} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Architecture Quick-ref ───────────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-sm">Kiến Trúc Hệ Thống</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs">
            {[
              { label: 'Tác Nhân Pháp Y',   detail: 'Volatility3 · Plaso/log2timeline',   color: 'border-blue-700/40 text-blue-300'  },
              { label: 'Tác Nhân Mạng',     detail: 'Splunk SPL · ES Notable Events',      color: 'border-cyan-700/40 text-cyan-300'  },
              { label: 'Tác Nhân Intel',    detail: 'VirusTotal v3 · AbuseIPDB v2',         color: 'border-purple-700/40 text-purple-300'},
              { label: 'Giám Sát Trung Tâm',detail: 'LangGraph Supervisor · SHA-256 Hash', color: 'border-green-700/40 text-green-300' },
            ].map(({ label, detail, color }) => (
              <div key={label} className={`rounded-md border p-3 ${color}`}>
                <p className="font-medium">{label}</p>
                <p className="mt-0.5 text-muted-foreground">{detail}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

    </div>
  )
}
