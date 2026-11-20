import { type RefObject, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { Meta, Priority, QueueFilters, QueueItem, TaskStatus } from "../api/types";
import { PriorityBadge, Tag } from "../components/Badges";
import { Pulse } from "../components/Pulse";
import { formatWait } from "../lib/format";
import { CATEGORY_LABEL, CHANNEL_LABEL, ROUTE_LABEL, STATUS_LABEL, alertText, qualityFlagLabel } from "../lib/labels";
import { managerOf, useRole } from "../lib/role";
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
  /** Refresh the department counters (tab counts) after a change. */
  reloadMeta?: () => void;
}

export type PaneTab = "analysis" | "player";

/** What the conversation pane gets from the inbox. */
export interface InboxContext {
  /** Refresh the list and the counters after a status change in the pane. */
  reloadQueue: () => void;
  /** The open tab of the right pane; kept while moving between conversations. */
  pane: PaneTab;
  setPane: (tab: PaneTab) => void;
}

/** True when a key press belongs to a text field, not to the inbox shortcuts. */
function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * The manager's inbox. Three panes on wide screens: the queue, the conversation and its analysis.
 * On narrow screens the list and the conversation take turns, as list → detail navigation.
 */
export function QueuePage() {
  const { meta, reloadMeta } = useOutletContext<ShellContext>();
  const [pane, setPane] = useState<PaneTab>("analysis");
  const { id: selected } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const view = VIEWS.find((v) => v.id === params.get("view")) ?? ACTIVE_VIEW;
  const priority = PRIORITIES.find((p) => p === params.get("priority"));
  // A manager role sees only their own players (demo filter, not authorisation).
  const roleManager = managerOf(useRole().role);
  const manager = roleManager ?? params.get("manager");

  const filters: QueueFilters = {
    ...(view.statuses ? { status: view.statuses } : {}),
    ...(priority ? { priority: [priority] } : {}),
    ...(manager ? { manager: [manager] } : {}),
  };
  const queue = useApi(() => api.queue(filters), JSON.stringify(filters));

  // j / k: next and previous conversation, wherever the focus is, except inside text fields.
  const items = queue.data;
  const listRef = useRef<HTMLUListElement>(null);
  // Where the selection was: when it leaves the list (e.g. resolved), j/k continue from that spot.
  const lastIndex = useRef<number | null>(null);
  useEffect(() => {
    const at = items?.findIndex((i) => i.conversation_id === selected) ?? -1;
    if (at !== -1) lastIndex.current = at;
  }, [items, selected]);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.altKey || e.ctrlKey || e.metaKey || typing(e.target) || !items?.length) return;
      if (e.key !== "j" && e.key !== "k") return;
      const last = items.length - 1;
      const at = items.findIndex((i) => i.conversation_id === selected);
      let index: number;
      if (at !== -1) index = e.key === "j" ? Math.min(at + 1, last) : Math.max(at - 1, 0);
      else if (selected && lastIndex.current !== null)
        // The old position now holds the item that came after the one that left.
        index = e.key === "j" ? Math.min(lastIndex.current, last) : Math.max(lastIndex.current - 1, 0);
      else index = 0;
      const target = items[index];
      if (!target || target.conversation_id === selected) return;
      e.preventDefault();
      navigate({ pathname: `/queue/${encodeURIComponent(target.conversation_id)}`, search: location.search });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, selected, navigate, location.search]);

  // Keep the selected row in view when it changes from the keyboard.
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView?.({ block: "nearest" });
  }, [selected, items]);

  function clearManager() {
    const p = new URLSearchParams(params);
    p.delete("manager");
    setParams(p);
  }

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
    <div className="lg:grid lg:h-full lg:grid-cols-[minmax(20rem,24rem)_minmax(0,1fr)]">
      <section
        aria-label="Список диалогов"
        className={`${selected ? "hidden lg:flex" : "flex"} min-h-0 flex-col border-line lg:border-r`}
      >
        <div className="shrink-0 px-4 pt-5 sm:px-5">
          <div className="flex items-end justify-between gap-3">
            <h1 className="text-xl font-semibold tracking-tight">Очередь</h1>
            <div role="group" className="flex items-center gap-1" aria-label="Фильтр по приоритету">
              {PRIORITIES.map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={priority === p}
                  onClick={() => update({ priority: priority === p ? null : p })}
                  className={`h-6 rounded-md px-1.5 text-xs font-semibold tabular-nums ring-1 ring-inset transition-colors ${
                    priority === p ? "bg-ink text-white ring-ink" : "bg-surface text-muted ring-line hover:text-ink"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <p className="mt-0.5 text-xs text-muted">
            Сначала самое срочное, внутри приоритета — кто дольше ждёт.{" "}
            <span className="hidden lg:inline">
              <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> — следующий и предыдущий.
            </span>
          </p>
          {manager && !roleManager && (
            <button
              type="button"
              onClick={clearManager}
              aria-label={`Менеджер ${manager}: снять фильтр`}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-chip px-2 py-0.5 text-xs font-medium hover:bg-line"
            >
              Менеджер {manager}
              <span aria-hidden="true">×</span>
            </button>
          )}

          <div role="tablist" className="mt-3 flex gap-4 overflow-x-auto border-b border-line text-sm">
            {VIEWS.map((v) => {
              const isSelected = v.id === view.id;
              // Meta counts the whole department: wrong on one manager's queue, so hidden there.
              const count = manager ? null : viewCount(v, meta);
              return (
                <button
                  key={v.id}
                  role="tab"
                  type="button"
                  aria-selected={isSelected}
                  onClick={() => update({ view: v.id })}
                  className={`-mb-px flex shrink-0 items-center gap-1.5 border-b-2 pb-2 ${
                    isSelected ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink"
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
        </div>

        <div className="min-h-0 flex-1 lg:overflow-y-auto">
          <QueueBody queue={queue} managerFilter={Boolean(manager)} listRef={listRef} search={location.search} />
        </div>
      </section>

      {/* lg..xl: the conversation and its analysis stack and scroll together; from xl each pane scrolls. */}
      <div className={`${selected ? "block" : "hidden lg:block"} min-h-0 lg:h-full lg:overflow-y-auto`}>
        <Outlet
          context={
            {
              reloadQueue: () => {
                queue.reload();
                reloadMeta?.();
              },
              pane,
              setPane,
            } satisfies InboxContext
          }
        />
      </div>
    </div>
  );
}

function QueueBody({
  queue,
  managerFilter,
  listRef,
  search,
}: {
  queue: ReturnType<typeof useApi<QueueItem[]>>;
  managerFilter: boolean;
  listRef: RefObject<HTMLUListElement | null>;
  search: string;
}) {
  if (queue.error) {
    return (
      <div role="alert" className="m-4 rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
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
      <div aria-busy="true" className="space-y-px">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[4.5rem] animate-pulse bg-surface" />
        ))}
      </div>
    );
  }
  if (queue.data.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <p className="text-sm font-medium">Нет диалогов по этому фильтру</p>
        <p className="mt-1 text-sm text-muted">
          {managerFilter
            ? "Снимите фильтр менеджера над списком или откройте вкладку «Все»."
            : "Попробуйте вкладку «Все» или снимите фильтр приоритета."}
        </p>
      </div>
    );
  }
  return (
    <ul ref={listRef} aria-label="Очередь" className={`divide-y divide-line ${queue.loading ? "opacity-60" : ""}`}>
      {queue.data.map((item) => (
        <li key={item.task_id}>
          <QueueRow item={item} search={search} />
        </li>
      ))}
    </ul>
  );
}

