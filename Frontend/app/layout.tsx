import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

// ---------------------------------------------------------------------------
// Font — Inter for body text
// ---------------------------------------------------------------------------
const inter = Inter({
  subsets: ['latin', 'vietnamese'],
  variable: '--font-inter',
  display: 'swap',
})

// ---------------------------------------------------------------------------
// SEO Metadata
// ---------------------------------------------------------------------------
export const metadata: Metadata = {
  title: {
    default: 'TaxLens-AI | Nền Tảng Điều Tra Sự Cố Đa Tác Nhân',
    template: '%s | TaxLens-AI',
  },
  description:
    'TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer) — Nền tảng điều tra sự cố bảo mật đa tác nhân AI sử dụng LangGraph, MCP Servers và PostgreSQL Audit Trail chuẩn SANS.',
  authors: [{ name: 'Đoàn Hoàng Việt (Việt Gamer)' }],
  keywords: ['SANS', 'Splunk', 'Incident Response', 'LangGraph', 'MCP', 'AI Security'],
}

// ---------------------------------------------------------------------------
// Root Layout
// ---------------------------------------------------------------------------
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="vi" className="dark">
      <body className={`${inter.variable} font-sans`}>
        {/* Fixed sidebar — 256 px wide */}
        <Sidebar />

        {/* Fixed top bar — positioned after sidebar */}
        <TopBar />

        {/* Main content area — offset by sidebar + topbar */}
        <main className="ml-64 mt-16 min-h-[calc(100vh-4rem)] bg-background">
          <div className="p-6">{children}</div>
        </main>
      </body>
    </html>
  )
}
