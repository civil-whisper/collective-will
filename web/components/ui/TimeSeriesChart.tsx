"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import {Card} from "./Card";

export type TimeSeriesPoint = {
  label: string;
  value: number;
};

type Props = {
  data: TimeSeriesPoint[];
  title?: string;
  color?: string;
  height?: number;
};

export function TimeSeriesChart({
  data,
  title,
  color = "#4f46e5",
  height = 280,
}: Props) {
  return (
    <Card>
      {title && (
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
          {title}
        </h3>
      )}
      {data.length === 0 ? (
        <div
          className="flex items-center justify-center text-sm text-gray-400 dark:text-slate-500"
          style={{height}}
        >
          No data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={data} margin={{top: 4, right: 4, bottom: 0, left: -20}}>
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="var(--border-color)"
            />
            <XAxis
              dataKey="label"
              tick={{fontSize: 12, fill: "var(--text-secondary)"}}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{fontSize: 12, fill: "var(--text-secondary)"}}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                borderRadius: "0.5rem",
                fontSize: "0.875rem",
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill="url(#chartGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
