import type { SlaLane } from "../api/types";
import { formatWait } from "../lib/format";

// Ring geometry: r = 7 in a 18×18 box, 2.5 px stroke.
const R = 7;
const CIRCUMFERENCE = 2 * Math.PI * R;

const STROKE: Record<SlaLane, string> = {
  breached: "stroke-danger",
  at_risk: "stroke-p1",
  waiting: "stroke-p2",
  specialist: "stroke-p2",
  ok: "stroke-line",
};

function label(lane: SlaLane, waitHours: number | null, slaHours: number): string {
  if (waitHours === null || lane === "ok") return "Игрок не ждёт ответа";
  const base = `Ждёт ${formatWait(waitHours)} из ${formatWait(slaHours)} по SLA`;
  if (lane === "breached") return `${base}, SLA нарушен`;
  if (lane === "at_risk") return `${base}, скоро нарушение`;
  if (lane === "specialist") return `У специалиста, игрок ждёт ${formatWait(waitHours)}`;
  return base;
}

/**
 * The signature detail: the ring fills as the wait approaches the channel's SLA.
 * Only "at risk" pulses (and only without prefers-reduced-motion); a breach is solid and still.
 * The lane comes from the API (policy thresholds), never from the model.
 */
export function Pulse({
  lane,
  waitHours,
  slaHours,
}: {
  lane: SlaLane;
  waitHours: number | null;
  slaHours: number;
}) {
  const waiting = lane !== "ok" && waitHours !== null;
  const fill = !waiting ? 0 : lane === "breached" ? 1 : Math.min(1, Math.round((waitHours / slaHours) * 100) / 100);
  const animated = lane === "at_risk";
  return (
    <span
      role="img"
      aria-label={label(lane, waitHours, slaHours)}
      title={label(lane, waitHours, slaHours)}
      data-fill={String(fill)}
      data-animated={String(animated)}
      className="relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center"
    >
      {animated && (
        <span
          aria-hidden="true"
          className="absolute inset-0 rounded-full bg-p1/30 motion-safe:animate-[vp-pulse_1.8s_ease-out_infinite]"
        />
      )}
      <svg aria-hidden="true" viewBox="0 0 18 18" className="relative h-[18px] w-[18px] -rotate-90">
        <circle cx="9" cy="9" r={R} fill="none" strokeWidth="2.5" className="stroke-chip" />
        {fill > 0 && (
          <circle
            cx="9"
            cy="9"
            r={R}
            fill="none"
            strokeWidth="2.5"
            strokeLinecap={fill < 1 ? "round" : "butt"}
            strokeDasharray={`${fill * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
            className={STROKE[lane]}
          />
        )}
        {lane === "breached" && <circle cx="9" cy="9" r="3" className="fill-danger" />}
      </svg>
    </span>
  );
}
