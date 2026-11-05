import { useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, BrainCircuit, ChevronDown, Cpu, KeyRound, Moon, Search, Sun, UserPlus } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useApi } from "../lib/useApi";
import { humanise } from "../lib/format";
import { isEmail, isPhone, passwordError, required } from "../lib/validation";
import { Field, Notice, Tabs } from "../components/ui";

interface DemoAccount { role: string; email: string; password: string; name: string; note: string }
interface DemoMember { name: string; email: string; member_type: string; department: string; password: string }

// The hero panel keeps the same dark "ink" look in both themes, so its colours are fixed.
const HERO = { bg: "#1d2433", text: "#f5f1e8", accent: "#ee805f", teal: "#5cbeb4" };

export default function LoginPage() {
  const { theme, toggle } = useTheme();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [prefill, setPrefill] = useState<{ email: string; password: string } | null>(null);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.1fr,1fr]">
      <section className="relative hidden overflow-hidden p-12 lg:flex lg:flex-col" style={{ background: HERO.bg, color: HERO.text }}>
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "repeating-linear-gradient(90deg, currentColor 0 1px, transparent 1px 64px), repeating-linear-gradient(0deg, currentColor 0 1px, transparent 1px 64px)" }} aria-hidden />
        <p className="relative font-mono text-xs uppercase tracking-[0.2em] opacity-60">Fundamentals of AI · Microproject</p>
        <h1 className="relative mt-6 max-w-xl font-display text-5xl font-semibold leading-[1.05]">
          An intelligent agent that <em className="not-italic" style={{ color: HERO.accent }}>perceives</em>, <em className="not-italic" style={{ color: HERO.teal }}>reasons</em> and{" "}
          <em className="not-italic underline decoration-2 underline-offset-4" style={{ textDecorationColor: HERO.accent }}>acts</em> on library circulation.
        </h1>
        <ul className="relative mt-10 grid max-w-lg gap-4 text-sm opacity-85">
          <li className="flex gap-3"><Cpu className="h-5 w-5 shrink-0" style={{ color: HERO.accent }} aria-hidden />Sense-think-act loop on a simulated clock with a full decision trace.</li>
          <li className="flex gap-3"><BookOpen className="h-5 w-5 shrink-0" style={{ color: HERO.teal }} aria-hidden />Forward-chaining expert system, fuzzy priority levels and a heap-based notification queue.</li>
          <li className="flex gap-3"><BrainCircuit className="h-5 w-5 shrink-0" style={{ color: HERO.accent }} aria-hidden />Late-return prediction as decision support — fines stay deterministic, humans approve high-impact actions.</li>
        </ul>
        <p className="relative mt-auto font-mono text-[11px] opacity-50">Runs fully offline · SQLite · FastAPI · React</p>
      </section>

      <section className="flex min-h-screen flex-col px-4 py-6 sm:px-10">
        <div className="flex justify-end">
          <button className="btn-ghost p-2" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
        <div className="mx-auto my-auto w-full max-w-md py-8">
          <p className="eyebrow">Circulus</p>
          <h2 className="mt-1 text-3xl font-semibold">{mode === "signin" ? "Sign in to the library agent" : "Create a member account"}</h2>
          <p className="mt-1 text-sm text-ink2">Intelligent Library Circulation, Fine Calculation and Priority Notification Agent.</p>
          <div className="mt-5">
            <Tabs label="Sign in or create an account" value={mode} onChange={setMode}
              options={[{ value: "signin", label: "Sign in" }, { value: "register", label: "Create account" }]} />
          </div>
          {mode === "signin"
            ? <SignInForm key={prefill ? prefill.email : "blank"} prefill={prefill} onPick={setPrefill} />
            : <RegisterForm />}
        </div>
      </section>
    </div>
  );
}

