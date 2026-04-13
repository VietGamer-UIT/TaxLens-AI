import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes safely without conflicts */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format ISO date string to Vietnamese locale */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(dateStr))
  } catch {
    return dateStr
  }
}

/** Truncate long string with ellipsis */
export function truncate(str: string, maxLen = 48): string {
  if (!str || str.length <= maxLen) return str
  return str.slice(0, maxLen) + '…'
}

/** Map severity string to Tailwind color classes */
export function severityColor(severity: string): {
  text: string
  bg: string
  border: string
  badge: string
} {
  switch (severity?.toLowerCase()) {
    case 'critical':
      return {
        text: 'text-red-400',
        bg: 'bg-red-950/50',
        border: 'border-red-700',
        badge: 'bg-red-900 text-red-300 border-red-700',
      }
    case 'high':
      return {
        text: 'text-orange-400',
        bg: 'bg-orange-950/50',
        border: 'border-orange-700',
        badge: 'bg-orange-900 text-orange-300 border-orange-700',
      }
    case 'medium':
      return {
        text: 'text-yellow-400',
        bg: 'bg-yellow-950/50',
        border: 'border-yellow-700',
        badge: 'bg-yellow-900 text-yellow-300 border-yellow-700',
      }
    case 'low':
      return {
        text: 'text-green-400',
        bg: 'bg-green-950/50',
        border: 'border-green-700',
        badge: 'bg-green-900 text-green-300 border-green-700',
      }
    default:
      return {
        text: 'text-slate-400',
        bg: 'bg-slate-900/50',
        border: 'border-slate-700',
        badge: 'bg-slate-800 text-slate-300 border-slate-600',
      }
  }
}

/** Vietnamese severity label */
export function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    critical: 'NGHIÊM TRỌNG',
    high: 'CAO',
    medium: 'TRUNG BÌNH',
    low: 'THẤP',
    unknown: 'CHƯA XÁC ĐỊNH',
  }
  return map[severity?.toLowerCase()] ?? severity?.toUpperCase() ?? '—'
}

/** Vietnamese status label */
export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    complete: 'Hoàn tất',
    partial: 'Một phần',
    failed: 'Thất bại',
    ok: 'Thành công',
    error: 'Lỗi',
    blocked: 'Bị chặn',
    unknown: 'Chưa rõ',
  }
  return map[status?.toLowerCase()] ?? status ?? '—'
}

/** Vietnamese event type label */
export function eventTypeLabel(t: string): string {
  const map: Record<string, string> = {
    GRAPH_STARTED: 'Bắt đầu đồ thị',
    GRAPH_COMPLETED: 'Hoàn tất đồ thị',
    AGENT_STARTED: 'Agent khởi động',
    AGENT_COMPLETED: 'Agent hoàn tất',
    SUPERVISOR_ROUTED: 'Supervisor định tuyến',
    SUPERVISOR_COMPLETED: 'Supervisor hoàn tất',
    TOOL_CALLED: 'Gọi công cụ',
    TOOL_SUCCEEDED: 'Công cụ thành công',
    TOOL_FAILED: 'Công cụ thất bại',
    HTTP_REQUEST: 'Yêu cầu HTTP',
  }
  return map[t] ?? t ?? '—'
}

/** Vietnamese agent name label */
export function agentLabel(name: string): string {
  const map: Record<string, string> = {
    supervisor: 'Giám sát',
    forensics_agent: 'Pháp y',
    network_agent: 'Mạng',
    database_agent: 'Threat Intel',
    system: 'Hệ thống',
  }
  return map[name?.toLowerCase()] ?? name ?? '—'
}
