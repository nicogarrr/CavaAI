'use client';

import {useForm} from "react-hook-form";
import {Button} from "@/components/ui/button";
import InputField from "@/components/forms/InputField";
import SelectField from "@/components/forms/SelectField";
import {INVESTMENT_GOALS, PREFERRED_INDUSTRIES, RISK_TOLERANCE_OPTIONS} from "@/lib/constants";
import {CountrySelectField} from "@/components/forms/CountrySelectField";
import FooterLink from "@/components/forms/FooterLink";
import {signUpWithEmail} from "@/lib/actions/auth.actions";
import {useRouter} from "next/navigation";
import {toast} from "sonner";
import React from "react";

const SignUp = () => {
    const router = useRouter()
    const {
        register,
        handleSubmit,
        control,
        formState: { errors, isSubmitting },
    } = useForm<SignUpFormData>({
        defaultValues: {
            fullName: '',
            email: '',
            password: '',
            country: 'ES',
            investmentGoals: 'Growth',
            riskTolerance: 'Medium',
            preferredIndustry: 'Technology'
        },
        mode: 'onBlur'
    }, );

    const onSubmit = async (data: SignUpFormData) => {
        try {
            const result = await signUpWithEmail(data);
            if (result.success) {
                router.push('/');
                return;
            }
            toast.error('No se pudo crear la cuenta', {
                description: result.error ?? 'We could not create your account.',
            });
        } catch (e) {
            toast.error('No se pudo crear la cuenta', {
                description: e instanceof Error ? e.message : 'An unexpected error occurred. Please try again.'
            })
        }
    }

    return (
        <>
            <h1 className="form-title">Crea tu cuenta</h1>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
                <InputField
                    name="fullName"
                    label="Nombre completo"
                    placeholder="Introduce tu nombre completo"
                    register={register}
                    error={errors.fullName}
                    validation={{ required: 'El nombre es obligatorio', minLength: 2 }}
                />

                <InputField
                    name="email"
                    label="Email"
                    placeholder="email@ejemplo.com"
                    register={register}
                    error={errors.email}
                    validation={{
                      required: 'El email es obligatorio',
                      pattern: {
                        value: /^[\w-.]+@([\w-]+\.)+[\w-]{2,}$/,
                        message: 'Introduce un email válido'
                      }
                    }}
                />

                <InputField
                    name="password"
                    label="Contraseña"
                    placeholder="Crea una contraseña segura"
                    type="password"
                    autoComplete="new-password"
                    register={register}
                    error={errors.password}
                    validation={{ required: 'La contraseña es obligatoria', minLength: 8 }}
                />

                <CountrySelectField
                    name="country"
                    label="País"
                    control={control}
                    error={errors.country}
                    required
                />

                <SelectField
                    name="investmentGoals"
                    label="Objetivo de inversión"
                    placeholder="Selecciona tu objetivo"
                    options={INVESTMENT_GOALS}
                    control={control}
                    error={errors.investmentGoals}
                    required
                />

                <SelectField
                    name="riskTolerance"
                    label="Tolerancia al riesgo"
                    placeholder="Selecciona tu nivel de riesgo"
                    options={RISK_TOLERANCE_OPTIONS}
                    control={control}
                    error={errors.riskTolerance}
                    required
                />

                <SelectField
                    name="preferredIndustry"
                    label="Sector preferido"
                    placeholder="Selecciona tu sector preferido"
                    options={PREFERRED_INDUSTRIES}
                    control={control}
                    error={errors.preferredIndustry}
                    required
                />

                <Button type="submit" disabled={isSubmitting} className="yellow-btn w-full mt-5">
                    {isSubmitting ? 'Creando cuenta' : 'Empieza tu viaje inversor'}
                </Button>

                <FooterLink text="¿Ya tienes cuenta?" linkText="Iniciar sesión" href="/sign-in" />
            </form>
        </>
    )
}
export default SignUp;
