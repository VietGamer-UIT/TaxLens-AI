import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary/20 text-primary',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground',
        destructive:
          'border-transparent bg-destructive/20 text-red-400 border-red-700/50',
        outline:
          'text-foreground border-border',
        success:
          'border-green-700/50 bg-green-900/30 text-green-400',
        warning:
          'border-yellow-700/50 bg-yellow-900/30 text-yellow-400',
        critical:
          'border-red-700/50 bg-red-900/30 text-red-400',
        high:
          'border-orange-700/50 bg-orange-900/30 text-orange-400',
        medium:
          'border-yellow-700/50 bg-yellow-900/30 text-yellow-300',
        low:
          'border-green-700/50 bg-green-900/30 text-green-400',
        cyan:
          'border-cyan-700/50 bg-cyan-900/20 text-cyan-400',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
