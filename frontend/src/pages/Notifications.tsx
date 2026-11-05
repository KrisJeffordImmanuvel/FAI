import { useEffect, useState } from "react";
import { CheckCheck, ListOrdered, Mail, MessageSquare, Smartphone } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, put, qs } from "../lib/api";
import { CHANNEL_LABELS, KIND_LABELS, fmtDate, humanise } from "../lib/format";
import type { Level, Notification, Page, ScoreItem } from "../lib/types";
import { Async, Card, EmptyState, LevelBadge, Modal, Notice, PageHeader, Pagination, StatusBadge, TableWrap, Tabs, cx } from "../components/ui";
import { NotificationExplanation } from "../components/explain";
import { useAction } from "../components/toast";

const CHANNEL_ICON: Record<string, typeof Mail> = { email: Mail, sms: Smartphone, in_app: MessageSquare };

export default function Notifications() {
  const user = useUser();
  return user.role === "member" ? <Inbox /> : <StaffNotifications />;
}

function NotificationDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const state = useApi<Notification>(`/api/notifications/${id}`);
  return (
    <Modal open onClose={onClose} title="Why was this notification sent?" wide>
      <Async state={state}>
        {(n) => (
          <div className="space-y-4">
            <div className="rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center gap-2"><LevelBadge level={n.level} score={n.score} /><StatusBadge status={n.status} />
                <span className="text-xs text-muted">{KIND_LABELS[n.kind]} · {CHANNEL_LABELS[n.channel]} · {fmtDate(n.created_on)} · to {n.member_name}</span></div>
              <p className="mt-2 font-medium">{n.subject}</p>
              <p className="mt-1 text-sm text-ink2">{n.body}</p>
              {n.suppression_reason && <p className="mt-2 text-sm text-crit">{n.suppression_reason}</p>}
            </div>
            {n.explanation && <NotificationExplanation exp={n.explanation} />}
          </div>
        )}
      </Async>
    </Modal>
  );
}

