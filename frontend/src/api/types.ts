// Mirrors backend/app/api/schemas.py. Keep in sync when the API contract changes.

export type Priority = "P0" | "P1" | "P2" | "P3";
export type TaskStatus = "open" | "in_progress" | "resolved" | "no_action";
export type Route = "manager" | "rg_specialist" | "security";
export type Channel = "telegram" | "whatsapp" | "email" | "other";
export type SenderRole = "player" | "manager" | "system";
/** Mirrors backend/app/policy/sla.py: decided by thresholds, never by the model. */
export type SlaLane = "breached" | "at_risk" | "waiting" | "specialist" | "ok";
/** Who owes the next message: the one source for every wait and overdue number (decision 0017). */
export type ReplyState = "players_turn" | "no_reply_needed" | "manager" | "specialist";
export type Sentiment = "positive" | "neutral" | "negative" | "mixed";
export type Category =
  | "withdrawal"
  | "deposit"
  | "verification"
  | "account"
  | "technical"
  | "general"
  | "responsible_gaming"
  | "other";

export interface ProviderInfo {
  name: string;
  model: string;
  simulated: boolean;
  label: string;
  budget_usd: number | null;
  spent_usd: number | null;
}

export interface Meta {
  as_of: string | null;
  provider: ProviderInfo;
  counts: {
    total: number;
    by_status: Record<TaskStatus, number>;
    by_priority: Record<Priority, number>;
  };
  managers: string[]; // from players.csv, for the demo role switcher
}

export interface Player {
  player_id: string;
  display_name: string | null;
  manager_id: string | null;
  segment: string | null;
  country?: string | null;
  registered_at?: string | null;
  profile?: PlayerProfile; // always sent by the API; optional for hand-made test data
}

/** Profile columns of players.csv. null = not in the source or unreadable. */
export interface PlayerProfile {
  account_status: string | null; // active | limit_set | self_excluded
  brand: string | null;
  language: string | null;
  geo: string | null;
  deposits_30d_usd: number | null;
  deposits_30d_count: number | null;
  deposits_prev_30d_usd: number | null;
  deposits_prev_30d_count: number | null;
  last_deposit_at: string | null;
  failed_deposits_7d: number | null;
  withdrawals_30d_usd: number | null;
  last_withdrawal_at: string | null;
  pending_withdrawal_usd: number | null;
  bonuses_30d_usd: number | null;
  bonuses_30d_count: number | null;
  last_login_at: string | null;
  birthday: string | null;
  favorite_game: string | null;
  deposits_change_pct?: number | null; // derived: 30-day deposits against the 30 days before
  deposit_drop?: boolean | null; // fell below player.deposit_drop_share (thresholds.yaml)
}

export interface Reason {
  code: string;
  text: string;
}

/** Mistakes in how a manager handled a contact, found by the analysis (closed list). */
export type ManagerErrorCode =
  | "canned_reply"
  | "rude_tone"
  | "wrong_info"
  | "incomplete_answer"
  | "wrong_name"
  | "broken_promise"
  | "retention_pressure";

export interface ManagerError {
  code: ManagerErrorCode;
  evidence_message_ids: string[]; // manager messages that show the mistake
}

/** A manager mistake counted by code (late_reply | waiting_past_sla), not by the model. */
export interface RuleError {
  code: string;
  evidence_message_ids: string[]; // the player message answered late (or still waiting) first
  hours: number;
}

export interface QueueItem {
  task_id: number;
  conversation_id: string;
  player: Player;
  channel: Channel;
  status: TaskStatus;
  priority: Priority;
  route: Route;
  category: Category | null;
  sentiment: Sentiment | null;
  summary: string | null;
  next_action: string | null;
  wait_hours: number | null;
  awaiting_reply: boolean; // the manager or a specialist owes a reply
  reply_state: ReplyState;
  /** Active work where the manager owes a reply past the channel's SLA (lane «Горит»). */
  overdue: boolean;
  /** The channel's response SLA under the current thresholds. */
  sla_hours: number;
  /** "breached" exactly when overdue. */
  sla_lane: SlaLane;
  requires_review: boolean;
  quality_flags: string[]; // counted by code
  manager_errors: ManagerError[]; // found by the analysis
  rule_errors: RuleError[]; // counted by code from message times
  /** Personal-contact alerts from the policy, e.g. "multi_account". */
  alerts: string[];
  reasons: Reason[];
  last_message_at: string;
  simulated: boolean;
}

