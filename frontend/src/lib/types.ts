export type Role = "admin" | "librarian" | "member";
export type Level = "Critical" | "High" | "Medium" | "Low";

export interface User { id: number; email: string; name: string; role: Role; member_id: number | null; is_active: boolean }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; counts?: Record<string, number> }

export interface Book {
  id: number; isbn: string; title: string; author: string; category: string; publisher: string; year: number; price: number; description: string;
  copies_total?: number; copies_available?: number; copy_status?: Record<string, number>; waiting?: number;
}
export interface Copy { id: number; barcode: string; status: string; shelf: string; book_id: number; acquired_on: string }
export interface BookDetail extends Book { copies: Copy[]; queue: Reservation[]; times_borrowed: number; active_loans?: Loan[] }

export interface MemberStats { prior_loans: number; late_loans: number; late_rate: number; unpaid_fines: number; active_loans: number; overdue_loans: number }
export interface Member {
  id: number; code: string; name: string; email: string; phone: string; member_type: string; department: string; joined_on: string;
  status: string; restriction_reason: string | null; notify_pref: string; stats?: MemberStats;
}
export interface MemberDetail extends Member {
  stats: MemberStats;
  policy: { label: string; max_loans: number; loan_days: number; max_renewals: number; max_reservations: number; grace_days: number; max_fine: number };
  active_loans: Loan[]; history: Loan[]; reservations: Reservation[]; fines: Fine[];
  unread_notifications?: number; sim_date?: string;
}

export interface Factor { feature: string; text?: string; value?: unknown; contribution?: number; effect?: string; risk_after_step?: number }
export interface Prediction { probability: number; label: string; model: { id: number; algo: string; version: number }; factors: Factor[]; features: Record<string, unknown>; note?: string }

export interface Loan {
  id: number; copy_id: number; barcode: string; book_id: number; title: string; author: string; category: string; member_id: number; member_name: string;
  member_code: string; member_type: string; issued_on: string; due_on: string; returned_on: string | null; renewals: number; status: string;
  fine_id: number | null; fine_amount: number; fine_balance: number; days_overdue?: number; days_until_due?: number; days_late?: number;
  risk_score?: number | null; risk_label?: string | null; risk_detail?: Prediction & { features: Record<string, unknown> }; fine?: FineDetail | null;
}
export interface Reservation {
  id: number; book_id: number; title: string; author: string; member_id: number; member_name: string; member_code: string; member_type: string;
  created_on: string; status: string; copy_barcode: string | null; ready_on: string | null; expires_on: string | null; closed_on: string | null; position: number | null;
}
export interface FineLine { date: string; overdue_day: number; status: string; chargeable_index: number | null; rate: number; amount: number; cumulative: number; note: string }
export interface FineBreakdown {
  total: number; overdue_total: number; days_overdue: number; chargeable_days: number; grace_days_used: number; excluded_days: number; capped: boolean; cap: number;
  lines: FineLine[]; extra_charges: { label: string; amount: number }[]; kind: string; summary: string;
  policy?: { member_type: string; grace_days: number; fine_slabs: Slab[]; max_fine: number; exclude_sundays: boolean; lost_processing_fee: number };
}
export interface Fine {
  id: number; loan_id: number; member_id: number; member_name: string; member_code: string; title: string; kind: string; amount: number; amount_paid: number;
  amount_waived: number; balance: number; status: string; created_on: string; last_computed_on: string; due_on: string; returned_on: string | null; summary: string;
}
export interface FineDetail extends Fine {
  breakdown: FineBreakdown;
  payments: { id: number; amount: number; method: string; paid_on: string }[];
  waivers: { id: number; amount: number; reason: string; waived_on: string }[];
}
export interface Slab { from_day: number; to_day: number | null; rate: number }

