import { NextResponse } from 'next/server';

/**
 * Health check endpoint to verify environment configuration
 * Returns 200 if all critical services are configured
 * Returns 503 if critical configuration is missing
 */
export async function GET() {
    const health = {
        status: 'healthy',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'unknown',
        checks: {
            mongodb: false,
            auth: false,
            api: false,
        },
        errors: [] as string[],
    };

    // Check MongoDB URI
    if (!process.env.MONGODB_URI) {
        health.checks.mongodb = false;
        health.errors.push('MONGODB_URI is not configured');
    } else {
        health.checks.mongodb = true;
    }

    // Check Better Auth Secret
    if (!process.env.BETTER_AUTH_SECRET) {
        health.checks.auth = false;
        health.errors.push('BETTER_AUTH_SECRET is not configured');
    } else if (process.env.BETTER_AUTH_SECRET.length < 32) {
        health.checks.auth = false;
        health.errors.push('BETTER_AUTH_SECRET must be at least 32 characters');
    } else {
        health.checks.auth = true;
    }

    // Check Better Auth URL
    if (!process.env.BETTER_AUTH_URL) {
        health.errors.push('BETTER_AUTH_URL is not configured (non-critical)');
    }

    // Check Finnhub API Key (optional but recommended)
    if (!process.env.FINNHUB_API_KEY) {
        health.errors.push('FINNHUB_API_KEY is not configured (will use fallback sources)');
    } else {
        health.checks.api = true;
    }

    // Determine overall status
    const criticalChecks = health.checks.mongodb && health.checks.auth;
    health.status = criticalChecks ? 'healthy' : 'unhealthy';

    const statusCode = criticalChecks ? 200 : 503;

    return NextResponse.json(health, { status: statusCode });
}
