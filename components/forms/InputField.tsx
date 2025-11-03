import React from 'react'
import {Label} from "@/components/ui/label";
import {Input} from "@/components/ui/input";
import {cn} from "@/lib/utils";

const InputField = ({name, label, placeholder, type ="text", register, error, validation, disabled, value, autoComplete}: FormInputProps) => {
    // Determinar el autocompletado si no se proporciona explícitamente
    const getAutoComplete = () => {
        if (autoComplete) return autoComplete;
        if (type === 'password') return 'current-password';
        if (type === 'email') return 'email';
        return undefined;
    };
    
    return (
        <div className="space-y-2">
            <Label htmlFor={name} className="form-label">
                {label}
            </Label>
            <Input
                type={type}
                id={name}
                placeholder={placeholder}
                disabled={disabled}
                value={value}
                autoComplete={getAutoComplete()}
                className={cn('form-input', {'opacity-50 cursor-not-allowed': disabled})}
                {...register(name, validation)}
            />
            {error && <p className="text-red-500">{error.message}</p>}
        </div>
    )
}
export default InputField
