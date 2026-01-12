import * as React from 'react';
import { cn } from '@/lib/utils';

interface SelectProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
}

interface SelectTriggerProps {
  children: React.ReactNode;
  className?: string;
}

interface SelectContentProps {
  children: React.ReactNode;
}

interface SelectItemProps {
  value: string;
  children: React.ReactNode;
}

interface SelectValueProps {
  placeholder?: string;
}

const SelectContext = React.createContext<{
  value: string;
  onValueChange: (value: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}>({
  value: '',
  onValueChange: () => {},
  open: false,
  setOpen: () => {},
});

export function Select({ value, onValueChange, children }: SelectProps) {
  const [open, setOpen] = React.useState(false);
  return (
    <SelectContext.Provider value={{ value, onValueChange, open, setOpen }}>
      <div className="relative">{children}</div>
    </SelectContext.Provider>
  );
}

export function SelectTrigger({ children, className }: SelectTriggerProps) {
  const { open, setOpen } = React.useContext(SelectContext);
  return (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      className={cn(
        'flex h-9 w-full items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-gray-400 disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
    >
      {children}
      <svg
        className="h-4 w-4 opacity-50"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    </button>
  );
}

export function SelectValue({ placeholder }: SelectValueProps) {
  const { value } = React.useContext(SelectContext);
  return <span>{value || placeholder}</span>;
}

export function SelectContent({ children }: SelectContentProps) {
  const { open, setOpen } = React.useContext(SelectContext);

  React.useEffect(() => {
    const handleClick = () => setOpen(false);
    if (open) {
      document.addEventListener('click', handleClick);
    }
    return () => document.removeEventListener('click', handleClick);
  }, [open, setOpen]);

  if (!open) return null;

  return (
    <div
      className="absolute z-50 mt-1 w-full rounded-md border bg-white shadow-lg"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="py-1">{children}</div>
    </div>
  );
}

export function SelectItem({ value, children }: SelectItemProps) {
  const { value: selectedValue, onValueChange, setOpen } = React.useContext(SelectContext);
  const isSelected = value === selectedValue;

  return (
    <div
      className={cn(
        'cursor-pointer px-3 py-2 text-sm hover:bg-gray-100',
        isSelected && 'bg-gray-50 font-medium'
      )}
      onClick={() => {
        onValueChange(value);
        setOpen(false);
      }}
    >
      {children}
    </div>
  );
}
