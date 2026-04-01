import type { ButtonHTMLAttributes, PropsWithChildren } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, PropsWithChildren {
  variant?: 'default' | 'primary' | 'ghost' | 'danger';
}

export function Button({ variant = 'default', className = '', children, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`button button--${variant} ${className}`.trim()}
    >
      {children}
    </button>
  );
}