function Inbox() {
  const { tick } = useAgent();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const state = useApi<Page<Notification>>(`/api/notifications${qs({ page, page_size: 20 })}`, [tick]);
  const act = useAction();
  async function markAll() {
    const r = await act(() => post<{ marked: number }>("/api/notifications/read-all"), (x) => `${x.marked} marked as read`);
    if (r) state.reload();
  }
  async function openNote(n: Notification) {
    setOpen(n.id);
    if (!n.read) { await post(`/api/notifications/${n.id}/read`).catch(() => null); state.reload(); }
  }
  return (
    <div>
      <PageHeader eyebrow="Inbox" title="Notifications" description="Messages from the library agent. Each one explains why it was sent and how urgent it is."
        actions={<button className="btn-secondary" onClick={markAll}><CheckCheck className="h-4 w-4" aria-hidden />Mark all read</button>} />
      <PreferenceCard />
      <Async state={state} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="Your inbox is empty">Reminders, recalls and reservation alerts will appear here.</EmptyState>}>
        {(p) => (
          <>
            <ul className="space-y-2">
              {p.items.map((n) => {
                const Icon = CHANNEL_ICON[n.channel] ?? MessageSquare;
                return (
                  <li key={n.id}>
                    <button onClick={() => openNote(n)} className={cx("card flex w-full gap-3 p-4 text-left transition hover:border-accent/50", !n.read && "border-l-4 border-l-accent")}>
                      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-muted" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2"><LevelBadge level={n.level} /><span className="text-xs text-muted">{KIND_LABELS[n.kind]} · {CHANNEL_LABELS[n.channel]} · {fmtDate(n.sent_on)}</span>
                          {!n.read && <span className="rounded bg-accent px-1.5 text-[10px] font-medium uppercase text-accent-ink">new</span>}</span>
                        <span className={cx("mt-1 block", !n.read && "font-medium")}>{n.subject}</span>
                        <span className="mt-0.5 block text-sm text-ink2">{n.body}</span>
                        <span className="mt-1 block text-xs text-muted">Why: {n.why}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
          </>
        )}
      </Async>
      {open !== null && <NotificationDetail id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function PreferenceCard() {
  const summary = useApi<{ notify_pref: string }>("/api/me/summary");
  const act = useAction();
  const [pref, setPref] = useState<string | null>(null);
  useEffect(() => { if (summary.data) setPref(summary.data.notify_pref); }, [summary.data]);
  if (!pref) return null;
  async function save(v: string) {
    setPref(v);
    await act(() => fetchPut(v), "Notification preference saved");
  }
  return (
    <div className="card mb-4 flex flex-col gap-2 p-3 text-sm sm:flex-row sm:items-center">
      <span className="font-medium">Preferred channel for important notices</span>
      <div className="flex flex-wrap gap-1 sm:ml-auto" role="radiogroup" aria-label="Preferred channel">
        {(["in_app", "email", "sms"] as const).map((c) => (
          <button key={c} role="radio" aria-checked={pref === c} onClick={() => save(c)} className={pref === c ? "btn-primary px-3 py-1.5" : "btn-secondary px-3 py-1.5"}>{CHANNEL_LABELS[c]}</button>
        ))}
      </div>
      <span className="text-xs text-muted sm:basis-full">Routine (Low/Medium) notices stay in-app. High uses your preference; Critical escalates to SMS/email so it isn't missed.</span>
    </div>
  );
}

function fetchPut(v: string) {
  return put("/api/me/preferences", { notify_pref: v });
}

type StaffTab = "queue" | "delivered" | "suppressed" | "queued";

function StaffNotifications() {
  const { tick } = useAgent();
  const [tab, setTab] = useState<StaffTab>("queue");
  const [level, setLevel] = useState("");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => setPage(1), [tab, level, kind]);
  const list = useApi<Page<Notification>>(tab === "queue" ? null : `/api/notifications${qs({ status: tab, level, kind, page, page_size: 30 })}`, [tick]);
  return (
    <div>
      <PageHeader eyebrow="Notification center" title="Notifications"
        description="The agent scores every candidate with a weighted utility function, classifies it with fuzzy logic, then serves a heap priority queue through cooldowns, duplicate suppression and daily limits." />
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center">
        <Tabs label="Notification view" value={tab} onChange={setTab} options={[
          { value: "queue", label: <span className="flex items-center gap-1.5"><ListOrdered className="h-3.5 w-3.5" aria-hidden />Priority queue</span> },
          { value: "delivered", label: "Delivered" }, { value: "suppressed", label: "Suppressed" }, { value: "queued", label: "Waiting" }]} />
        {tab !== "queue" && (
          <div className="flex gap-2 lg:ml-auto">
            <label><span className="sr-only">Level</span><select className="input" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">All levels</option>{["Critical", "High", "Medium", "Low"].map((l) => <option key={l}>{l}</option>)}</select></label>
            <label><span className="sr-only">Type</span><select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All types</option>{Object.entries(KIND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          </div>
        )}
      </div>
      {tab === "queue" ? <QueueView /> : (
        <div className="card p-4">
          {list.data?.counts && <p className="mb-3 text-xs text-muted">All time: {Object.entries(list.data.counts).map(([k, v]) => `${v} ${k}`).join(" · ")}</p>}
          <Async state={list} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No notifications in this view" />}>
            {(p) => (
              <>
                <TableWrap label="Notifications">
                  <table className="table-base">
                    <thead><tr><th>Priority</th><th>Member</th><th>Notice</th><th>Channel</th><th>Date</th><th>{tab === "suppressed" ? "Suppressed because" : "Outcome"}</th><th className="text-right"><span className="sr-only">Explain</span></th></tr></thead>
                    <tbody>{p.items.map((n) => (
                      <tr key={n.id}>
                        <td><LevelBadge level={n.level} score={n.score} /></td>
                        <td className="whitespace-nowrap">{n.member_name}</td>
                        <td><p className="text-xs text-muted">{KIND_LABELS[n.kind]}</p><p className="max-w-md">{n.subject}</p></td>
                        <td className="whitespace-nowrap text-xs">{CHANNEL_LABELS[n.channel]}</td>
                        <td className="whitespace-nowrap text-xs">{fmtDate(n.created_on)}</td>
                        <td className="max-w-xs text-xs">{tab === "suppressed" ? n.suppression_reason : <StatusBadge status={n.outcome} />}</td>
                        <td className="text-right"><button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => setOpen(n.id)}>Why?</button></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </TableWrap>
                <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
              </>
            )}
          </Async>
        </div>
      )}
      {open !== null && <NotificationDetail id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

interface QueueItem { rank: number; kind: string; entity: string; entity_id: number; member: string; label: string; score: number; level: Level; crisp: number; breakdown: ScoreItem[] }

function QueueView() {
  const { tick } = useAgent();
  const state = useApi<{ sim_date: string; items: QueueItem[]; carried_over: Notification[] }>("/api/notifications/queue", [tick]);
  const [expanded, setExpanded] = useState<number | null>(null);
  return (
    <Card title="Heap priority queue — dry run for today" subtitle="What the agent would push into its min-heap on key (−level, −score, arrival) if it ran now. Nothing is sent from this view.">
      <Async state={state} isEmpty={(d) => d.items.length === 0} empty={<EmptyState title="The queue is empty">No rule currently asks for a notification.</EmptyState>}>
        {(d) => (
          <>
            {d.carried_over.length > 0 && <Notice tone="warn">{d.carried_over.length} notification(s) are waiting from an earlier cycle (dispatch capacity reached) and will be served first in their level.</Notice>}
            <ol className="mt-2 space-y-1.5">
              {d.items.map((it) => (
                <li key={`${it.kind}-${it.entity}-${it.entity_id}`} className="rounded-lg border border-line">
                  <button className="flex w-full flex-wrap items-center gap-3 px-3 py-2 text-left text-sm hover:bg-sunken/60" onClick={() => setExpanded(expanded === it.rank ? null : it.rank)} aria-expanded={expanded === it.rank}>
                    <span className="num w-8 font-mono text-xs text-muted">#{it.rank}</span>
                    <LevelBadge level={it.level} score={it.score} />
                    <span className="min-w-0 flex-1"><span className="font-medium">{KIND_LABELS[it.kind] ?? humanise(it.kind)}</span> <span className="text-ink2">· {it.member} · {it.label}</span></span>
                    <span className="font-mono text-[11px] text-muted">fuzzy crisp {it.crisp}</span>
                  </button>
                  {expanded === it.rank && (
                    <div className="border-t border-line px-3 py-2">
                      <ul className="grid gap-1 text-xs sm:grid-cols-3">
                        {it.breakdown.map((b) => <li key={b.factor} className="flex justify-between gap-2"><span className="text-ink2">{b.label}</span><span className="num font-mono">{b.contribution.toFixed(1)}</span></li>)}
                      </ul>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </Async>
    </Card>
  );
}
