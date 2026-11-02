import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, BrainCircuit, Cpu, KeyRound, Moon, Sun } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useApi } from "../lib/useApi";
import { isEmail } from "../lib/validation";
import { Field, Notice } from "../components/ui";

interface DemoAccount { role: string; email: string; password: string; name: string; note: string }

export default function LoginPage() {
  const { login } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const accounts = useApi<DemoAccount[]>("/api/auth/demo-accounts");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="min-h-screen lg:grid lg:grid-cols-[1.1fr,1fr]">
      <section className="relative hidden overflow-hidden bg-ink p-12 text-paper lg:flex lg:flex-col">
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "repeating-linear-gradient(90deg, currentColor 0 1px, transparent 1px 64px), repeating-linear-gradient(0deg, currentColor 0 1px, transparent 1px 64px)" }} aria-hidden />
        <p className="relative font-mono text-xs uppercase tracking-[0.2em] text-paper/60">Fundamentals of AI · Microproject</p>
        <h1 className="relative mt-6 max-w-xl font-display text-5xl font-semibold leading-[1.05]">
          An intelligent agent that <em className="not-italic text-[#ee805f]">perceives</em>, <em className="not-italic text-[#5cbeb4]">reasons</em> and <em className="not-italic underline decoration-[#ee805f] decoration-2 underline-offset-4">acts</em> on library circulation.
        </h1>
        <ul className="relative mt-10 grid max-w-lg gap-4 text-sm text-paper/80">
          <li className="flex gap-3"><Cpu className="h-5 w-5 shrink-0 text-[#ee805f]" aria-hidden />Sense-think-act loop on a simulated clock with a full decision trace.</li>
          <li className="flex gap-3"><BookOpen className="h-5 w-5 shrink-0 text-[#5cbeb4]" aria-hidden />Forward-chaining expert system, fuzzy priority levels and a heap-based notification queue.</li>
          <li className="flex gap-3"><BrainCircuit className="h-5 w-5 shrink-0 text-[#ee805f]" aria-hidden />Late-return prediction as decision support — fines stay deterministic, humans approve high-impact actions.</li>
        </ul>
        <p className="relative mt-auto font-mono text-[11px] text-paper/50">Runs fully offline · SQLite · FastAPI · React</p>
      </section>

      <section className="flex min-h-screen flex-col px-4 py-6 sm:px-10">
        <div className="flex justify-end">
          <button className="btn-ghost p-2" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
        <div className="mx-auto my-auto w-full max-w-md py-8">
          <p className="eyebrow">Circulus</p>
          <h2 className="mt-1 text-3xl font-semibold">Sign in to the library agent</h2>
          <p className="mt-1 text-sm text-ink2">Intelligent Library Circulation, Fine Calculation and Priority Notification Agent.</p>

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            {error && <Notice tone="error">{error}</Notice>}
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
                <li key={a.email}>
                  <button type="button" onClick={() => { setEmail(a.email); setPassword(a.password); setTouched(false); }}
                    className="card flex w-full items-start gap-3 px-3 py-2.5 text-left transition hover:border-accent/60">
                    <span className="mt-0.5 rounded-md bg-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-paper">{a.role}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">{a.name}</span>
                      <span className="block truncate font-mono text-xs text-ink2">{a.email} · {a.password}</span>
                      <span className="block text-xs text-muted">{a.note}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">Every other seeded member can sign in with their college email and <span className="font-mono">Member@123</span>.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
