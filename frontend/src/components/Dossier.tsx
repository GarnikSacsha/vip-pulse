import { Fragment, type ReactNode, useId } from "react";
import { NavLink } from "react-router";
import { api } from "../api/client";
import type { Player, QueueItem, Sentiment } from "../api/types";
import { formatDay, formatShort } from "../lib/format";
import { CATEGORY_LABEL, SENTIMENT_LABEL, STATUS_LABEL } from "../lib/labels";
import { useApi } from "../lib/useApi";
import { PriorityBadge, Tag } from "./Badges";

// Sparkline rows, top to bottom. "mixed" sits with "neutral": both are neither better nor worse.
const LEVEL: Record<Sentiment, number> = { positive: 0, neutral: 1, mixed: 1, negative: 2 };
const W = 168;
const H = 40;
const PAD = 6;

const ACCOUNT_STATUS: Record<string, string> = {
  active: "Активен",
  limit_set: "Установлен лимит",
  self_excluded: "Самоисключение",
};

const RESTRICTION_NOTE: Record<string, string> = {
  self_excluded: "Самоисключение: никаких бонусов, акций и уговоров вернуться. Только сервисные вопросы.",
  limit_set: "Установлен лимит: не предлагать бонусы и повышение лимита.",
};

const dash = "—";
const usd = (n: number | null) => (n === null ? dash : `$${Math.round(n).toLocaleString("ru-RU").replace(/\s/g, " ")}`);
const day = (s: string | null) => (s ? formatDay(s) : dash);
function amount(sum: number | null, count: number | null): string {
  if (sum === null && count === null) return dash;
  return count === null ? usd(sum) : `${usd(sum)} · ${count} шт.`;
}

