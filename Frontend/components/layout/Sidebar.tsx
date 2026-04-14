'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Search,
  ScrollText,
  ShieldCheck,
  Github,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Navigation definition (Vietnamese UI labels)
// ---------------------------------------------------------------------------
const NAV_ITEMS = [
  {
    href: '/',
    icon: LayoutDashboard,
    label: 'Bảng Điều Khiển',
    description: 'Trạng thái hệ thống',
  },
  {
    href: '/investigate',
    icon: Search,
    label: 'Chat Điều Tra',
    description: 'Khởi động cuộc điều tra',
  },
  {
    href: '/audit',
    icon: ScrollText,
    label: 'Nhật Ký Kiểm Toán',
    description: 'Lịch sử sự kiện SANS',
  },
] as const

// ---------------------------------------------------------------------------
// Sidebar Component
// ---------------------------------------------------------------------------
export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-card">

      {/* ── Brand / Logo ────────────────────────────────────────────────── */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/30">
          <ShieldCheck className="h-5 w-5 text-primary" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-bold tracking-wide text-foreground">
            TaxLens
            <span className="text-primary">-AI</span>
          </p>
          <p className="text-[10px] text-muted-foreground">IR Platform</p>
        </div>
      </div>

      {/* ── Navigation ──────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-4 px-2">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Điều Hướng
        </p>
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ href, icon: Icon, label, description }) => {
            const isActive =
              href === '/' ? pathname === '/' : pathname.startsWith(href)
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={cn(
                    'group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-all duration-150',
                    isActive
                      ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                  )}
                >
                  <Icon
                    className={cn(
                      'h-4 w-4 flex-shrink-0 transition-colors',
                      isActive
                        ? 'text-primary'
                        : 'text-muted-foreground group-hover:text-foreground'
                    )}
                  />
                  <span className="flex-1 font-medium">{label}</span>
                  {isActive && (
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  )}
                </Link>
              </li>
            )
          })}
        </ul>

        {/* ── Separator + Quick Info ───────────────────────────────────── */}
        <div className="mt-6 border-t border-border pt-4 px-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Công Nghệ
          </p>
          <div className="space-y-1.5 text-[11px] text-muted-foreground">
            {[
              '🤖 LangGraph Multi-Agent',
              '🔌 Custom MCP Servers',
              '🛡️ Read-Only Forensics',
              '📋 PostgreSQL Audit Trail',
              '⚡ FastAPI + Asyncio',
            ].map((tech) => (
              <p key={tech}>{tech}</p>
            ))}
          </div>
        </div>
      </nav>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <div className="border-t border-border p-4">
        <a
          href="https://github.com/VietGamer-UIT/TaxLens-AI"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <Github className="h-3.5 w-3.5" />
          <span>VietGamer-UIT / TaxLens-AI</span>
        </a>
        <p className="mt-1 px-2 text-[10px] text-muted-foreground/60">
          © 2024 Đoàn Hoàng Việt (Việt Gamer)
        </p>
      </div>
    </aside>
  )
}
