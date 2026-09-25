import React, { useId } from 'react'
import {Label} from "@/components/ui/label";
import {Controller} from "react-hook-form";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"

const SelectField = ({name, label, placeholder, options, control, error, required = false}: SelectFieldProps) => {
    const selectId = useId();
    const errorId = `${selectId}-error`;

    return (
        <div className="space-y-2">
            <Label htmlFor={selectId}>{label}{required ? <span aria-hidden="true"> *</span> : null}</Label>

            <Controller
                name={name}
                control={control}
                rules={{
                    required: required ? `Por favor, selecciona ${label.toLowerCase()}` : false,
                }}
                render={({field}) => (
                    <>
                        <Select value={field.value} onValueChange={field.onChange} required={required}>
                            <SelectTrigger
                                id={selectId}
                                aria-required={required}
                                aria-invalid={Boolean(error)}
                                aria-describedby={error ? errorId : undefined}
                                className="select-trigger"
                            >
                                <SelectValue placeholder={placeholder} />
                            </SelectTrigger>
                            <SelectContent className="bg-gray-800 border-gray-600 text-white">
                                {options.map((option) => (
                                    <SelectItem key={option.value} value={option.value} className="focus:bg-gray-600 focus: text-white">
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {error ? <p className="text-red-600" id={errorId}>{error.message}</p> : null}
                    </>
                )}
            />
            {error
                ? <p id={errorId} role="alert" className="text-sm text-red-500">{error.message}</p>
                : null}
        </div>
    )
}
export default SelectField
