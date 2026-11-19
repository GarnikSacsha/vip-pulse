import type { ReactNode } from "react";
import type { Priority } from "../api/types";
import { PRIORITY_LABEL } from "../lib/labels";

const PRIORITY_STYLE: Record<Priority, string> = {
  P0: "bg-p0-soft text-p0 ring-p0/25",
  P1: "bg-p1-soft text-p1 ring-p1/25",
  P2: "bg-p2-soft text-p2 ring-p2/20",
  P3: "bg-p3-soft text-p3 ring-p3/20",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span
      title={PRIORITY_LABEL[priority]}
      className={`inline-flex h-6 min-w-9 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums ring-1 ring-inset ${PRIORITY_STYLE[priority]}`}
    >
      {priority}
    </span>
  );
}

type Tone = "neutral" | "warn" | "danger" | "accent" | "ok";

const TONE: Record<Tone, string> = {
  neutral: "bg-chip text-muted",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
  accent: "bg-evidence-soft text-evidence",
  ok: "bg-ok-soft text-ok",
};

export function Tag({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${TONE[tone]}`}>
      {children}
    </span>
  );
}
