import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Search, UserPlus } from "lucide-react";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { humanise, pct, rupees } from "../lib/format";
import type { Member, Page } from "../lib/types";
import { isEmail, isPhone, required } from "../lib/validation";
import { Async, EmptyState, Field, Modal, PageHeader, Pagination, StatusBadge, TableWrap } from "../components/ui";
import { useAction } from "../components/toast";

export default function Members() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  useEffect(() => setPage(1), [q, type, status]);
  const state = useApi<Page<Member>>(`/api/members${qs({ q, member_type: type, status, page, page_size: 25 })}`);
  return (
    <div>
      <PageHeader eyebrow="People" title="Members" description="Students, faculty and staff. No sensitive personal attributes are stored or used by the agent."
        actions={<button className="btn-primary" onClick={() => setAdding(true)}><UserPlus className="h-4 w-4" aria-hidden />Add member</button>} />
      <div className="card mb-4 grid gap-3 p-3 sm:grid-cols-[2fr,1fr,1fr]">
        <label className="relative"><span className="sr-only">Search members</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <input className="input pl-9" placeholder="Name, code, email or department…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} />
        </label>
        <label><span className="sr-only">Member type</span><select className="input" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option><option value="student">Students</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></label>
        <label><span className="sr-only">Status</span><select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option><option value="active">Active</option><option value="restricted">Restricted</option><option value="suspended">Suspended</option></select></label>
      </div>
      <div className="card p-4">
        <Async state={state} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No members match" />}>
          {(p) => (
            <>
              <TableWrap label="Members">
                <table className="table-base">
                  <thead><tr><th>Member</th><th>Type</th><th>Department</th><th>Loans</th><th>Late rate</th><th>Unpaid</th><th>Status</th></tr></thead>
                  <tbody>
                    {p.items.map((m) => (
                      <tr key={m.id}>
                        <td><Link to={`/members/${m.id}`} className="font-medium hover:text-accent hover:underline">{m.name}</Link><p className="font-mono text-xs text-muted">{m.code}</p></td>
                        <td>{humanise(m.member_type)}</td>
                        <td className="text-ink2">{m.department}</td>
                        <td className="num font-mono text-xs">{m.stats?.active_loans ?? 0} active{m.stats?.overdue_loans ? <span className="text-crit"> · {m.stats.overdue_loans} overdue</span> : null}</td>
                        <td className="num font-mono text-xs">{pct(m.stats?.late_rate)}</td>
                        <td className="num font-mono text-xs">{rupees(m.stats?.unpaid_fines)}</td>
                        <td><StatusBadge status={m.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
              <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
            </>
          )}
        </Async>
      </div>
      <AddMember open={adding} onClose={() => setAdding(false)} onSaved={state.reload} />
    </div>
  );
}

const EMPTY = { name: "", email: "", phone: "+91 ", member_type: "student", department: "", notify_pref: "email" };

function AddMember({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState(EMPTY);
  const [touched, setTouched] = useState(false);
  const act = useAction();
  const errors = {
    name: required(f.name, "Name", 2), email: isEmail(f.email) ? null : "Enter a valid email", phone: isPhone(f.phone) ? null : "8–16 digits, optional +",
    department: required(f.department, "Department", 2),
  };
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    const r = await act(() => post<{ code: string; initial_password: string | null }>("/api/members", { ...f, create_login: true }),
      (m) => `Member ${m.code} created${m.initial_password ? ` — initial password ${m.initial_password}` : ""}`);
    if (r) { setF(EMPTY); setTouched(false); onSaved(); onClose(); }
  }
  const err = (k: keyof typeof errors) => (touched ? errors[k] : null);
  return (
    <Modal open={open} onClose={onClose} title="Add a member">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
        <div className="sm:col-span-2"><Field label="Full name" htmlFor="m-name" error={err("name")}><input id="m-name" className="input" value={f.name} onChange={set("name")} /></Field></div>
        <Field label="Email" htmlFor="m-email" error={err("email")}><input id="m-email" className="input" type="email" value={f.email} onChange={set("email")} /></Field>
        <Field label="Phone" htmlFor="m-phone" error={err("phone")}><input id="m-phone" className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field>
        <Field label="Member type" htmlFor="m-type"><select id="m-type" className="input" value={f.member_type} onChange={set("member_type")}>
          <option value="student">Student</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></Field>
        <Field label="Notification preference" htmlFor="m-pref"><select id="m-pref" className="input" value={f.notify_pref} onChange={set("notify_pref")}>
          <option value="in_app">In-app</option><option value="email">Email</option><option value="sms">SMS</option></select></Field>
        <div className="sm:col-span-2"><Field label="Department" htmlFor="m-dept" error={err("department")}><input id="m-dept" className="input" value={f.department} onChange={set("department")} /></Field></div>
        <p className="text-xs text-muted sm:col-span-2">A login is created with the email and initial password Member@123. Only academic details are collected — never gender, age, religion or address.</p>
        <div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary">Create member</button></div>
      </form>
    </Modal>
  );
}
