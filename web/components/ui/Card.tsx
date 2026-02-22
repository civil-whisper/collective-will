import {ReactNode} from "react";

type Props = {
  children: ReactNode;
  className?: string;
};

export function Card({children, className = ""}: Props) {
  return (
    <div
      className={`rounded-lg border border-gray-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800 ${className}`}
    >
      {children}
    </div>
  );
}
