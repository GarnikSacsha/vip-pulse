import { type KeyboardEvent, type ReactNode, useId, useState } from "react";
import { Link, useLocation, useOutletContext, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { AnalysisOut, AuditEvent, ConversationDetail, MessageOut, TaskOut, TaskStatus } from "../api/types";
import { PriorityBadge, Tag } from "../components/Badges";
import { Dossier } from "../components/Dossier";
import { formatShort, formatWait } from "../lib/format";
import {
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  MANAGER_ERROR_LABEL,
  PRIORITY_NAME,
  ROUTE_LABEL,
  SENDER_LABEL,
  SENTIMENT_LABEL,
  STATUS_LABEL,
  alertText,
  qualityFlagLabel,
} from "../lib/labels";
import { useApi } from "../lib/useApi";
import type { InboxContext, PaneTab } from "./QueuePage";

// Mirrors TRANSITIONS in backend/app/tasks/service.py; the server re-checks every change.
const ACTIONS: Record<TaskStatus, { to: TaskStatus; label: string; primary?: boolean }[]> = {
  open: [
    { to: "in_progress", label: "Взять в работу", primary: true },
    { to: "resolved", label: "Отметить решённой" },
  ],
  in_progress: [
    { to: "resolved", label: "Отметить решённой", primary: true },
    { to: "open", label: "Вернуть в открытые" },
  ],
  resolved: [{ to: "open", label: "Переоткрыть" }],
  no_action: [{ to: "open", label: "Открыть задачу" }],
};

// No authentication in the MVP: every change is attributed to a demo role.
const DEMO_ACTOR = "demo-manager";

/** The inbox's empty right side, before a conversation is picked. */
export function NoConversation() {
  return (
    <div className="flex h-full items-center justify-center px-6 py-16 text-center">
      <div>
        <p className="text-sm font-medium">Выберите диалог слева</p>
        <p className="mt-1 text-sm text-muted">
          Или нажмите <kbd className="rounded bg-chip px-1 font-mono text-xs">j</kbd>, чтобы открыть самый срочный.
        </p>
      </div>
    </div>
  );
}

/** The conversation and its analysis: the centre and right panes of the inbox. */
export function ConversationPane() {
  const { id = "" } = useParams();
  const inbox = useOutletContext<InboxContext | undefined>();
  const { search } = useLocation();
  const detail = useApi(() => api.conversation(id), `conversation:${id}`);

  if (detail.errorStatus === 404) {
    return (
      <div className="m-4 rounded-lg border border-dashed border-line bg-surface px-4 py-12 text-center sm:m-6">
        <p className="font-medium">Диалог не найден</p>
        <p className="mt-1 text-sm text-muted">Возможно, его нет в последнем импорте.</p>
        <Link to="/queue" className="mt-3 inline-block text-sm font-medium text-accent hover:underline">
          ← Вернуться в очередь
        </Link>
      </div>
    );
  }
  if (detail.error) {
    return (
      <div role="alert" className="m-4 rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger sm:m-6">
        <p>Не удалось загрузить диалог: {detail.error}</p>
        <button type="button" onClick={detail.reload} className="mt-2 rounded-md bg-surface px-2.5 py-1 font-medium ring-1 ring-danger-line">
          Повторить
        </button>
      </div>
    );
  }
  if (!detail.data) {
    return <div aria-busy="true" className="m-4 h-96 animate-pulse rounded-lg bg-surface ring-1 ring-line sm:m-6" />;
  }
  return (
    <Conversation
      // A fresh component per conversation: no highlight or tab carries over.
      key={detail.data.conversation_id}
      data={detail.data}
      backTo={`/queue${search}`}
      search={search}
      pane={inbox?.pane}
      setPane={inbox?.setPane}
      onChanged={() => {
        detail.reload();
        inbox?.reloadQueue();
      }}
    />
  );
}

/** Messages the panes refer to (cited by the analysis or waiting for a reply), numbered in order. */
function referenceNumbers(messages: MessageOut[]): Map<string, number> {
  const refs = new Map<string, number>();
  for (const m of messages) if (m.is_evidence || m.is_pending) refs.set(m.message_id, refs.size + 1);
  return refs;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface Highlight {
  hot: string | null;
  refs: Map<string, number>;
  byId: Map<string, MessageOut>;
  /** From a pill: highlight the message and bring it into view. */
  point: (id: string | null) => void;
  /** From a message: highlight the pills that cite it. */
  hover: (id: string | null) => void;
}

const TABS: [PaneTab, string][] = [
  ["analysis", "Разбор"],
  ["player", "Игрок"],
];

function Conversation({
  data,
  backTo,
  search,
  pane,
  setPane,
  onChanged,
}: {
  data: ConversationDetail;
  backTo: string;
  search: string;
  pane?: PaneTab;
  setPane?: (tab: PaneTab) => void;
  onChanged: () => void;
}) {
  const { task, analysis, player } = data;
  const name = player.display_name ?? player.player_id;
  // A link can name a message (?msg=…), e.g. a manager mistake from the team lead page.
  const [hot, setHot] = useState<string | null>(() => new URLSearchParams(search).get("msg"));
  // The inbox keeps the tab across conversations; standalone, the pane keeps its own.
  const [localTab, setLocalTab] = useState<PaneTab>("analysis");
  const tab = pane ?? localTab;
  const setTab = setPane ?? setLocalTab;
  const tabsId = useId();

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const at = TABS.findIndex(([value]) => value === tab);
    const next = TABS[(at + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    if (!next) return;
    setTab(next[0]);
    document.getElementById(`${tabsId}-${next[0]}`)?.focus();
  }

  const highlight: Highlight = {
    hot,
    refs: referenceNumbers(data.messages),
    byId: new Map(data.messages.map((m) => [m.message_id, m])),
    point(id) {
      setHot(id);
      if (id) {
        document
          .getElementById(`msg-${id}`)
          ?.scrollIntoView?.({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
      }
    },
    hover: setHot,
  };

  return (
    <article className="xl:grid xl:h-full xl:grid-cols-[minmax(0,1fr)_minmax(20rem,25rem)]">
      <section className="flex min-h-0 flex-col border-line xl:border-r">
        <header className="shrink-0 border-b border-line bg-surface px-4 py-4 sm:px-6">
          <Link to={backTo} className="mb-2 inline-block text-sm text-muted hover:text-ink lg:hidden">
            ← Очередь
          </Link>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              {task && <PriorityBadge priority={task.priority} />}
              <div className="min-w-0">
                <h2 className="truncate text-lg font-semibold tracking-tight">{name}</h2>
                <p className="mt-0.5 text-sm text-muted">
                  {[player.player_id, player.segment, player.manager_id && `менеджер ${player.manager_id}`, CHANNEL_LABEL[data.channel]]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
            {task && (
              <div className="text-right text-sm">
                <p className="font-medium">{`Статус: ${STATUS_LABEL[task.status]}`}</p>
                <p className="text-muted">{`Приоритет: ${PRIORITY_NAME[task.priority]}`}</p>
              </div>
            )}
          </div>
        </header>

        <div className="min-h-0 flex-1 px-4 py-5 sm:px-6 xl:overflow-y-auto">
          <ul aria-label="Переписка" className="mx-auto max-w-2xl space-y-3">
            {data.messages.map((m) => (
              <MessageBubble key={m.message_id} message={m} highlight={highlight} />
            ))}
          </ul>
          <p className="mx-auto mt-5 max-w-2xl text-xs text-muted">
            Номера в кружках — сообщения, на которые ссылается разбор. Наведите на номер справа, чтобы найти
            сообщение. Время — UTC.
          </p>
        </div>
      </section>

      <aside className="min-h-0 border-t border-line bg-canvas xl:overflow-y-auto xl:border-t-0">
        <div role="tablist" aria-label="Панель диалога" className="flex gap-4 border-b border-line px-4 pt-3 text-sm sm:px-5">
          {TABS.map(([value, label]) => (
            <button
              key={value}
              id={`${tabsId}-${value}`}
              role="tab"
              type="button"
              aria-selected={tab === value}
              aria-controls={`${tabsId}-${value}-panel`}
              tabIndex={tab === value ? 0 : -1}
              onKeyDown={onTabKey}
              onClick={() => setTab(value)}
              className={`-mb-px border-b-2 pb-2 ${
                tab === value ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Both panels exist for aria-controls; only the open one renders (the dossier loads lazily). */}
        {TABS.filter(([value]) => value !== tab).map(([value]) => (
          <div key={value} role="tabpanel" hidden id={`${tabsId}-${value}-panel`} aria-labelledby={`${tabsId}-${value}`} />
        ))}
        <div
          role="tabpanel"
          id={`${tabsId}-${tab}-panel`}
          aria-labelledby={`${tabsId}-${tab}`}
          className="space-y-4 p-4 sm:p-5"
        >
          {tab === "analysis" ? (
            <>
              {task?.suppress_offers && (
                <div role="note" className="rounded-lg border border-danger-line bg-danger-soft p-3.5 text-sm text-danger">
                  <p className="font-medium">Не предлагать бонусы и акции</p>
                  <p className="mt-0.5">Игрок сообщил о проблеме с контролем игры. Подключите специалиста.</p>
                </div>
              )}
              {task?.alerts.map((alert) => (
                <div
                  key={alert}
                  role="note"
                  aria-label="Уведомление менеджеру"
                  className="rounded-lg border border-warn-line bg-warn-soft p-3.5 text-sm text-warn"
                >
                  <p className="font-medium">{alertText(alert).title}</p>
                  <p className="mt-0.5">{alertText(alert).action}</p>
                </div>
              ))}
              {task && <NextStep task={task} onChanged={onChanged} />}
              {task && <Reasons task={task} />}
              <AnalysisCard analysis={analysis} messages={data.messages} highlight={highlight} />
              <Facts facts={data.facts} messages={data.messages} highlight={highlight} />
              {task && <History taskId={task.task_id} version={`${task.status}:${task.updated_at}`} />}
            </>
          ) : (
            <Dossier player={player} currentId={data.conversation_id} search={search} />
          )}
        </div>
      </aside>
    </article>
  );
}

function MessageBubble({ message, highlight }: { message: MessageOut; highlight: Highlight }) {
  const n = highlight.refs.get(message.message_id);
  const lit = highlight.hot === message.message_id;
  const hoverProps = n
    ? {
        onMouseEnter: () => highlight.hover(message.message_id),
        onMouseLeave: () => highlight.hover(null),
      }
    : {};

  if (message.sender_role === "system") {
    return (
      <li id={`msg-${message.message_id}`} data-highlighted={String(lit)} className="text-center text-xs text-muted" {...hoverProps}>
        {SENDER_LABEL.system} · {formatShort(message.sent_at)} — {message.text}
      </li>
    );
  }
  const fromPlayer = message.sender_role === "player";
  return (
    <li
      id={`msg-${message.message_id}`}
      data-highlighted={String(lit)}
      className={`flex scroll-my-6 ${fromPlayer ? "justify-start" : "justify-end"}`}
      {...hoverProps}
    >
      <div
        className={`relative max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm transition-shadow ${
          fromPlayer ? "bg-surface ring-1 ring-line" : "bg-chip"
        } ${message.is_evidence ? "ring-2 ring-evidence/50" : ""} ${lit ? "shadow-[0_0_0_4px_var(--color-evidence-soft)] ring-2 ring-evidence" : ""}`}
      >
        <p className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          {n !== undefined && <RefNumber n={n} active={lit} />}
          <span className="font-medium text-ink">{SENDER_LABEL[message.sender_role]}</span>
          <span className="tabular-nums">{formatShort(message.sent_at)}</span>
          {message.is_evidence && <Tag tone="accent">Основание вывода</Tag>}
          {message.is_pending && <Tag tone="warn">Ждёт ответа</Tag>}
        </p>
        <p className="whitespace-pre-line leading-relaxed">{message.text}</p>
      </div>
    </li>
  );
}

function RefNumber({ n, active }: { n: number; active: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 font-mono text-[11px] font-medium tabular-nums ${
        active ? "bg-evidence text-white" : "bg-evidence-soft text-evidence"
      }`}
    >
      {n}
    </span>
  );
}

/** Numbered link to a message. Hover or focus highlights it in the timeline. */
function EvidencePill({ id, highlight }: { id: string; highlight: Highlight }) {
  const n = highlight.refs.get(id);
  const message = highlight.byId.get(id);
  if (n === undefined || !message) return null;
  const active = highlight.hot === id;
  return (
    <button
      type="button"
      aria-label={`Сообщение ${n}: ${SENDER_LABEL[message.sender_role]}, ${formatShort(message.sent_at)}`}
      title={message.text}
      data-active={String(active)}
      onMouseEnter={() => highlight.point(id)}
      // A pill that keeps the keyboard focus keeps its message lit.
      onMouseLeave={(e) => {
        if (document.activeElement !== e.currentTarget) highlight.point(null);
      }}
      onFocus={() => highlight.point(id)}
      onBlur={() => highlight.point(null)}
      onClick={() => highlight.point(id)}
      className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 align-[1px] font-mono text-[11px] font-medium tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-evidence ${
        active ? "bg-evidence text-white" : "bg-evidence-soft text-evidence hover:bg-evidence hover:text-white"
      }`}
    >
      {n}
    </button>
  );
}

function Pills({ ids, highlight }: { ids: string[]; highlight: Highlight }) {
  if (ids.length === 0) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((id) => (
        <EvidencePill key={id} id={id} highlight={highlight} />
      ))}
    </span>
  );
}

function Card({
  title,
  children,
  aside,
  className = "",
  ...rest
}: {
  title: string;
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
} & Record<`data-${string}`, string>) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={`rounded-lg bg-surface p-4 ring-1 ring-line ${className}`} {...rest}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-medium text-muted">
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function NextStep({ task, onChanged }: { task: TaskOut; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function move(to: TaskStatus) {
    setBusy(true);
    setError(null);
    try {
      await api.updateTask(task.task_id, { status: to, actor: DEMO_ACTOR, ...(note.trim() ? { note: note.trim() } : {}) });
      setNote("");
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось изменить статус");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Следующий шаг">
      <p className="text-sm leading-relaxed">{task.next_action ?? "Действий не требуется."}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {task.route !== "manager" && <Tag tone="danger">{ROUTE_LABEL[task.route]}</Tag>}
        {task.quality_flags.map((f) => (
          <Tag key={f} tone="danger">
            {qualityFlagLabel(f)}
          </Tag>
        ))}
        {task.requires_review && <Tag tone="warn">Нужна проверка человеком</Tag>}
      </div>

      <label htmlFor="action-note" className="mt-4 block text-xs text-muted">
        Комментарий к действию
      </label>
      <textarea
        id="action-note"
        value={note}
        maxLength={500}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        placeholder="Необязательно: что сделано или почему"
        className="mt-1 w-full resize-y rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
      />
      <div role="group" aria-label="Действия" className="mt-2 flex flex-wrap gap-2">
        {ACTIONS[task.status].map((a) => (
          <button
            key={a.to}
            type="button"
            disabled={busy}
            onClick={() => void move(a.to)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
              a.primary ? "bg-ink text-white hover:bg-ink/85" : "bg-surface ring-1 ring-line hover:bg-canvas"
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </Card>
  );
}

function Reasons({ task }: { task: TaskOut }) {
  return (
    <Card title="Почему такой приоритет">
      <ul aria-label="Почему такой приоритет" className="space-y-1.5 text-sm">
        {task.reasons.map((r) => (
          <li key={r.code} className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
            <span>{r.text}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AnalysisCard({
  analysis,
  messages,
  highlight,
}: {
  analysis: AnalysisOut | null;
  messages: MessageOut[];
  highlight: Highlight;
}) {
  if (!analysis) {
    return (
      <Card title="Разбор" data-simulated="false">
        <p className="text-sm text-muted">Разбор ещё не запускался.</p>
      </Card>
    );
  }
  if (analysis.status === "failed") {
    return (
      <Card title="Разбор" data-simulated="false">
        <p className="text-sm text-warn">{analysis.message}</p>
      </Card>
    );
  }
  const errorIds = new Set(analysis.manager_errors.flatMap((e) => e.evidence_message_ids));
  const cited = messages.filter((m) => m.is_evidence && !errorIds.has(m.message_id)).map((m) => m.message_id);
  return (
    <Card
      title="Разбор"
      data-simulated={String(analysis.simulated)}
      className={analysis.simulated ? "hatch" : ""}
      aside={analysis.simulated ? <Tag tone="warn">демо</Tag> : undefined}
    >
      {analysis.summary && (
        <p className="text-sm leading-relaxed">
          {analysis.summary}
          <Pills ids={cited} highlight={highlight} />
        </p>
      )}
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {analysis.category && (
          <>
            <dt className="text-muted">Тема</dt>
            <dd>{CATEGORY_LABEL[analysis.category]}</dd>
          </>
        )}
        {analysis.sentiment && (
          <>
            <dt className="text-muted">Тон игрока</dt>
            <dd>{SENTIMENT_LABEL[analysis.sentiment]}</dd>
          </>
        )}
        {analysis.confidence !== null && (
          <>
            <dt className="text-muted">Уверенность</dt>
            <dd className="tabular-nums">{Math.round(analysis.confidence * 100)}%</dd>
          </>
        )}
      </dl>
      {analysis.manager_errors.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-medium">Ошибки менеджера</p>
          <ul aria-label="Ошибки менеджера" className="mt-1 space-y-1 text-sm">
            {analysis.manager_errors.map((e) => (
              <li key={e.code}>
                {MANAGER_ERROR_LABEL[e.code]}
                <Pills ids={e.evidence_message_ids} highlight={highlight} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">{`Источник: ${analysis.label}`}</p>
    </Card>
  );
}

function Facts({
  facts,
  messages,
  highlight,
}: {
  facts: ConversationDetail["facts"];
  messages: MessageOut[];
  highlight: Highlight;
}) {
  const pending = messages.filter((m) => m.is_pending).map((m) => m.message_id);
  return (
    <Card title="Факты">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">Ожидание</dt>
        <dd>
          {facts.reply_state === "no_reply_needed" ? (
            // The model's decision, shown as such; the SLA does not apply to it.
            <span>
              Ответ не требуется (AI)
              {facts.raw_wait_hours !== null && (
                <span className="block text-xs text-muted">
                  последнее сообщение игрока {formatWait(facts.raw_wait_hours)} назад
                </span>
              )}
            </span>
          ) : (
            <span className="tabular-nums">{facts.awaiting_reply ? formatWait(facts.wait_hours) : "игрок не ждёт"}</span>
          )}
          {facts.awaiting_reply && <Pills ids={pending} highlight={highlight} />}
        </dd>
        {/* The channel's response SLA. The money escalation threshold is a separate rule: see reasons. */}
        <dt className="text-muted">SLA канала</dt>
        <dd className={facts.sla_breached ? "text-danger" : ""}>
          {facts.awaiting_reply
            ? `${facts.response_sla_hours} ч, ${facts.sla_breached ? "нарушен" : "в пределах"}`
            : `${facts.response_sla_hours} ч, сейчас не применяется`}
        </dd>
        {facts.median_response_minutes !== null && (
          <>
            <dt className="text-muted">Обычно отвечают</dt>
            <dd className="tabular-nums">за {formatWait(facts.median_response_minutes / 60)}</dd>
          </>
        )}
      </dl>
      <p className="mt-3 text-xs text-muted">Посчитано кодом по времени сообщений, без модели.</p>
    </Card>
  );
}

function History({ taskId, version }: { taskId: number; version: string }) {
  const audit = useApi(() => api.audit(taskId), `audit:${taskId}:${version}`);
  const events: AuditEvent[] = audit.data ?? [];
  return (
    <Card title="История">
      {events.length === 0 ? (
        <p className="text-sm text-muted">{audit.loading ? "Загрузка…" : "Статус ещё не менялся."}</p>
      ) : (
        <ul aria-label="История" className="space-y-2 text-sm">
          {events.map((e, i) => (
            <li key={i}>
              <p>
                {e.before && e.after
                  ? `${STATUS_LABEL[e.before as TaskStatus] ?? e.before} → ${STATUS_LABEL[e.after as TaskStatus] ?? e.after}`
                  : e.action}
              </p>
              <p className="text-xs text-muted">
                {e.actor === "system" ? "система" : e.actor} · {formatShort(e.at)}
              </p>
              {e.note && <p className="mt-0.5 text-muted">«{e.note}»</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
