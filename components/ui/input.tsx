import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-gray-800/50 border-gray-600 h-10 w-full min-w-0 rounded-lg border bg-transparent px-4 py-2 text-base transition-all duration-200 outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        // Anillo al 100%: al 50% daba ~2:1 sobre superficie, por debajo del 3:1
        // de WCAG 2.2 SC 2.4.11. El borde sube a gray-600 como segunda pista.
        "focus-visible:border-teal-400 focus-visible:bg-gray-800 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0",
        "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