export interface MessageOut {
  message_id: string;
  sender_role: SenderRole;
  sent_at: string;
  text: string;
  is_evidence: boolean;
  is_pending: boolean;
}

export interface AnalysisOut {
  status: "ok" | "failed";
  category: Category | null;
  sentiment: Sentiment | null;
  urgency: "low" | "medium" | "high" | null;
  summary: string | null;
  confidence: number | null;
  safety_flag: "none" | "responsible_gaming" | "fraud_security" | null;
  needs_escalation: boolean | null;
  manager_errors: ManagerError[];
  model: string | null;
  simulated: boolean;
  label: string;
  message: string | null;
}

export interface TaskOut {
  task_id: number;
  status: TaskStatus;
  priority: Priority;
  route: Route;
  next_action: string | null;
  reasons: Reason[];
  quality_flags: string[];
  /** Personal-contact alerts from the policy, e.g. "multi_account". */
  alerts: string[];
  requires_review: boolean;
  suppress_offers: boolean;
  updated_at: string;
  resolved_at: string | null;
}

export interface ConversationDetail {
  conversation_id: string;
  channel: Channel;
  player: Player;
  messages: MessageOut[];
  analysis: AnalysisOut | null;
  task: TaskOut | null;
  facts: {
    as_of: string;
    awaiting_reply: boolean;
    wait_hours: number | null;
    response_sla_hours: number;
    sla_breached: boolean;
    reply_state: ReplyState | null;
    raw_wait_hours: number | null; // since the player's last message, whoever owes
    median_response_minutes: number | null;
  };
}

export interface AuditEvent {
  at: string;
  actor: string;
  action: string;
  before: string | null;
  after: string | null;
  note: string | null;
}

export interface QueueFilters {
  status?: TaskStatus[];
  priority?: Priority[];
  route?: Route[];
  manager?: string[];
  player?: string[];
  overdue?: boolean;
}

// --- oversight (mirrors backend/app/api/schemas.py: Overview) ---

export interface OverviewTotals {
  total: number;
  active: number;
  in_progress: number;
  critical: number;
  overdue: number;
  awaiting_reply: number;
  escalated: number;
  quality_issues: number;
  needs_review: number;
  resolved: number;
  no_action: number;
}

export interface ManagerLoad {
  manager_id: string | null;
  total: number;
  active: number;
  in_progress: number;
  critical: number;
  overdue: number;
  oldest_wait_hours: number | null;
  errors: number; // code flags + analysis findings, all conversations
  error_conversations: number; // conversations with at least one mistake
}

export interface CategoryCount {
  category: Category | null;
  total: number;
  active: number;
}

export interface ChannelCount {
  channel: Channel;
  total: number;
  active: number;
  overdue: number;
}

export interface Overview {
  as_of: string | null;
  totals: OverviewTotals;
  managers: ManagerLoad[];
  categories: CategoryCount[];
  channels: ChannelCount[];
  routes: Record<Route, number>;
  coverage: {
    conversations: number;
    /** Conversations with a work item; the rest wait for a triage run. */
    in_queue: number;
    analysed: number;
    failed: number;
    /** Of `analysed`: produced by the offline stand-in, not a model. */
    simulated: number;
  };
}

export interface StatusChange {
  status: TaskStatus;
  note?: string;
  actor?: string;
}

// --- win-back (mirrors backend/app/api/schemas.py: WinbackOut) ---

export type WinbackTier = "urgent" | "attention" | "introduce";

export interface WinbackItem {
  player: Player;
  tier: WinbackTier;
  reasons: Reason[];
  next_action: string;
  last_login_days: number | null;
  /** null: the manager never wrote to this player. */
  last_contact_days: number | null;
  deposits_30d_usd: number | null;
  deposits_prev_30d_usd: number | null;
  favorite_game: string | null;
  latest_conversation_id: string | null;
  /** The player's most urgent active conversation: answer it before writing about win-back. */
  open_request?: OpenRequest | null;
}

export interface OpenRequest {
  conversation_id: string;
  category: Category | null;
  priority: Priority;
  wait_hours: number | null;
}

export interface BirthdayItem {
  player: Player;
  birthday: string; // YYYY-MM-DD
  days: number; // from the data date: 0 today, negative = already passed
  next_action: string;
}
