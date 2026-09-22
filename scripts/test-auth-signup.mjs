/**
 * CI smoke test: user sign-up + sign-in against a real (ephemeral) MongoDB,
 * using the same better-auth configuration as lib/better-auth/auth.ts.
 *
 * Production incident (2026-09-22): sign-up returned FAILED_TO_CREATE_USER
 * for every new user. The frontend had zero coverage of the auth write path;
 * e2e only rendered the form. This test fails CI if user creation, session
 * issuance (autoSignIn) or credential sign-in regress again.
 *
 * Keep the config below in sync with lib/better-auth/auth.ts.
 */
import { MongoMemoryServer } from 'mongodb-memory-server';
import mongoose from 'mongoose';
import { betterAuth } from 'better-auth';
import { mongodbAdapter } from 'better-auth/adapters/mongodb';
import { twoFactor } from 'better-auth/plugins';

const EMAIL = `ci-auth-${Date.now()}@example.com`;
const PASSWORD = 'CI-smoke-password-123';

let mongod;
try {
    mongod = await MongoMemoryServer.create();
    await mongoose.connect(mongod.getUri());

    const auth = betterAuth({
        database: mongodbAdapter(mongoose.connection),
        secret: 'ci-only-secret-that-is-long-enough-for-builds',
        baseURL: 'http://localhost:3000',
        emailAndPassword: {
            enabled: true,
            disableSignUp: false,
            requireEmailVerification: false,
            minPasswordLength: 8,
            maxPasswordLength: 128,
            autoSignIn: true,
        },
        plugins: [twoFactor({ issuer: 'CavaAI' })],
    });

    const signUp = await auth.api.signUpEmail({
        body: { email: EMAIL, password: PASSWORD, name: 'CI Smoke' },
    });
    if (!signUp?.user?.id || !signUp?.token) {
        throw new Error('signUpEmail returned no user id or session token');
    }
    console.log(`OK sign-up: user ${signUp.user.id}, session issued`);

    const signIn = await auth.api.signInEmail({
        body: { email: EMAIL, password: PASSWORD },
    });
    if (!signIn?.user?.id) {
        throw new Error('signInEmail failed for the freshly created user');
    }
    console.log('OK sign-in: credentials accepted');
} catch (err) {
    console.error('AUTH SMOKE FAILED:', err?.body?.code || err?.code || '', err?.message || err);
    process.exitCode = 1;
} finally {
    try { await mongoose.connection.close(); } catch {}
    try { await mongod?.stop(); } catch {}
}
