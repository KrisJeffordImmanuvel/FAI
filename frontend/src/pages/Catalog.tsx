import { useEffect, useState, type FormEvent } from "react";
import { BookmarkPlus, Plus, Search, Wrench } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { patch, post, qs } from "../lib/api";
import { fmtDate, rupees } from "../lib/format";
import type { Book, BookDetail, Member, Page } from "../lib/types";
import { can } from "../lib/roles";
import { isIsbn, required } from "../lib/validation";
import { Async, EmptyState, Field, Modal, Notice, PageHeader, Pagination, RiskPill, StatusBadge, TableWrap, cx } from "../components/ui";
import { useAction } from "../components/toast";

const CATEGORY_TINT: Record<string, string> = {
  "Artificial Intelligence": "var(--series-1)", "Computer Science": "var(--series-3)", Mathematics: "var(--series-2)", Physics: "var(--series-4)",
  Electronics: "var(--series-5)",
};

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function Catalog() {
  const user = useUser();
  const { tick } = useAgent();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [availability, setAvailability] = useState("");
  const [sort, setSort] = useState("title");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const dq = useDebounced(q);
  useEffect(() => setPage(1), [dq, category, availability, sort]);
  const cats = useApi<{ category: string; count: number }[]>("/api/books/categories");
  const books = useApi<Page<Book>>(`/api/books${qs({ q: dq, category, availability, sort, page, page_size: 24 })}`, [tick]);

  return (
    <div>
      <PageHeader eyebrow="Collection" title="Catalog" description="Titles and their physical copies. Search by title, author, ISBN or publisher."
        actions={can.manageCirculation(user.role) && <button className="btn-primary" onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden />Add title</button>} />
      <div className="card mb-5 grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-[2fr,1fr,1fr,1fr]">
        <label className="relative">
          <span className="sr-only">Search the catalog</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <input className="input pl-9" placeholder="Search title, author, ISBN…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} />
        </label>
        <label><span className="sr-only">Category</span>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {(cats.data ?? []).map((c) => <option key={c.category} value={c.category}>{c.category} ({c.count})</option>)}
          </select>
        </label>
        <label><span className="sr-only">Availability</span>
          <select className="input" value={availability} onChange={(e) => setAvailability(e.target.value)}>
            <option value="">Any availability</option><option value="available">On the shelf</option><option value="unavailable">All copies out</option>
          </select>
        </label>
        <label><span className="sr-only">Sort</span>
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="title">Sort: title</option><option value="author">Sort: author</option><option value="year">Sort: newest</option><option value="popular">Sort: most borrowed</option>
          </select>
        </label>
      </div>
      <Async state={books} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No books match">Try a different search or clear the filters.</EmptyState>}>
        {(p) => (
          <>
            <p className="mb-3 text-sm text-muted" aria-live="polite">{p.total} title{p.total === 1 ? "" : "s"}</p>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {p.items.map((b) => (
                <li key={b.id}>
                  <button onClick={() => setSelected(b.id)} className="card catalog-card group flex h-full w-full flex-col gap-2 overflow-hidden px-4 pb-7 pt-0 text-left transition hover:-translate-y-0.5 hover:shadow-lift">
                    <span className="-mx-4 mb-1 h-1.5" style={{ background: CATEGORY_TINT[b.category] ?? "rgb(var(--line))" }} aria-hidden />
                    <span className="eyebrow">{b.category}</span>
                    <span className="font-display text-lg font-semibold leading-snug group-hover:text-accent">{b.title}</span>
                    <span className="line-clamp-2 text-sm text-ink2">{b.author}</span>
                    <span className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-xs">
                      <StatusBadge status={b.copies_available ? "available" : "on_loan"} label={b.copies_available ? `${b.copies_available}/${b.copies_total} on shelf` : `all ${b.copies_total} out`} />
                      {!!b.waiting && <StatusBadge status="waiting" label={`${b.waiting} waiting`} />}
                      <span className="ml-auto font-mono text-muted">{b.year}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
          </>
        )}
      </Async>
      {selected !== null && <BookModal id={selected} onClose={() => setSelected(null)} onChanged={books.reload} />}
      <AddBookModal open={adding} onClose={() => setAdding(false)} categories={(cats.data ?? []).map((c) => c.category)} onSaved={books.reload} />
    </div>
  );
}

function BookModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const user = useUser();
  const { bump } = useAgent();
  const state = useApi<BookDetail>(`/api/books/${id}`);
  const act = useAction();
  const staff = can.manageCirculation(user.role);
  const [memberQ, setMemberQ] = useState("");
  const members = useApi<Page<Member>>(staff && memberQ.length >= 2 ? `/api/members${qs({ q: memberQ, page_size: 8 })}` : null);
  const [memberId, setMemberId] = useState<number | null>(null);

  const refresh = () => { state.reload(); onChanged(); bump(); };
  const reserve = async (mid?: number) => {
    const r = await act(() => post<{ status?: string }>("/api/reservations", { book_id: id, member_id: mid }), (res: { status?: string }) =>
      res.status === "ready" ? "A copy is on hold — collect it from the desk" : "Added to the reservation queue");
    if (r) refresh();
  };
  const issue = async () => {
    if (!memberId) return;
    const r = await act(() => post<{ due_on: string }>("/api/loans/issue", { member_id: memberId, book_id: id }), (l) => `Issued — due ${fmtDate(l.due_on)}`);
    if (r) refresh();
  };
  const toggleMaintenance = async (copyId: number, status: string) => {
    const r = await act(() => patch(`/api/copies/${copyId}`, { status: status === "maintenance" ? "available" : "maintenance" }), "Copy status updated");
    if (r) refresh();
  };
  const addCopy = async () => {
    const r = await act(() => post(`/api/books/${id}/copies`, { count: 1, shelf: "NEW-1A" }), "Copy added (queue allocation re-checked)");
    if (r) refresh();
  };

  return (
    <Modal open onClose={onClose} title="Book details" wide>
      <Async state={state}>
        {(b) => {
          const mine = b.queue.find((r) => r.member_id === user.member_id);
          return (
            <div className="space-y-5">
              <div>
                <p className="eyebrow">{b.category} · ISBN {b.isbn}</p>
                <h3 className="mt-1 font-display text-2xl font-semibold">{b.title}</h3>
                <p className="text-sm text-ink2">{b.author} · {b.publisher}, {b.year}</p>
                <p className="mt-2 text-sm">{b.description}</p>
                <p className="mt-2 text-xs text-muted">Borrowed {b.times_borrowed} times · replacement cost {rupees(b.price)}</p>
              </div>
              {user.role === "member" && (
                <div className="flex flex-wrap items-center gap-2">
                  {mine ? <Notice tone="info">You are {mine.status === "ready" ? "holding a copy — collect it by " + fmtDate(mine.expires_on) : `#${mine.position} in the queue`}.</Notice>
                    : <button className="btn-primary" onClick={() => reserve()}><BookmarkPlus className="h-4 w-4" aria-hidden />{b.copies_available ? "Place on hold" : "Join the queue"}</button>}
                </div>
              )}
              {staff && (
                <div className="rounded-lg border border-line p-3">
                  <p className="label">Issue or reserve for a member</p>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input className="input" placeholder="Type a member name or code…" value={memberQ} onChange={(e) => { setMemberQ(e.target.value); setMemberId(null); }} aria-label="Find member" />
                    <button className="btn-primary" disabled={!memberId} onClick={issue}>Issue</button>
                    <button className="btn-secondary" disabled={!memberId} onClick={() => memberId && reserve(memberId)}>Reserve</button>
                  </div>
                  {members.data && !memberId && (
                    <ul className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-line">
                      {members.data.items.map((m) => (
                        <li key={m.id}><button className="w-full px-3 py-1.5 text-left text-sm hover:bg-sunken" onClick={() => { setMemberId(m.id); setMemberQ(`${m.name} (${m.code})`); }}>
                          {m.name} <span className="text-muted">· {m.code} · {m.member_type}</span></button></li>
                      ))}
                      {members.data.items.length === 0 && <li className="px-3 py-2 text-sm text-muted">No members found</li>}
                    </ul>
                  )}
                </div>
              )}
              <div className="grid gap-5 lg:grid-cols-2">
                <div>
                  <div className="mb-2 flex items-center justify-between"><h4 className="font-display text-base font-semibold">Physical copies</h4>
                    {staff && <button className="btn-ghost text-xs" onClick={addCopy}><Plus className="h-3.5 w-3.5" aria-hidden />Add copy</button>}</div>
                  <TableWrap label="Copies">
                    <table className="table-base">
                      <thead><tr><th>Barcode</th><th>Shelf</th><th>Status</th>{staff && <th className="text-right"><span className="sr-only">Actions</span></th>}</tr></thead>
                      <tbody>
                        {b.copies.map((c) => (
                          <tr key={c.id}>
                            <td className="font-mono text-xs">{c.barcode}</td><td className="font-mono text-xs">{c.shelf}</td><td><StatusBadge status={c.status} /></td>
                            {staff && <td className="text-right">{["available", "maintenance"].includes(c.status) && (
                              <button className="btn-ghost px-2 py-1 text-xs" onClick={() => toggleMaintenance(c.id, c.status)}><Wrench className="h-3.5 w-3.5" aria-hidden />{c.status === "maintenance" ? "Back to shelf" : "Maintenance"}</button>)}</td>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableWrap>
                </div>
                <div>
                  <h4 className="mb-2 font-display text-base font-semibold">Reservation queue (FIFO)</h4>
                  {b.queue.length === 0 ? <p className="text-sm text-muted">Nobody is waiting.</p> : (
                    <ol className="space-y-1.5">
                      {b.queue.map((r) => (
                        <li key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                          <span><span className="mr-2 font-mono text-xs text-muted">{r.position ? `#${r.position}` : "hold"}</span>{r.member_name}</span>
                          <StatusBadge status={r.status} label={r.status === "ready" ? `ready until ${fmtDate(r.expires_on)}` : `since ${fmtDate(r.created_on)}`} />
                        </li>
                      ))}
                    </ol>
                  )}
                  {staff && b.active_loans && b.active_loans.length > 0 && (
                    <>
                      <h4 className="mb-2 mt-4 font-display text-base font-semibold">Currently borrowed by</h4>
                      <ul className="space-y-1.5 text-sm">
                        {b.active_loans.map((l) => (
                          <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line px-3 py-2">
                            <span>{l.member_name} <span className="text-xs text-muted">due {fmtDate(l.due_on)}</span></span>
                            <span className="flex items-center gap-2">{(l.days_overdue ?? 0) > 0 && <StatusBadge status="overdue" label={`${l.days_overdue}d overdue`} />}<RiskPill score={l.risk_score} label={l.risk_label} /></span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        }}
      </Async>
    </Modal>
  );
}

const EMPTY_BOOK = { isbn: "", title: "", author: "", category: "", publisher: "", year: "2024", price: "500", description: "", copies: "1" };

function AddBookModal({ open, onClose, categories, onSaved }: { open: boolean; onClose: () => void; categories: string[]; onSaved: () => void }) {
  const [f, setF] = useState(EMPTY_BOOK);
  const [touched, setTouched] = useState(false);
  const act = useAction();
  const errors = {
    isbn: !isIsbn(f.isbn) ? "ISBN must be 10 or 13 digits" : null,
    title: required(f.title, "Title"),
    author: required(f.author, "Author"),
    category: required(f.category, "Category"),
    publisher: required(f.publisher, "Publisher"),
    year: !/^\d{4}$/.test(f.year) || +f.year < 1450 || +f.year > 2100 ? "Enter a valid year" : null,
    price: !(+f.price > 0) ? "Price must be positive" : null,
    copies: !/^\d+$/.test(f.copies) || +f.copies > 50 ? "0–50 copies" : null,
  };
  const set = (k: keyof typeof EMPTY_BOOK) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const show = (k: keyof typeof errors) => (touched ? errors[k] : null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    const r = await act(() => post("/api/books", { ...f, year: +f.year, price: +f.price, copies: +f.copies }), "Title added to the catalog");
    if (r) { setF(EMPTY_BOOK); setTouched(false); onSaved(); onClose(); }
  }
  return (
    <Modal open={open} onClose={onClose} title="Add a title">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
        <div className="sm:col-span-2"><Field label="Title" htmlFor="b-title" error={show("title")}><input id="b-title" className="input" value={f.title} onChange={set("title")} /></Field></div>
        <div className="sm:col-span-2"><Field label="Author(s)" htmlFor="b-author" error={show("author")}><input id="b-author" className="input" value={f.author} onChange={set("author")} /></Field></div>
        <Field label="ISBN" htmlFor="b-isbn" error={show("isbn")} hint="Digits only"><input id="b-isbn" className="input font-mono" inputMode="numeric" value={f.isbn} onChange={set("isbn")} /></Field>
        <Field label="Category" htmlFor="b-cat" error={show("category")}>
          <input id="b-cat" className="input" list="cat-list" value={f.category} onChange={set("category")} />
          <datalist id="cat-list">{categories.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
        <Field label="Publisher" htmlFor="b-pub" error={show("publisher")}><input id="b-pub" className="input" value={f.publisher} onChange={set("publisher")} /></Field>
        <Field label="Year" htmlFor="b-year" error={show("year")}><input id="b-year" className="input" inputMode="numeric" value={f.year} onChange={set("year")} /></Field>
        <Field label="Replacement cost (₹)" htmlFor="b-price" error={show("price")}><input id="b-price" className="input" inputMode="decimal" value={f.price} onChange={set("price")} /></Field>
        <Field label="Copies" htmlFor="b-copies" error={show("copies")}><input id="b-copies" className="input" inputMode="numeric" value={f.copies} onChange={set("copies")} /></Field>
        <div className="sm:col-span-2"><Field label="Description" htmlFor="b-desc"><textarea id="b-desc" className="input" rows={3} maxLength={2000} value={f.description} onChange={set("description")} /></Field></div>
        <div className={cx("flex justify-end gap-2 sm:col-span-2")}><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary">Save title</button></div>
      </form>
    </Modal>
  );
}
