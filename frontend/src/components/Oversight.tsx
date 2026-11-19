import type { ReactNode } from "react";
import { Link } from "react-router";
import type { QueueItem } from "../api/types";
import { formatWait } from "../lib/format";
import { CATEGORY_LABEL, ROUTE_LABEL, qualityFlagLabel } from "../lib/labels";
import { PriorityBadge, Tag } from "./Badges";

export interface KpiDef {
  label: string;
  value: ReactNode;
  hint?: string;
  /** "alert" only when the number means something is wrong right now. */
  tone?: "plain" | "alert";
}

/** Headline numbers. Text only: a stat tile needs no chart. */
export function KpiList({ items }: { items: KpiDef[] }) {
  return (
    <ul aria-label="Ключевые показатели" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((k) => (
        <li key={k.label} className="rounded-lg bg-surface px-4 py-3 ring-1 ring-line">
          <p className="text-xs text-muted">{k.label}</p>
          <p
            className={`mt-1 text-2xl font-semibold tabular-nums tracking-tight ${
              k.tone === "alert" ? "text-danger" : "text-ink"
            }`}
          >
            {k.value}
          </p>
          {k.hint && <p className="mt-0.5 text-xs text-muted">{k.hint}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Thin magnitude bar for a table cell; the number next to it carries the value. */
export function InlineBar({ value, max, label }: { value: number; max: number; label: string }) {
  const width = max > 0 ? Math.max(value > 0 ? 4 : 0, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2" title={label}>
      <span className="w-6 shrink-0 text-right tabular-nums">{value}</span>
      <span aria-hidden="true" className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-chip sm:w-40">
        <span className="block h-full rounded-r-[4px] bg-muted/70" style={{ width: `${width}%` }} />
      </span>
    </div>
  );
}

export function Panel({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: ReactNode;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="rounded-lg bg-surface ring-1 ring-line">
      <header className="border-b border-line px-4 py-3">
        <h2 id={id} className="text-sm font-semibold">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </header>
      {children}
    </section>
  );
}

/** One work item in an oversight list: why it is here and how long the player waits. */
export function CompactItem({ item }: { item: QueueItem }) {
  const name = item.player.display_name ?? item.player.player_id;
  return (
    <Link
      to={`/conversations/${item.conversation_id}`}
      className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-canvas"
    >
      <PriorityBadge priority={item.priority} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {name}
          <span className="font-normal text-muted"> · {item.player.manager_id ?? "без менеджера"}</span>
        </p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          <span className="text-xs text-muted">
            {item.category ? CATEGORY_LABEL[item.category] : "Разбор не выполнен"}
          </span>
          {item.route !== "manager" && <Tag tone="danger">{ROUTE_LABEL[item.route]}</Tag>}
          {item.quality_flags.map((f) => (
            <Tag key={f} tone="danger">
              {qualityFlagLabel(f)}
            </Tag>
          ))}
        </div>
      </div>
      <span className={`shrink-0 text-sm tabular-nums ${item.overdue ? "font-medium text-danger" : "text-muted"}`}>
        {item.awaiting_reply ? formatWait(item.wait_hours) : "не ждёт"}
      </span>
    </Link>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
      <p>{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 rounded-md bg-surface px-2.5 py-1 font-medium ring-1 ring-danger-line hover:bg-white"
      >
        Повторить
      </button>
    </div>
  );
}

export function LoadingBlocks() {
  return (
    <div aria-busy="true" className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg bg-surface ring-1 ring-line" />
        ))}
      </div>
      <div className="h-48 animate-pulse rounded-lg bg-surface ring-1 ring-line" />
    </div>
  );
}

/** Russian plural: plural(5, ["диалог", "диалога", "диалогов"]) -> "диалогов". */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}
