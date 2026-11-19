import { type ReactNode, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { AnalysisOut, AuditEvent, ConversationDetail, MessageOut, TaskOut, TaskStatus } from "../api/types";
import { PriorityBadge, Tag } from "../components/Badges";
import { formatShort, formatWait } from "../lib/format";
import {
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  PRIORITY_LABEL,
  ROUTE_LABEL,
  SENDER_LABEL,
  STATUS_LABEL,
  qualityFlagLabel,
} from "../lib/labels";
import { useApi } from "../lib/useApi";

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

const SENTIMENT_LABEL: Record<NonNullable<AnalysisOut["sentiment"]>, string> = {
  positive: "позитивный",
  neutral: "нейтральный",
  negative: "негативный",
  mixed: "смешанный",
};

export function ConversationPage() {
  const { id = "" } = useParams();
  const detail = useApi(() => api.conversation(id), `conversation:${id}`);

  if (detail.errorStatus === 404) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-surface px-4 py-12 text-center">
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
      <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
        <p>Не удалось загрузить диалог: {detail.error}</p>
        <button type="button" onClick={detail.reload} className="mt-2 rounded-md bg-surface px-2.5 py-1 font-medium ring-1 ring-danger-line">
          Повторить
        </button>
      </div>
    );
  }
  if (!detail.data) {
    return <div aria-busy="true" className="h-96 animate-pulse rounded-lg bg-surface ring-1 ring-line" />;
  }
  return <Conversation data={detail.data} onChanged={detail.reload} />;
}

function Conversation({ data, onChanged }: { data: ConversationDetail; onChanged: () => void }) {
  const { task, analysis, player } = data;
  const name = player.display_name ?? player.player_id;

  return (
    <article>
      <Link to="/queue" className="text-sm text-muted hover:text-ink">
        ← Очередь
      </Link>

      <header className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {task && <PriorityBadge priority={task.priority} />}
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{name}</h1>
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
            <p className="text-muted">{PRIORITY_LABEL[task.priority]} приоритет</p>
          </div>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="rounded-lg bg-surface p-4 ring-1 ring-line sm:p-5">
          <h2 className="mb-4 text-sm font-medium text-muted">Переписка</h2>
          <ul aria-label="Переписка" className="space-y-3">
            {data.messages.map((m) => (
              <MessageBubble key={m.message_id} message={m} />
            ))}
          </ul>
          <p className="mt-4 text-xs text-muted">
            <span className="mr-1 inline-block h-2 w-2 rounded-full bg-evidence align-middle" />
            Отмечены сообщения, на которые опирается разбор. Время — UTC.
          </p>
        </section>

        <aside className="space-y-4">
          {task?.suppress_offers && (
            <div role="note" className="rounded-lg border border-danger-line bg-danger-soft p-3.5 text-sm text-danger">
              <p className="font-medium">Не предлагать бонусы и акции</p>
              <p className="mt-0.5">Игрок сообщил о проблеме с контролем игры. Подключите специалиста.</p>
            </div>
          )}

          {task && <NextStep task={task} onChanged={onChanged} />}
          {task && <Reasons task={task} />}
          <AnalysisCard analysis={analysis} />
          <Facts facts={data.facts} />
          {task && <History taskId={task.task_id} version={`${task.status}:${task.updated_at}`} />}
        </aside>
      </div>
    </article>
  );
}

function MessageBubble({ message }: { message: MessageOut }) {
  if (message.sender_role === "system") {
    return (
      <li className="text-center text-xs text-muted">
        {SENDER_LABEL.system} · {formatShort(message.sent_at)} — {message.text}
      </li>
    );
  }
  const fromPlayer = message.sender_role === "player";
  return (
    <li className={`flex ${fromPlayer ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm ${
          fromPlayer ? "bg-canvas" : "bg-chip"
        } ${message.is_evidence ? "ring-2 ring-evidence/60" : ""}`}
      >
        <p className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          <span className="font-medium text-ink">{SENDER_LABEL[message.sender_role]}</span>
          <span>{formatShort(message.sent_at)}</span>
          {message.is_evidence && <Tag tone="accent">Основание вывода</Tag>}
          {message.is_pending && <Tag tone="warn">Ждёт ответа</Tag>}
        </p>
        <p className="whitespace-pre-line leading-relaxed">{message.text}</p>
      </div>
    </li>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <h2 className="mb-2 text-sm font-medium text-muted">{title}</h2>
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

function AnalysisCard({ analysis }: { analysis: AnalysisOut | null }) {
  if (!analysis) {
    return (
      <Card title="Разбор">
        <p className="text-sm text-muted">Разбор ещё не запускался.</p>
      </Card>
    );
  }
  if (analysis.status === "failed") {
    return (
      <Card title="Разбор">
        <p className="text-sm text-warn">{analysis.message}</p>
      </Card>
    );
  }
  return (
    <Card title="Разбор">
      {analysis.summary && <p className="text-sm leading-relaxed">{analysis.summary}</p>}
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
      <p className="mt-3 text-xs text-muted">{`Источник: ${analysis.label}`}</p>
    </Card>
  );
}

function Facts({ facts }: { facts: ConversationDetail["facts"] }) {
  return (
    <Card title="Факты">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">Ожидание</dt>
        <dd className="tabular-nums">{facts.awaiting_reply ? formatWait(facts.wait_hours) : "игрок не ждёт"}</dd>
        <dt className="text-muted">SLA</dt>
        <dd>
          {facts.sla_breached
            ? `SLA ${facts.response_sla_hours} ч нарушен`
            : `в пределах ${facts.response_sla_hours} ч`}
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