export interface Firing { iteration: number; rule_code: string; rule_name: string; entity?: string; entity_id?: number; asserted: string; salience?: number; matched: { condition: string; field: string; actual: unknown; compared_to?: Record<string, unknown> }[] }
export interface ScoreItem { factor: string; label: string; raw: unknown; normalised: number; weight: number; contribution: number }
export interface FuzzyResult {
  level: Level; crisp: number; inputs: Record<string, number | null>; memberships: Record<string, Record<string, number>>;
  activations: { rule: string; if: string; then: Level; strength: number }[]; output_strengths: Record<Level, number>; floor_applied: string | null;
}
export interface Explanation {
  why: string; rules: Firing[]; priority: { score: number; level: Level; breakdown: ScoreItem[]; fuzzy: FuzzyResult };
  inputs: Record<string, unknown>; channel: { channel: string; reason: string; preference: string }; anti_spam: string[];
  prediction: Partial<Prediction> | null; queue_rank: number; queue_key: string; resolved_on?: string; days_to_resolve?: number;
}
export interface Notification {
  id: number; member_id: number; member_name: string; kind: string; loan_id: number | null; reservation_id: number | null; fine_id: number | null;
  score: number; level: Level; channel: string; subject: string; body: string; status: string; suppression_reason: string | null; outcome: string;
  created_on: string; sent_on: string | null; read: boolean; cycle_id: number | null; why: string; explanation?: Explanation;
}
export interface Approval {
  id: number; kind: string; status: string; source: string; member_id: number | null; member_name: string | null; loan_id: number | null; fine_id: number | null;
  payload: Record<string, unknown>; reason: string; explanation: { rules?: Firing[]; facts?: Record<string, unknown>; note?: string }; requested_by: string;
  created_on: string; decided_on: string | null; decision_note: string | null;
}
export interface AgentEvent {
  id: number; cycle_id: number | null; sim_date: string; created_at: string; phase: string; kind: string; severity: string; title: string; detail: string;
  data: Record<string, unknown>; member_id: number | null; loan_id: number | null;
}
export interface Cycle {
  id: number; sim_date: string; mode: string; started_at: string; duration_ms: number; summary: string; percepts: Record<string, number>;
  firing_count: number; action_count: number;
}
export interface CycleDetail extends Cycle {
  firings: Firing[]; decisions: { entity?: string; id?: number; label?: string; asserted?: string[]; facts?: Record<string, unknown>; type?: string; text?: string }[];
  actions: Record<string, unknown>[]; events: AgentEvent[]; notifications: Notification[];
}
export interface AgentStatus {
  sim_date: string; weekday: string; background_activity: boolean; auto_interval_sec: number; cycles: number; pending_approvals: number; queued_notifications: number;
  last_cycle: { id: number; sim_date: string; summary: string; duration_ms: number } | null;
}
export interface Rule {
  id: number; code: string; name: string; description: string; entity: string; conditions: Condition[]; conclusion: string; salience: number; enabled: boolean; updated_at: string | null;
}
export interface Condition { field: string; op: string; value?: unknown; value_field?: string | null }
export interface KbSchema {
  entities: string[]; fields: Record<string, Record<string, { type: string; label: string }>>; operators: Record<string, string>;
  conclusions: Record<string, { kind: string; label: string; notification?: string; penalising?: boolean; approval?: boolean }>;
}
export interface MLModel {
  id: number; algo: string; version: number; trained_at: string; params: Record<string, unknown>; is_selected: boolean;
  metrics: { accuracy: number; precision: number; recall: number; f1: number; roc_auc: number; confusion_matrix: { tn: number; fp: number; fn: number; tp: number };
    by_member_type: Record<string, { n: number; actual_late_rate: number; predicted_high_rate: number; recall: number }> };
  feature_importance: { feature: string; importance: number; direction: string; coefficient?: number }[];
  dataset_info: { synthetic_rows: number; history_rows: number; train_rows: number; test_rows: number; positive_rate: number; seed: number; label: string };
}
export interface Policy {
  id: number; member_type: string; label: string; max_loans: number; loan_days: number; max_renewals: number; max_reservations: number; grace_days: number;
  fine_slabs: Slab[]; max_fine: number; exclude_sundays: boolean; lost_after_days: number; lost_processing_fee: number; hold_days: number;
}
export interface AgentSettings {
  sim_date: string; priority_weights: Record<string, number>; cooldown_days: Record<string, number>; daily_limit: number; dispatch_capacity: number;
  fine_notice_threshold: number; restriction_fine_threshold: number; waiver_suggestion_max: number; high_risk_threshold: number;
  background_activity: boolean; auto_interval_sec: number;
}
export interface DemoLogEntry { step: number; title: string; sim_date: string; narrative: string[]; event_ids: number[]; events?: AgentEvent[]; refs: Record<string, unknown> }
export interface DemoState {
  steps: { title: string; summary: string }[]; next_step: number; status: AgentStatus;
  state: null | { step: number; loan_id: number; reservation_id: number; log: DemoLogEntry[] };
}
