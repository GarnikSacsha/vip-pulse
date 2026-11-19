import { Link, useOutletContext, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { Meta, Priority, QueueFilters, QueueItem, TaskStatus } from "../api/types";
import { PriorityBadge, Tag } from "../components/Badges";
import { formatWait } from "../lib/format";
import { CATEGORY_LABEL, CHANNEL_LABEL, ROUTE_LABEL, STATUS_LABEL, qualityFlagLabel } from "../lib/labels";
import { useApi } from "../lib/useApi";

type View = "active" | "all" | "resolved" | "no_action";

interface ViewDef {
  id: View;
  label: string;
  statuses?: TaskStatus[];
}

// The default view: what still needs the manager.
const ACTIVE_VIEW: ViewDef = { id: "active", label: "Активные", statuses: ["open", "in_progress"] };
const VIEWS: ViewDef[] = [
  ACTIVE_VIEW,
  { id: "all", label: "Все" },
  { id: "resolved", label: "Решённые", statuses: ["resolved"] },
  { id: "no_action", label: "Без действий", statuses: ["no_action"] },
];
const PRIORITIES: Priority[] = ["P0", "P1", "P2", "P3"];

function viewCount(view: ViewDef, meta: Meta | null): number | null {
  if (!meta) return null;
  if (!view.statuses) return meta.counts.total;
  return view.statuses.reduce((sum, s) => sum + meta.counts.by_status[s], 0);
}

export interface ShellContext {
  meta: Meta | null;
}

export function QueuePage() {
  const { meta } = useOutletContext<ShellContext>();
  const [params, setParams] = useSearchParams();
  const view = VIEWS.find((v) => v.id === params.get("view")) ?? ACTIVE_VIEW;
  const priority = PRIORITIES.find((p) => p === params.get("priority"));

  const filters: QueueFilters = {
    ...(view.statuses ? { status: view.statuses } : {}),
    ...(priority ? { priority: [priority] } : {}),
  };
  const queue = useApi(() => api.queue(filters), JSON.stringify(filters));

  function update(next: { view?: View; priority?: Priority | null }) {
    const p = new URLSearchParams(params);
    const v = next.view ?? view.id;
    if (v === "active") p.delete("view");
    else p.set("view", v);
    const pr = next.priority === undefined ? priority : next.priority;
    if (pr) p.set("priority", pr);
    else p.delete("priority");
    setParams(p);
  }

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Очередь</h1>
          <p className="mt-0.5 text-sm text-muted">
            Сначала самое срочное, внутри приоритета — кто дольше ждёт ответа.
          </p>
        </div>
        <div className="flex items-center gap-1" aria-label="Фильтр по приоритету">
          {PRIORITIES.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={priority === p}
              onClick={() => update({ priority: priority === p ? null : p })}
              className={`h-7 rounded-md px-2.5 text-xs font-semibold tabular-nums ring-1 ring-inset transition-colors ${
                priority === p ? "bg-ink text-white ring-ink" : "bg-surface text-muted ring-line hover:text-ink"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div role="tablist" className="mb-3 flex gap-5 overflow-x-auto border-b border-line text-sm">
        {VIEWS.map((v) => {
          const selected = v.id === view.id;
          const count = viewCount(v, meta);
          return (
            <button
              key={v.id}
              role="tab"
              type="button"
              aria-selected={selected}
              onClick={() => update({ view: v.id })}
              className={`-mb-px flex shrink-0 items-center gap-1.5 border-b-2 pb-2 ${
                selected ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {v.label}
              {count !== null && (
                <>
                  {" "}
                  <span className="text-xs tabular-nums text-muted">{count}</span>
                </>
              )}
            </button>
          );
        })}
      </div>

      <QueueBody queue={queue} />
    </section>
  );
}

function QueueBody({ queue }: { queue: ReturnType<typeof useApi<QueueItem[]>> }) {
  if (queue.error) {
    return (
      <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
        <p>Не удалось загрузить очередь: {queue.error}</p>
        <button
          type="button"
          onClick={queue.reload}
          className="mt-2 rounded-md bg-surface px-2.5 py-1 font-medium ring-1 ring-danger-line hover:bg-white"
        >
          Повторить
        </button>
      </div>
    );
  }
  if (!queue.data) {
    return (
      <div aria-busy="true" className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg bg-surface ring-1 ring-line" />
        ))}
      </div>
    );
  }
  if (queue.data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-surface px-4 py-10 text-center">
        <p className="text-sm font-medium">Нет диалогов по этому фильтру</p>
        <p className="mt-1 text-sm text-muted">Попробуйте вкладку «Все» или снимите фильтр приоритета.</p>
      </div>
    );
  }
  return (
    <ul
      className={`divide-y divide-line overflow-hidden rounded-lg bg-surface ring-1 ring-line ${
        queue.loading ? "opacity-60" : ""
      }`}
    >
      {queue.data.map((item) => (
        <li key={item.task_id}>
          <QueueRow item={item} />
        </li>
      ))}
    </ul>
  );
}

function QueueRow({ item }: { item: QueueItem }) {
  const name = item.player.display_name ?? item.player.player_id;
  return (
    <Link
      to={`/conversations/${item.conversation_id}`}
      className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-4 py-3.5 transition-colors hover:bg-canvas sm:grid-cols-[auto_minmax(0,14rem)_1fr_auto]"
    >
      <div className="pt-0.5">
        <PriorityBadge priority={item.priority} />
      </div>

      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="mt-0.5 flex gap-1.5 truncate text-xs text-muted">
          <span>{item.player.player_id}</span>
          {item.player.segment && <span>· {item.player.segment}</span>}
          <span aria-hidden="true">·</span>
          <span>{CHANNEL_LABEL[item.channel]}</span>
        </p>
      </div>

      <div className="col-span-2 min-w-0 sm:col-span-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm">{item.category ? CATEGORY_LABEL[item.category] : "Разбор не выполнен"}</span>
          {item.route !== "manager" && <Tag tone="danger">{ROUTE_LABEL[item.route]}</Tag>}
          {item.quality_flags.map((f) => (
            <Tag key={f} tone="danger">
              {qualityFlagLabel(f)}
            </Tag>
          ))}
          {item.requires_review && <Tag tone="warn">Нужна проверка</Tag>}
          {(item.status === "in_progress" || item.status === "resolved") && (
            <Tag tone={item.status === "resolved" ? "ok" : "accent"}>{STATUS_LABEL[item.status]}</Tag>
          )}
        </div>
        {item.next_action && <p className="mt-1 line-clamp-2 text-sm text-muted">{item.next_action}</p>}
      </div>

      <div className="col-span-2 text-left sm:col-span-1 sm:text-right">
        <p className={`text-sm tabular-nums ${item.awaiting_reply ? "font-medium" : "text-muted"}`}>
          {item.awaiting_reply ? formatWait(item.wait_hours) : "не ждёт"}
        </p>
        {item.awaiting_reply && <p className="text-xs text-muted">ждёт ответа</p>}
      </div>
    </Link>
  );
}