const ROW_ACCENT: Record<Priority, string> = {
  P0: "before:bg-p0",
  P1: "before:bg-p1",
  P2: "before:bg-p2",
  P3: "before:bg-transparent",
};

function QueueRow({ item, search }: { item: QueueItem; search: string }) {
  const name = item.player.display_name ?? item.player.player_id;
  return (
    <NavLink
      to={{ pathname: `/queue/${encodeURIComponent(item.conversation_id)}`, search }}
      className={({ isActive }) =>
        `relative grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 px-4 py-3 transition-colors before:absolute before:inset-y-0 before:left-0 before:w-[3px] sm:px-5 ${
          ROW_ACCENT[item.priority]
        } ${isActive ? "bg-surface shadow-[inset_0_0_0_1px_var(--color-line)]" : "hover:bg-surface/60"}`
      }
    >
      <div className="pt-0.5">
        <Pulse lane={item.sla_lane} waitHours={item.wait_hours} slaHours={item.sla_hours} />
      </div>

      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="mt-0.5 truncate text-xs text-muted">
          {item.category ? CATEGORY_LABEL[item.category] : "Разбор не выполнен"}
          <span aria-hidden="true"> · </span>
          {CHANNEL_LABEL[item.channel]}
          {item.player.segment && (
            <>
              <span aria-hidden="true"> · </span>
              {item.player.segment}
            </>
          )}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {item.route !== "manager" && <Tag tone="danger">{ROUTE_LABEL[item.route]}</Tag>}
          {item.quality_flags.map((f) => (
            <Tag key={f} tone="danger">
              {qualityFlagLabel(f)}
            </Tag>
          ))}
          {[...new Set(item.alerts.map((a) => alertText(a).tag))].map((tag) => (
            <Tag key={tag} tone="warn">
              {tag}
            </Tag>
          ))}
          {item.overdue && <Tag tone="danger">Просрочено</Tag>}
          {item.requires_review && <Tag tone="warn">Нужна проверка</Tag>}
          {(item.status === "in_progress" || item.status === "resolved") && (
            <Tag tone={item.status === "resolved" ? "ok" : "accent"}>{STATUS_LABEL[item.status]}</Tag>
          )}
          {item.simulated && <Tag>демо</Tag>}
        </div>
        {item.next_action && <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted">{item.next_action}</p>}
      </div>

      <div className="flex flex-col items-end gap-1.5">
        <PriorityBadge priority={item.priority} />
        <span
          className={`text-xs tabular-nums ${
            item.sla_lane === "breached" ? "font-medium text-danger" : item.awaiting_reply ? "text-ink" : "text-muted"
          }`}
        >
          {item.awaiting_reply ? formatWait(item.wait_hours) : "не ждёт"}
        </span>
      </div>
    </NavLink>
  );
}
