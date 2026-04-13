'use client'

import { usePathname } from 'next/navigation'
import { Activity } from 'lucide-react'

// Vietnamese breadcrumb labels
const ROUTE_LABELS: Record<string, { title: string; subtitle: string }> = {
  '/':           { title: 'Bảng Điều Khiển',    subtitle: 'Tổng quan hệ thống TaxLens-AI' },
  '/investigate':{ title: 'Chat Điều Tra',        subtitle: 'Khởi động điều tra đa tác nhân AI' },
  '/audit':      { title: 'Nhật Ký Kiểm Toán',   subtitle: 'Lịch sử sự kiện chuẩn SANS FIND EVIL!' },
}

export function TopBar() {
  const pathname = usePathname()
  // Match exact or prefix
  const routeKey =
    Object.keys(ROUTE_LABELS)
      .filter((k) => (k === '/' ? pathname === '/' : pathname.startsWith(k)))
      .sort((a, b) => b.length - a.length)[0] ?? '/'

  const { title, subtitle } = ROUTE_LABELS[routeKey]

  return (
    <header className="fixed left-64 right-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-sm">
      {/* Left: page title */}
      <div>
        <h1 className="text-sm font-semibold text-foreground">{title}</h1>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>

      {/* Right: live status pill */}
      <div className="flex items-center gap-2 rounded-full border border-green-700/40 bg-green-950/30 px-3 py-1.5 text-xs text-green-400">
        <Activity className="h-3 w-3 animate-pulse" />
        <span>Hệ Thống Hoạt Động</span>
      </div>
    </header>
  )
}
