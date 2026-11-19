// Mirrors backend/app/api/schemas.py. Keep in sync when the API contract changes.

export type Priority = "P0" | "P1" | "P2" | "P3";
export type TaskStatus = "open" | "in_progress" | "resolved" | "no_action";
export type Route = "manager" | "rg_specialist" | "security";
export type Channel = "telegram" | "whatsapp" | "email" | "other";
export type SenderRole = "player" | "manager" | "system";
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
}

export interface Meta {
  as_of: string | null;
  provider: ProviderInfo;
  counts: {
    total: number;
    by_status: Record<TaskStatus, number>;
    by_priority: Record<Priority, number>;
  };
}

export interface Player {
  player_id: string;
  display_name: string | null;
  manager_id: string | null;
  segment: string | null;
}

export interface Reason {
  code: string;
  text: string;
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
  summary: string | null;
  next_action: string | null;
  wait_hours: number | null;
  awaiting_reply: boolean;
  requires_review: boolean;
  quality_flags: string[];
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
  sentiment: "positive" | "neutral" | "negative" | "mixed" | null;
  urgency: "low" | "medium" | "high" | null;
  summary: string | null;
  confidence: number | null;
  safety_flag: "none" | "responsible_gaming" | "fraud_security" | null;
  needs_escalation: boolean | null;
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
}

export interface StatusChange {
  status: TaskStatus;
  note?: string;
  actor?: string;
}