function SignInForm({ prefill, onPick }: { prefill: { email: string; password: string } | null; onPick: (p: { email: string; password: string }) => void }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const accounts = useApi<DemoAccount[]>("/api/auth/demo-accounts");
  const [email, setEmail] = useState(prefill?.email ?? "");
  const [password, setPassword] = useState(prefill?.password ?? "");
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);

  const emailError = touched && !isEmail(email) ? "Enter a valid email address" : null;
  const pwError = touched && !password ? "Password is required" : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!isEmail(email) || !password) return;
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
        {error && <Notice tone="error">{error}. Use one of the accounts below, or create your own account.</Notice>}
        <Field label="Email" htmlFor="email" error={emailError}>
          <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!emailError} />
        </Field>
        <Field label="Password" htmlFor="password" error={pwError}>
          <input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!pwError} />
        </Field>
        <button className="btn-primary w-full py-2.5" disabled={busy}>{busy ? "Signing in…" : <>Sign in <ArrowRight className="h-4 w-4" aria-hidden /></>}</button>
      </form>

      <div className="mt-8">
        <p className="eyebrow mb-2 flex items-center gap-1.5"><KeyRound className="h-3.5 w-3.5" aria-hidden />Demo credentials — click to fill</p>
        {accounts.error && <Notice tone="warn">Could not load demo accounts: {accounts.error}</Notice>}
        <ul className="grid gap-2">
          {(accounts.data ?? []).map((a) => (
            <li key={a.email} className="min-w-0">
              <button type="button" onClick={() => onPick({ email: a.email, password: a.password })}
                className="card flex w-full items-start gap-3 px-3 py-2.5 text-left transition hover:border-accent/60">
                <span className="mt-0.5 rounded-md bg-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-paper">{a.role}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{a.name}</span>
                  <span className="block break-all font-mono text-xs text-ink2">{a.email} · {a.password}</span>
                  <span className="block text-xs text-muted">{a.note}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <MoreMembers onPick={onPick} />
      </div>
    </>
  );
}

function MoreMembers({ onPick }: { onPick: (p: { email: string; password: string }) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const members = useApi<DemoMember[]>(open ? "/api/auth/demo-members" : null);
  const shown = useMemo(() => (members.data ?? []).filter((m) => `${m.name} ${m.email} ${m.department}`.toLowerCase().includes(q.toLowerCase())), [members.data, q]);
  return (
    <div className="mt-3 rounded-lg border border-line">
      <button type="button" className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm font-medium" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>All other member accounts (35) · password <span className="font-mono">Member@123</span></span>
        <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <div className="border-t border-line p-2">
          <label className="relative block">
            <span className="sr-only">Search members</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input className="input pl-9" placeholder="Search name, email or department…" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          {members.error && <p className="mt-2 text-sm text-crit">{members.error}</p>}
          <ul className="mt-2 max-h-64 overflow-y-auto">
            {shown.map((m) => (
              <li key={m.email}>
                <button type="button" onClick={() => onPick({ email: m.email, password: m.password })} className="w-full rounded-md px-2 py-1.5 text-left hover:bg-sunken">
                  <span className="block text-sm">{m.name} <span className="text-xs text-muted">· {humanise(m.member_type)} · {m.department}</span></span>
                  <span className="block break-all font-mono text-xs text-ink2">{m.email}</span>
                </button>
              </li>
            ))}
            {members.data && shown.length === 0 && <li className="px-2 py-2 text-sm text-muted">No member matches “{q}”.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

const EMPTY = { name: "", email: "", password: "", confirm: "", member_type: "student", department: "", phone: "", notify_pref: "email" };

function RegisterForm() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState(EMPTY);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errors = {
    name: required(f.name, "Full name", 2),
    email: isEmail(f.email) ? null : "Enter a valid email address",
    password: passwordError(f.password),
    confirm: f.confirm === f.password ? null : "Passwords do not match",
    department: required(f.department, "Department", 2),
    phone: !f.phone.trim() || isPhone(f.phone) ? null : "8–16 digits, optional + (or leave blank)",
  };
  const err = (k: keyof typeof errors) => (touched ? errors[k] : null);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    setBusy(true);
    setError(null);
    try {
      const { confirm: _c, ...data } = f;
      void _c;
      await register(data);
      navigate("/", { replace: true });
    } catch (ex) {
      setError((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-5 grid gap-4 sm:grid-cols-2" noValidate>
      {error && <div className="sm:col-span-2"><Notice tone="error">{error}</Notice></div>}
      <div className="sm:col-span-2"><Field label="Full name" htmlFor="r-name" error={err("name")}><input id="r-name" className="input" autoComplete="name" value={f.name} onChange={set("name")} /></Field></div>
      <div className="sm:col-span-2"><Field label="Email" htmlFor="r-email" error={err("email")}><input id="r-email" className="input" type="email" autoComplete="email" value={f.email} onChange={set("email")} /></Field></div>
      <Field label="Password" htmlFor="r-pw" error={err("password")} hint="8+ characters, letters and digits">
        <input id="r-pw" className="input" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} /></Field>
      <Field label="Confirm password" htmlFor="r-pw2" error={err("confirm")}>
        <input id="r-pw2" className="input" type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} /></Field>
      <Field label="I am a" htmlFor="r-type"><select id="r-type" className="input" value={f.member_type} onChange={set("member_type")}>
        <option value="student">Student</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></Field>
      <Field label="Department" htmlFor="r-dept" error={err("department")}><input id="r-dept" className="input" value={f.department} onChange={set("department")} /></Field>
      <Field label="Phone (optional)" htmlFor="r-phone" error={err("phone")}><input id="r-phone" className="input" inputMode="tel" autoComplete="tel" value={f.phone} onChange={set("phone")} /></Field>
      <Field label="Notify me by" htmlFor="r-pref"><select id="r-pref" className="input" value={f.notify_pref} onChange={set("notify_pref")}>
        <option value="in_app">In-app</option><option value="email">Email</option><option value="sms">SMS</option></select></Field>
      <p className="text-xs text-muted sm:col-span-2">Creates a library <strong>member</strong> account. Staff (librarian/admin) accounts are created by an administrator. Only academic details are collected.</p>
      <button className="btn-primary w-full py-2.5 sm:col-span-2" disabled={busy}>{busy ? "Creating account…" : <><UserPlus className="h-4 w-4" aria-hidden />Create account & sign in</>}</button>
    </form>
  );
}
