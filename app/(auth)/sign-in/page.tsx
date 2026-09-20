'use client';

import { useForm } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import InputField from '@/components/forms/InputField';
import FooterLink from '@/components/forms/FooterLink';
import {signInWithEmail, verifyTwoFactorTotp} from "@/lib/actions/auth.actions";
import {toast} from "sonner";
import {useRouter} from "next/navigation";
import React, {useState} from "react";

const SignIn = () => {
    const router = useRouter()
    const [twoFactorRequired, setTwoFactorRequired] = useState(false);
    const [pendingCredentials, setPendingCredentials] = useState<{ email: string; password: string } | null>(null);
    const [isVerifying, setIsVerifying] = useState(false);
    const {
        register,
        handleSubmit,
        getValues,
        formState: { errors, isSubmitting },
    } = useForm<SignInFormData>({
        defaultValues: {
            email: '',
            password: '',
        },
        mode: 'onBlur',
    });

    const onSubmit = async (data: SignInFormData) => {
        try {
            const result = await signInWithEmail(data);
            if (result.success) {
                router.push('/');
                router.refresh();
                return;
            }
            if (result.twoFactorRequired) {
                setPendingCredentials({ email: data.email, password: data.password });
                setTwoFactorRequired(true);
                return;
            }
            toast.error('Sign in failed', {
                description: result.error ?? 'Invalid email or password.',
            });
        } catch (e) {
            toast.error('Sign in failed', {
                description: e instanceof Error ? e.message : 'An unexpected error occurred. Please try again.'
            })
        }
    }

    const onVerifyTotp = async (totpCode: string) => {
        if (!pendingCredentials) return;
        setIsVerifying(true);
        try {
            const result = await verifyTwoFactorTotp({
                email: pendingCredentials.email,
                password: pendingCredentials.password,
                totpCode,
            });
            if (result.success) {
                router.push('/');
                router.refresh();
                return;
            }
            toast.error('Verification failed', {
                description: result.error ?? 'Invalid authentication code.',
            });
        } catch (e) {
            toast.error('Verification failed', {
                description: e instanceof Error ? e.message : 'An unexpected error occurred.'
            })
        } finally {
            setIsVerifying(false);
        }
    }

    if (twoFactorRequired) {
        return (
            <>
                <h1 className="form-title">Two-factor authentication</h1>
                <p className="text-sm text-gray-500 mb-6">
                    Enter the 6-digit code from your authenticator app to continue.
                </p>

                <form onSubmit={handleSubmit((_data) => onVerifyTotp(getValues('totpCode') ?? ''))} className="space-y-5">
                                    <InputField
                                        name="totpCode"
                                        label="Authentication code"
                                        placeholder="000000"
                                        autoComplete="one-time-code"
                                        register={register}
                                        error={errors.totpCode}
                                        validation={{
                                            required: 'Authentication code is required',
                                            pattern: {
                                                value: /^\d{6}$/,
                                                message: 'Code must be 6 digits'
                                            }
                                        }}
                                    />

                    <Button type="submit" disabled={isVerifying} className="yellow-btn w-full mt-5">
                        {isVerifying ? 'Verifying' : 'Verify & Sign In'}
                    </Button>

                    <button
                        type="button"
                        className="w-full text-center text-sm text-gray-500 hover:text-gray-300"
                        onClick={() => {
                            setTwoFactorRequired(false);
                            setPendingCredentials(null);
                        }}
                    >
                        Back to sign in
                    </button>
                </form>
            </>
        );
    }

    return (
        <>
            <h1 className="form-title">Welcome back</h1>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
                <InputField
                    name="email"
                    label="Email"
                    placeholder="email@ejemplo.com"
                    register={register}
                    error={errors.email}
                    validation={{
                      required: 'Email is required',
                      pattern: {
                        value: /^[\w-.]+@([\w-]+\.)+[\w-]{2,}$/,
                        message: 'Please enter a valid email address'
                      }
                    }}
                />

                <InputField
                    name="password"
                    label="Password"
                    placeholder="Enter your password"
                    type="password"
                    register={register}
                    error={errors.password}
                    validation={{ required: 'Password is required', minLength: 8 }}
                />

                <Button type="submit" disabled={isSubmitting} className="yellow-btn w-full mt-5">
                    {isSubmitting ? 'Signing In' : 'Sign In'}
                </Button>

                <FooterLink text="Don't have an account?" linkText="Create an account" href="/sign-up" />
            </form>
        </>
    );
};
export default SignIn;