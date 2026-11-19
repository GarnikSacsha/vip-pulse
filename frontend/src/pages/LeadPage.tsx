import { Link } from "react-router";
import { api } from "../api/client";
import type { ManagerLoad, Overview, QueueItem, SlaLane } from "../api/types";
import { Tag } from "../components/Badges";
import { CompactItem, ErrorBox, KpiList, LoadingBlocks, Panel } from "../components/Oversight";
import { Pulse } from "../components/Pulse";
import { formatWait } from "../lib/format";
import { CATEGORY_LABEL, SLA_LANE_LABEL } from "../lib/labels";
import { useApi } from "../lib/useApi";

interface Group {
  id: string;
  title: string;
  description: string;
  pick: (item: QueueItem) => boolean;
}

// Each active item can appear in several groups: they answer different questions.
// Overdue work is not a group here: the SLA board above shows it as the «Горит» lane.
const GROUPS: Group[] = [
  {
    id: "escalated",
    title: "Эскалации",
    description: "Ведёт не менеджер: специалист по ответственной игре или безопасность.",
    pick: (i) => i.route !== "manager",
  },
  {
    id: "quality",
    title: "Ошибки менеджеров",
    description: "Например, бонус игроку с сигналом ответственной игры.",
    pick: (i) => i.quality_flags.length > 0,
  },
  {
    id: "review",
    title: "Нужна ручная проверка",
    description: "Автоматический разбор не выполнен или неуверен.",
    pick: (i) => i.requires_review,
  },
];