function Group({ title, rows }: { title: string; rows: [string, ReactNode][] }) {
  const id = useId();
  return (
    <section aria-labelledby={id}>
      <h3 id={id} className="text-xs font-medium uppercase tracking-wide text-muted">
        {title}
      </h3>
      <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([term, value]) => (
          <Fragment key={term}>
            <dt className="text-muted">{term}</dt>
            <dd className="tabular-nums">{value}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  );
}

/** Every column of players.csv the adapter kept, in groups. Missing values show as a dash. */
function PlayerCard({ player }: { player: Player }) {
  const p = player.profile;
  const status = p?.account_status ?? null;
  const pending = p?.pending_withdrawal_usd ?? null;
  return (
    <section className="space-y-4 rounded-lg bg-surface p-4 ring-1 ring-line">
      {status && RESTRICTION_NOTE[status] && (
        <p role="note" className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
          {RESTRICTION_NOTE[status]}
        </p>
      )}
      <Group
        title="Аккаунт"
        rows={[
          ["Игрок", <span className="font-mono text-xs">{player.player_id}</span>],
          [
            "Статус",
            status ? (
              <span className={RESTRICTION_NOTE[status] ? "font-medium text-danger" : ""}>
                {ACCOUNT_STATUS[status] ?? status}
              </span>
            ) : (
              dash
            ),
          ],
          ["Сегмент", player.segment ?? dash],
          ["Менеджер", player.manager_id ?? "не закреплён"],
          ["Бренд", p?.brand ?? dash],
          ["Язык", p?.language ?? dash],
          ["Гео", p?.geo ?? player.country ?? dash],
          ["VIP с", day(player.registered_at ?? null)],
        ]}
      />
      <Group
        title="Деньги"
        rows={[
          ["Депозиты 30 дн.", amount(p?.deposits_30d_usd ?? null, p?.deposits_30d_count ?? null)],
          ["Пред. 30 дн.", amount(p?.deposits_prev_30d_usd ?? null, p?.deposits_prev_30d_count ?? null)],
          ["Последний депозит", day(p?.last_deposit_at ?? null)],
          ["Неудачные депозиты 7 дн.", p?.failed_deposits_7d ?? dash],
          ["Выводы 30 дн.", usd(p?.withdrawals_30d_usd ?? null)],
          ["Последний вывод", day(p?.last_withdrawal_at ?? null)],
          [
            "Вывод в ожидании",
            pending ? (
              <span data-alert="true" className="font-medium text-danger">
                {usd(pending)}
              </span>
            ) : (
              usd(pending)
            ),
          ],
          ["Бонусы 30 дн.", amount(p?.bonuses_30d_usd ?? null, p?.bonuses_30d_count ?? null)],
        ]}
      />
      <Group title="Активность" rows={[["Последний вход", day(p?.last_login_at ?? null)]]} />
      <Group
        title="Личное"
        rows={[
          ["День рождения", day(p?.birthday ?? null)],
          ["Любимая игра", p?.favorite_game ?? dash],
        ]}
      />
    </section>
  );
}

/** Player context for the manager: profile, tone across conversations, every conversation. */
export function Dossier({ player, currentId, search = "" }: { player: Player; currentId: string; search?: string }) {
  const history = useApi(() => api.queue({ player: [player.player_id] }), `dossier:${player.player_id}`);
  const items = [...(history.data ?? [])].sort((a, b) => b.last_message_at.localeCompare(a.last_message_at));

  return (
    <div className="space-y-4">
      <PlayerCard player={player} />

      {history.error ? (
        <p role="alert" className="text-sm text-danger">
          Не удалось загрузить историю игрока: {history.error}
        </p>
      ) : !history.data ? (
        <div aria-busy="true" className="h-32 animate-pulse rounded-lg bg-surface ring-1 ring-line" />
      ) : (
        <>
          <ToneTrend items={items} />
          <section className="rounded-lg bg-surface ring-1 ring-line">
            <h3 className="px-4 pt-3 text-sm font-medium text-muted">
              Все переписки <span className="tabular-nums">· {items.length}</span>
            </h3>
            <ul aria-label="Переписки игрока" className="mt-2 divide-y divide-line">
              {items.map((item) => (
                <li key={item.task_id}>
                  <NavLink
                    to={{ pathname: `/queue/${encodeURIComponent(item.conversation_id)}`, search }}
                    className={({ isActive }) =>
                      `flex items-start gap-3 px-4 py-2.5 text-sm transition-colors ${
                        isActive ? "bg-evidence-soft/60" : "hover:bg-canvas"
                      }`
                    }
                  >
                    <PriorityBadge priority={item.priority} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">
                        {item.category ? CATEGORY_LABEL[item.category] : "Разбор не выполнен"}
                        {item.conversation_id === currentId && <span className="text-muted"> · открыта</span>}
                      </span>
                      {item.simulated && (
                        <span className="mt-0.5 block">
                          <Tag>демо</Tag>
                        </span>
                      )}
                      <span className="block text-xs text-muted">
                        {formatShort(item.last_message_at)} · {STATUS_LABEL[item.status]}
                        {item.sentiment && ` · ${SENTIMENT_LABEL[item.sentiment]}`}
                      </span>
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

/** Sentiment per conversation, oldest to newest. Shown only when there is a trend to see. */
function ToneTrend({ items }: { items: QueueItem[] }) {
  const points = items
    .filter((i): i is QueueItem & { sentiment: Sentiment } => i.sentiment !== null)
    .sort((a, b) => a.last_message_at.localeCompare(b.last_message_at));

  if (points.length < 2) {
    return (
      <p className="px-1 text-xs text-muted">
        Тон по перепискам появится, когда у игрока будет больше одного разобранного диалога.
      </p>
    );
  }

  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (points.length - 1);
  const y = (s: Sentiment) => PAD + (LEVEL[s] * (H - 2 * PAD)) / 2;
  const latest = points[points.length - 1];
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.sentiment)}`).join(" ");
  const label = `Тон игрока по перепискам: ${points.map((p) => SENTIMENT_LABEL[p.sentiment]).join(" → ")}`;
  const simulated = points.some((p) => p.simulated);

  return (
    <section className={`rounded-lg bg-surface p-4 ring-1 ring-line ${simulated ? "hatch" : ""}`}>
      <h3 className="text-sm font-medium text-muted">Тон по перепискам</h3>
      <div className="mt-2 flex items-center gap-3">
        <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="shrink-0 overflow-visible">
          {[0, 1, 2].map((level) => (
            <line
              key={level}
              x1={0}
              x2={W}
              y1={PAD + (level * (H - 2 * PAD)) / 2}
              y2={PAD + (level * (H - 2 * PAD)) / 2}
              className="stroke-line"
              strokeWidth={1}
              strokeDasharray={level === 1 ? "2 3" : undefined}
            />
          ))}
          <path d={path} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className="stroke-muted" />
          {points.map((p, i) => (
            <circle
              key={p.task_id}
              cx={x(i)}
              cy={y(p.sentiment)}
              r={i === points.length - 1 ? 4.5 : 3.5}
              strokeWidth={2}
              className={i === points.length - 1 ? "fill-ink stroke-surface" : "fill-muted stroke-surface"}
            >
              <title>{`${formatShort(p.last_message_at)}: ${SENTIMENT_LABEL[p.sentiment]}`}</title>
            </circle>
          ))}
        </svg>
        <div className="flex h-10 flex-col justify-between text-[11px] leading-none text-muted" aria-hidden="true">
          <span>позитив</span>
          <span>негатив</span>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">
        {latest && `Сейчас: ${SENTIMENT_LABEL[latest.sentiment]}. `}
        {simulated ? "Оценки тона — демо-эвристика, не модель." : "Определено разбором каждой переписки."}
      </p>
    </section>
  );
}
