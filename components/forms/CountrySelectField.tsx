/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useState } from 'react';
import { Control, Controller, FieldError, FieldValues, Path } from 'react-hook-form';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import countryList from 'react-select-country-list';

type CountrySelectProps<TFieldValues extends FieldValues = FieldValues> = {
    name: Path<TFieldValues>;
    label: string;
    control: Control<TFieldValues, any, any>;
    error?: FieldError;
    required?: boolean;
};

const CountrySelect = ({
                           value,
                           onChange,
                           invalid = false,
                           describedBy,
                           label,
                       }: {
    value: string;
    onChange: (value: string) => void;
    invalid?: boolean;
    describedBy?: string;
    label: string;
}) => {
    const [open, setOpen] = useState(false);

    // Get country options with flags
    const countries = countryList().getData();

    // Helper function to get flag emoji
    const getFlagEmoji = (countryCode: string) => {
        const codePoints = countryCode
            .toUpperCase()
            .split('')
            .map((char) => 127397 + char.charCodeAt(0));
        return String.fromCodePoint(...codePoints);
    };

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant='outline'
                    role='combobox'
                    aria-expanded={open}
                    aria-label={label}
                    aria-invalid={invalid}
                    aria-describedby={describedBy}
                    className='country-select-trigger'
                >
                    {value ? (
                        <span className='flex items-center gap-2'>
              <span>{getFlagEmoji(value)}</span>
              <span>{countries.find((c) => c.value === value)?.label}</span>
            </span>
                    ) : (
                        'Selecciona tu país…'
                    )}
                    <ChevronsUpDown className='ml-2 h-4 w-4 shrink-0 opacity-50' />
                </Button>
            </PopoverTrigger>
            <PopoverContent
                className='w-full p-0 bg-gray-800 border-gray-600'
                align='start'
            >
                <Command className='bg-gray-800 border-gray-600'>
                    <CommandInput
                        placeholder='Buscar países…'
                        className='country-select-input'
                    />
                    <CommandEmpty className='country-select-empty'>
                        No se ha encontrado ningún país.
                    </CommandEmpty>
                    <CommandList className='max-h-60 bg-gray-800 scrollbar-hide-default'>
                        <CommandGroup className='bg-gray-800'>
                            {countries.map((country) => (
                                <CommandItem
                                    key={country.value}
                                    value={`${country.label} ${country.value}`}
                                    onSelect={() => {
                                        onChange(country.value);
                                        setOpen(false);
                                    }}
                                    className='country-select-item'
                                >
                                    <Check
                                        className={cn(
                                            'mr-2 h-4 w-4 text-teal-500',
                                            value === country.value ? 'opacity-100' : 'opacity-0'
                                        )}
                                    />
                                    <span className='flex items-center gap-2'>
                    <span>{getFlagEmoji(country.value)}</span>
                    <span>{country.label}</span>
                  </span>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
};

export const CountrySelectField = <TFieldValues extends FieldValues = FieldValues>({
                                       name,
                                       label,
                                       control,
                                       error,
                                       required = false,
                                   }: CountrySelectProps<TFieldValues>) => {
    const errorId = `${name}-error`;
    const hintId = `${name}-hint`;
    return (
        <div className='space-y-2'>
            <Label htmlFor={name} className='form-label'>
                {label}
            </Label>
            <Controller
                name={name}
                control={control}
                rules={{
                    required: required ? `Por favor, selecciona ${label.toLowerCase()}` : false,
                }}
                render={({ field }) => (
                    <CountrySelect
                        value={field.value}
                        onChange={field.onChange}
                        label={label}
                        invalid={!!error}
                        describedBy={error ? errorId : hintId}
                    />
                )}
            />
            {error ? <p id={errorId} role='alert' className='text-sm text-red-500'>{error.message}</p> : null}
            <p id={hintId} className='text-xs text-gray-500'>
                Te mostramos datos de mercado y noticias relevantes según tu país.
            </p>
        </div>
    );
};