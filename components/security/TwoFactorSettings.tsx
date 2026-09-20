'use client';

import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import InputField from '@/components/forms/InputField';
import { useForm } from 'react-hook-form';
import {
    activateTwoFactorTotp,
    disableTwoFactor,
    enableTwoFactorTotp,
} from '@/lib/actions/auth.actions';

type Props = {
    initiallyEnabled: boolean;
};

type PasswordForm = { password: string };
type TotpForm = { totpCode: string };

export default function TwoFactorSettings({ initiallyEnabled }: Props) {
    const [enabled, setEnabled] = useState(initiallyEnabled);
    const [setup, setSetup] = useState<{ totpURI: string; backupCodes: string[] } | null>(null);
    const [busy, setBusy] = useState(false);

    const passwordForm = useForm<PasswordForm>({ mode: 'onBlur' });
    const totpForm = useForm<TotpForm>({
        defaultValues: { totpCode: '' },
        mode: 'onBlur',
    });

    const handleEnable = async ({ password }: PasswordForm) => {
        setBusy(true);
        try {
            const result = await enableTwoFactorTotp({ password });
            if (!result.success || !result.data?.totpURI) {
                toast.error('Unable to enable 2FA', { description: result.error ?? 'Please try again.' });
                return;
            }
            setSetup({
                totpURI: result.data.totpURI,
                backupCodes: result.data.backupCodes ?? [],
            });
            passwordForm.reset();
        } finally {
            setBusy(false);
        }
    };

    const handleActivate = async ({ totpCode }: TotpForm) => {
        setBusy(true);
        try {
            const result = await activateTwoFactorTotp({ totpCode });
            if (!result.success) {
                toast.error('Verification failed', { description: result.error ?? 'Invalid code.' });
                return;
            }
            setSetup(null);
            setEnabled(true);
            totpForm.reset();
            toast.success('Two-factor authentication enabled');
        } finally {
            setBusy(false);
        }
    };

    const handleDisable = async ({ password }: PasswordForm) => {
        setBusy(true);
        try {
            const result = await disableTwoFactor({ password });
            if (!result.success) {
                toast.error('Unable to disable 2FA', { description: result.error ?? 'Please try again.' });
                return;
            }
            setEnabled(false);
            passwordForm.reset();
            toast.success('Two-factor authentication disabled');
        } finally {
            setBusy(false);
        }
    };

    const copyBackupCodes = async () => {
        if (!setup) return;
        try {
            await navigator.clipboard.writeText(setup.backupCodes.join('\n'));
            toast.success('Backup codes copied to clipboard');
        } catch {
            toast.error('Could not copy codes — write them down manually');
        }
    };

    return (
        <div className="max-w-xl space-y-6">
            <div>
                <h2 className="text-xl font-semibold text-white">Two-factor authentication</h2>
                <p className="text-sm text-gray-400 mt-1">
                    Protect your account with a time-based one-time code from an authenticator
                    app (Google Authenticator, 1Password, Authy&hellip;).
                </p>
            </div>

            {enabled && (
                <div className="rounded-lg border border-green-800/50 bg-green-950/20 p-4">
                    <p className="text-sm text-green-400 font-medium">✓ 2FA is enabled on your account</p>
                    <p className="text-xs text-gray-400 mt-1">
                        Every sign-in now requires your authenticator code in addition to your password.
                    </p>
                </div>
            )}

            {!enabled && !setup && (
                <form onSubmit={passwordForm.handleSubmit(handleEnable)} className="space-y-4 rounded-lg border border-gray-800 p-5">
                    <p className="text-sm text-gray-300">To enable 2FA, confirm your password:</p>
                    <InputField
                        name="password"
                        label="Your password"
                        placeholder="Enter your password"
                        type="password"
                        register={passwordForm.register}
                        error={passwordForm.formState.errors.password}
                        validation={{ required: 'Password is required' }}
                    />
                    <Button type="submit" disabled={busy} className="yellow-btn">
                        {busy ? 'Generating…' : 'Enable 2FA'}
                    </Button>
                </form>
            )}

            {setup && (
                <div className="space-y-5 rounded-lg border border-gray-800 p-5">
                    <p className="text-sm text-gray-300 font-medium">1 · Scan the QR code</p>
                    <div className="flex items-center gap-5">
                        <div className="rounded-lg bg-white p-3">
                            <QRCodeSVG value={setup.totpURI} size={160} />
                        </div>
                        <p className="text-xs text-gray-400 max-w-[220px]">
                            Open your authenticator app and scan this code, or enter the key
                            manually from the app&apos;s settings.
                        </p>
                    </div>

                    <div>
                        <p className="text-sm text-gray-300 font-medium">2 · Save your backup codes</p>
                        <p className="text-xs text-gray-500 mt-1">
                            These one-time codes let you recover access if you lose your authenticator.
                            Store them somewhere safe.
                        </p>
                        <div className="mt-2 rounded-md bg-gray-900 border border-gray-800 p-3 font-mono text-xs text-gray-300 grid grid-cols-2 gap-1">
                            {setup.backupCodes.map((code) => (
                                <span key={code}>{code}</span>
                            ))}
                        </div>
                        <Button type="button" variant="outline" size="sm" className="mt-2" onClick={copyBackupCodes}>
                            Copy backup codes
                        </Button>
                    </div>

                    <form onSubmit={totpForm.handleSubmit(handleActivate)} className="space-y-4 pt-2">
                        <p className="text-sm text-gray-300 font-medium">3 · Confirm the code</p>
                        <InputField
                            name="totpCode"
                            label="6-digit code"
                            placeholder="000000"
                            autoComplete="one-time-code"
                            register={totpForm.register}
                            error={totpForm.formState.errors.totpCode}
                            validation={{
                                required: 'Code is required',
                                pattern: { value: /^\d{6}$/, message: 'Code must be 6 digits' },
                            }}
                        />
                        <Button type="submit" disabled={busy} className="yellow-btn">
                            {busy ? 'Verifying…' : 'Activate 2FA'}
                        </Button>
                        <button
                            type="button"
                            className="block text-sm text-gray-500 hover:text-gray-300"
                            onClick={() => setSetup(null)}
                        >
                            Cancel
                        </button>
                    </form>
                </div>
            )}

            {enabled && (
                <form onSubmit={passwordForm.handleSubmit(handleDisable)} className="space-y-4 rounded-lg border border-gray-800 p-5">
                    <p className="text-sm text-gray-300">To disable 2FA, confirm your password:</p>
                    <InputField
                        name="password"
                        label="Your password"
                        placeholder="Enter your password"
                        type="password"
                        register={passwordForm.register}
                        error={passwordForm.formState.errors.password}
                        validation={{ required: 'Password is required' }}
                    />
                    <Button type="submit" disabled={busy} variant="destructive" className="w-full sm:w-auto">
                        {busy ? 'Disabling…' : 'Disable 2FA'}
                    </Button>
                </form>
            )}
        </div>
    );
}