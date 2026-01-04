'use client';

import { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

// Base input styling
const baseInputClasses =
  'w-full px-3 py-2.5 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50 transition-colors';

const labelClasses = 'block text-sm font-medium text-[#a1a1a6] mb-1.5';
const hintClasses = 'text-xs text-[#636366] mt-1';

interface FormFieldProps {
  label?: string;
  hint?: string;
  required?: boolean;
  error?: string;
}

// Text Input
interface TextInputProps
  extends FormFieldProps,
    Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> {}

export function TextInput({
  label,
  hint,
  required,
  error,
  ...props
}: TextInputProps) {
  return (
    <div>
      {label && (
        <label className={labelClasses}>
          {label} {required && <span className="text-red-400">*</span>}
        </label>
      )}
      <input className={baseInputClasses} {...props} />
      {hint && !error && <p className={hintClasses}>{hint}</p>}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

// Number Input
interface NumberInputProps
  extends FormFieldProps,
    Omit<InputHTMLAttributes<HTMLInputElement>, 'className' | 'type'> {}

export function NumberInput({
  label,
  hint,
  required,
  error,
  ...props
}: NumberInputProps) {
  return (
    <div>
      {label && (
        <label className={labelClasses}>
          {label} {required && <span className="text-red-400">*</span>}
        </label>
      )}
      <input type="number" className={baseInputClasses} {...props} />
      {hint && !error && <p className={hintClasses}>{hint}</p>}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

// Select
interface SelectInputProps
  extends FormFieldProps,
    Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className'> {
  options: { value: string | number; label: string }[];
  placeholder?: string;
}

export function SelectInput({
  label,
  hint,
  required,
  error,
  options,
  placeholder,
  ...props
}: SelectInputProps) {
  return (
    <div>
      {label && (
        <label className={labelClasses}>
          {label} {required && <span className="text-red-400">*</span>}
        </label>
      )}
      <select className={baseInputClasses} {...props}>
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint && !error && <p className={hintClasses}>{hint}</p>}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

// Textarea
interface TextareaInputProps
  extends FormFieldProps,
    Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'> {}

export function TextareaInput({
  label,
  hint,
  required,
  error,
  ...props
}: TextareaInputProps) {
  return (
    <div>
      {label && (
        <label className={labelClasses}>
          {label} {required && <span className="text-red-400">*</span>}
        </label>
      )}
      <textarea className={`${baseInputClasses} resize-none`} {...props} />
      {hint && !error && <p className={hintClasses}>{hint}</p>}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

// Toggle/Switch
interface ToggleProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled = false,
}: ToggleProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <label className="block text-sm font-medium text-white">{label}</label>
        {description && (
          <p className="text-xs text-[#636366]">{description}</p>
        )}
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative w-12 h-7 rounded-full transition-colors ${
          checked ? 'bg-amber-500' : 'bg-[#3a3a3f]'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <div
          className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );
}

// Read-only display field
interface DisplayFieldProps {
  label: string;
  value: string | number;
}

export function DisplayField({ label, value }: DisplayFieldProps) {
  return (
    <div>
      <label className={labelClasses}>{label}</label>
      <div className="px-3 py-2.5 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-[#636366] font-mono">
        {value}
      </div>
    </div>
  );
}
