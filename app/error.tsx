'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/button'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Log the error to an error reporting service
    console.error('Application error:', error)
  }, [error])

  // Check if it's a configuration error
  const isConfigError = error.message.includes('MONGODB_URI') || 
                       error.message.includes('BETTER_AUTH_SECRET') ||
                       error.message.includes('environment variable') ||
                       error.message.includes('MongoDB connection');

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="mx-auto max-w-md text-center">
        <div className="mb-6">
          <svg
            className="mx-auto h-16 w-16 text-destructive"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        
        <h1 className="mb-2 text-2xl font-bold text-foreground">
          {isConfigError ? 'Configuration Error' : 'Something went wrong!'}
        </h1>
        
        <p className="mb-6 text-muted-foreground">
          {isConfigError ? (
            <>
              The application is not properly configured. Please check that all required 
              environment variables are set correctly.
            </>
          ) : (
            <>
              We apologize for the inconvenience. An unexpected error has occurred.
            </>
          )}
        </p>

        {isConfigError && (
          <div className="mb-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-left">
            <h3 className="mb-2 font-semibold text-destructive">Required Configuration:</h3>
            <ul className="space-y-1 text-sm text-muted-foreground">
              <li>• MONGODB_URI - Database connection string</li>
              <li>• BETTER_AUTH_SECRET - Authentication secret (32+ chars)</li>
              <li>• BETTER_AUTH_URL - Application base URL</li>
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              See <code className="rounded bg-muted px-1 py-0.5">.env.example</code> for details.
            </p>
          </div>
        )}

        <div className="flex gap-4 justify-center">
          <Button
            onClick={reset}
            variant="default"
          >
            Try again
          </Button>
          
          <Button
            onClick={() => window.location.href = '/'}
            variant="outline"
          >
            Go home
          </Button>
        </div>

        {process.env.NODE_ENV === 'development' && (
          <details className="mt-6 text-left">
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
              Error details (development only)
            </summary>
            <pre className="mt-2 overflow-auto rounded-lg bg-muted p-4 text-xs">
              {error.message}
              {error.digest && `\nError ID: ${error.digest}`}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
