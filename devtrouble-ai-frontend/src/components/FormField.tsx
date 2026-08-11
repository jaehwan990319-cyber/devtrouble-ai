import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

const FIELD_CLASSES =
  'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 ' +
  'placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500';

interface FieldWrapperProps {
  label?: string;
  error?: string;
  htmlFor?: string;
  children: ReactNode;
}

function FieldWrapper({ label, error, htmlFor, children }: FieldWrapperProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={htmlFor} className="text-sm font-medium text-slate-700">
          {label}
        </label>
      )}
      {children}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, id, className = '', ...rest }: InputProps) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={id}>
      <input id={id} className={`${FIELD_CLASSES} ${className}`} {...rest} />
    </FieldWrapper>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export function Textarea({ label, error, id, className = '', ...rest }: TextareaProps) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={id}>
      <textarea id={id} className={`${FIELD_CLASSES} min-h-24 resize-y ${className}`} {...rest} />
    </FieldWrapper>
  );
}

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
}

export function Select({ label, error, id, options, placeholder, className = '', ...rest }: SelectProps) {
  return (
    <FieldWrapper label={label} error={error} htmlFor={id}>
      <select id={id} className={`${FIELD_CLASSES} ${className}`} {...rest}>
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldWrapper>
  );
}
