'use server';

import { getAuth } from "@/lib/better-auth/auth";
import { inngest } from "@/lib/inngest/client";
import { headers } from "next/headers";
import { AuthenticationError, toAppError, getErrorMessage } from "@/lib/types/errors";
import { ERROR_MESSAGES } from "@/lib/constants";

export const signUpWithEmail = async ({ email, password, fullName, country, investmentGoals, riskTolerance, preferredIndustry }: SignUpFormData): Promise<{ success: boolean; data?: unknown; error?: string }> => {
    try {
        const auth = await getAuth();
        if (!auth) {
            throw new AuthenticationError(ERROR_MESSAGES.AUTH_UNAVAILABLE);
        }

        const response = await auth.api.signUpEmail({ body: { email, password, name: fullName } });

        if (response) {
            try {
                await inngest.send({
                    name: 'app/user.created',
                    data: { email, name: fullName, country, investmentGoals, riskTolerance, preferredIndustry }
                });
            } catch (inngestError) {
                // No fallar el signup si inngest falla
                console.warn('Failed to send inngest event:', inngestError);
            }
        }

        return { success: true, data: response };
    } catch (error: unknown) {
        const appError = toAppError(error);

        // Mensajes de error más específicos
        let errorMessage: string = ERROR_MESSAGES.AUTH_FAILED;

        if (appError.message.includes('email') || appError.message.includes('Email')) {
            errorMessage = 'This email is already registered. Please sign in instead.';
        } else if (appError.message.includes('password') || appError.message.includes('Password')) {
            errorMessage = 'Password must be at least 8 characters long.';
        } else if (appError.message.includes('unavailable') || appError.message.includes('temporarily')) {
            errorMessage = ERROR_MESSAGES.AUTH_UNAVAILABLE;
        } else {
            errorMessage = getErrorMessage(error);
        }

        console.error('Sign up failed:', appError);
        return { success: false, error: errorMessage };
    }
}

export const signInWithEmail = async ({ email, password }: SignInFormData): Promise<{ success: boolean; data?: unknown; error?: string }> => {
    try {
        const auth = await getAuth();
        if (!auth) {
            throw new AuthenticationError(ERROR_MESSAGES.AUTH_UNAVAILABLE);
        }

        const response = await auth.api.signInEmail({ body: { email, password } });

        return { success: true, data: response };
    } catch (error: unknown) {
        const appError = toAppError(error);

        // Mensajes de error más específicos
        let errorMessage: string = ERROR_MESSAGES.AUTH_FAILED;

        if (appError.message.includes('Invalid') || appError.message.includes('invalid')) {
            errorMessage = 'Invalid email or password. Please check your credentials and try again.';
        } else if (appError.message.includes('unavailable') || appError.message.includes('temporarily')) {
            errorMessage = ERROR_MESSAGES.AUTH_UNAVAILABLE;
        } else {
            errorMessage = getErrorMessage(error);
        }

        console.error('Sign in failed:', appError);
        return { success: false, error: errorMessage };
    }
}

export const signOut = async (): Promise<{ success: boolean; error?: string }> => {
    try {
        const auth = await getAuth();
        if (!auth) {
            throw new AuthenticationError('Unable to sign out. Authentication service is unavailable.');
        }

        await auth.api.signOut({ headers: await headers() });
        return { success: true };
    } catch (error: unknown) {
        const appError = toAppError(error);
        console.error('Sign out failed:', appError);
        return { success: false, error: 'Unable to sign out. Please refresh the page and try again.' };
    }
}