export function LeadPage() {
  const overview = useApi(() => api.overview(), "overview");
  const active = useApi(() => api.queue({ status: ["open", "in_progress"] }), "lead-active");

  const error = overview.error ?? active.error;
  if (error) {
    return (
      <ErrorBox
        message={`Не удалось загрузить данные: ${error}`}
        onRetry={() => {
          overview.reload();
          active.reload();
        }}
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Контроль команды</h1>
        <p className="mt-0.5 text-sm text-muted">
          Что горит по SLA, что ушло в эскалацию и где менеджер ошибся. Только активные диалоги.
        </p>
      </div>

      {!overview.data || !active.data ? (
        <LoadingBlocks />
      ) : (
        <LeadBody overview={overview.data} active={active.data} />
      )}
    </section>
  );
}

function LeadBody({ overview, active }: { overview: Overview; active: QueueItem[] }) {
  return (
    <>
      <LeadKpis overview={overview} />
      <SlaBoard items={active} />
      <Workload managers={overview.managers} />
      <div className="grid gap-4 lg:grid-cols-2">
        {GROUPS.map((g) => (
          <ExceptionGroup key={g.id} group={g} items={active.filter(g.pick)} />
        ))}
      </div>
    </>
  );
}

function LeadKpis({ overview }: { overview: Overview }) {
  const t = overview.totals;
  return (
    <KpiList
      items={[
        { label: "Активные", value: t.active, hint: `в работе ${t.in_progress}` },
        { label: "Просрочен ответ", value: t.overdue, tone: t.overdue ? "alert" : "plain" },
        { label: "Эскалации", value: t.escalated, hint: "RG и безопасность" },
        { label: "Ошибки менеджеров", value: t.quality_issues, tone: t.quality_issues ? "alert" : "plain" },
        { label: "Нужна проверка", value: t.needs_review },
      ]}
    />
  );
}

function Workload({ managers }: { managers: ManagerLoad[] }) {
  return (
    <Panel
      id="workload"
      title="Нагрузка по менеджерам"
      description="Закрепление игрока за менеджером взято из players.csv. Имя менеджера открывает его очередь."
    >
      {managers.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted">Нет данных: импортируйте игроков и диалоги.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label="Нагрузка по менеджерам" className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Менеджер</th>
                <th className="px-3 py-2 text-right font-medium">Активные</th>
                <th className="px-3 py-2 text-right font-medium">В работе</th>
                <th className="px-3 py-2 text-right font-medium">Критичные</th>
                <th className="px-3 py-2 text-right font-medium">Просрочено</th>
                <th className="px-3 py-2 text-right font-medium">Дольше всех ждёт</th>
                <th className="px-4 py-2 text-right font-medium">Всего</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line border-t border-line tabular-nums">
              {managers.map((m) => (
                <tr key={m.manager_id ?? "none"}>
                  <th scope="row" className="px-4 py-2.5 text-left font-medium">
                    {m.manager_id ? (
                      <Link
                        to={`/queue?manager=${encodeURIComponent(m.manager_id)}`}
                        className="underline decoration-line underline-offset-4 hover:decoration-ink"
                      >
                        {m.manager_id}
                      </Link>
                    ) : (
                      <span className="text-danger">Без менеджера</span>
                    )}
                  </th>
                  <td className="px-3 py-2.5 text-right">{m.active}</td>
                  <td className="px-3 py-2.5 text-right">{m.in_progress}</td>
                  <td className="px-3 py-2.5 text-right">{m.critical}</td>
                  <td className={`px-3 py-2.5 text-right ${m.overdue ? "font-medium text-danger" : ""}`}>{m.overdue}</td>
                  <td className="px-3 py-2.5 text-right">{formatWait(m.oldest_wait_hours)}</td>
                  <td className="px-4 py-2.5 text-right text-muted">{m.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function ExceptionGroup({ group, items }: { group: Group; items: QueueItem[] }) {
  return (
    <Panel
      id={`group-${group.id}`}
      title={
        <>
          {group.title} <span className="font-normal tabular-nums text-muted">· {items.length}</span>
        </>
      }
      description={group.description}
    >
      {items.length === 0 ? (
        <p className="px-4 py-4 text-sm text-muted">Нет</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.task_id}>
              <CompactItem item={item} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

const LANES: { lane: SlaLane; hint: string; tone: string }[] = [
  { lane: "breached", hint: "Ждут дольше SLA канала", tone: "text-danger" },
  { lane: "at_risk", hint: "Прошло больше 75 % SLA", tone: "text-p1" },
  { lane: "waiting", hint: "Ждут, время ещё есть", tone: "text-ink" },
  { lane: "ok", hint: "Ход за игроком", tone: "text-muted" },
];

/** Active work by SLA lane. Lanes come from the policy thresholds, never from the model. */
function SlaBoard({ items }: { items: QueueItem[] }) {
  return (
    <section aria-labelledby="sla-board" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="sla-board" className="text-sm font-semibold">
          SLA по активным диалогам
        </h2>
        <p className="text-xs text-muted">Пороги — в thresholds.yaml, не решение модели.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {LANES.map(({ lane, hint, tone }) => {
          const laneItems = items.filter((i) => i.sla_lane === lane);
          const headingId = `lane-${lane}`;
          return (
            <section
              key={lane}
              aria-labelledby={headingId}
              className="flex min-w-0 flex-col rounded-lg bg-chip/60 p-2 ring-1 ring-line"
            >
              <header className="px-1.5 pb-2 pt-1">
                <h3 id={headingId} className={`text-sm font-semibold ${tone}`}>
                  {SLA_LANE_LABEL[lane]} <span className="font-normal tabular-nums text-muted">· {laneItems.length}</span>
                </h3>
                <p className="text-xs text-muted">{hint}</p>
              </header>
              {laneItems.length === 0 ? (
                <p className="px-1.5 pb-2 text-sm text-muted">Пусто</p>
              ) : (
                <ul className="space-y-2">
                  {laneItems.map((item) => (
                    <li key={item.task_id}>
                      <LaneCard item={item} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </section>
  );
}

function timeLeft(item: QueueItem): string {
  if (!item.awaiting_reply || item.wait_hours === null) return "не ждёт ответа";
  const left = item.sla_hours - item.wait_hours;
  if (item.sla_lane === "breached") return `просрочено на ${formatWait(Math.max(-left, 0))}`;
  return left > 0 ? `осталось ${formatWait(left)}` : "SLA на исходе";
}

const BAR: Record<SlaLane, string> = {
  breached: "bg-danger",
  at_risk: "bg-p1",
  waiting: "bg-p2",
  ok: "bg-line",
};

function LaneCard({ item }: { item: QueueItem }) {
  const name = item.player.display_name ?? item.player.player_id;
  const share = item.wait_hours === null ? 0 : Math.min(1, item.wait_hours / item.sla_hours);
  return (
    <Link
      to={`/queue/${item.conversation_id}`}
      className="block rounded-md bg-surface p-3 ring-1 ring-line transition-shadow hover:shadow-sm"
    >
      <div className="flex items-start gap-2">
        <Pulse lane={item.sla_lane} waitHours={item.wait_hours} slaHours={item.sla_hours} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{name}</p>
          <p className="truncate text-xs text-muted">
            {item.player.manager_id ?? "без менеджера"} · {item.category ? CATEGORY_LABEL[item.category] : "без разбора"}
          </p>
        </div>
        <span className="text-xs font-semibold tabular-nums text-muted">{item.priority}</span>
      </div>
      {item.awaiting_reply && (
        <div aria-hidden="true" className="mt-2.5 h-1 overflow-hidden rounded-full bg-chip">
          <div className={`h-full rounded-full ${BAR[item.sla_lane]}`} style={{ width: `${share * 100}%` }} />
        </div>
      )}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className={`text-xs tabular-nums ${item.sla_lane === "breached" ? "font-medium text-danger" : "text-muted"}`}>
          {timeLeft(item)}
        </span>
        {item.simulated && <Tag>демо</Tag>}
      </div>
    </Link>
  );
}
