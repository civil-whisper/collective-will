import {ReactNode} from "react";

type Props = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
};

export function PageShell({title, subtitle, children, actions}: Props) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-base font-bold tracking-tight sm:text-2xl">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}
