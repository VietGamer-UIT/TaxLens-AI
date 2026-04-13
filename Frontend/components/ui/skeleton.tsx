import { cn } from '@/lib/utils'

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {}

function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn('skeleton-shimmer rounded-md', className)}
      {...props}
    />
  )
}

/** A full skeleton block for the investigation result panel */
function ResultSkeleton() {
  return (
    <div className="space-y-4 animate-fade-in-up">
      {/* Header skeleton */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <div className="flex gap-3">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-7 w-20" />
        </div>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      {/* Timeline skeleton */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
      {/* Recommendations skeleton */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  )
}

export { Skeleton, ResultSkeleton }
