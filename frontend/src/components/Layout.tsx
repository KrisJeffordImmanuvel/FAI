import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeftRight, Bell, KeyRound, BookOpen, BookmarkCheck, BrainCircuit, CalendarClock, ChartLine, Circle, Cpu, Info, LayoutDashboard, Lightbulb, LogOut, Menu,
  Moon, Network, Receipt, ScrollText, Settings, ShieldCheck, Sun, Users, X, Zap, type LucideIcon,
} from "lucide-react";
import { useAuth, useUser } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useAgent } from "../context/AgentContext";
import { navFor, type NavItem } from "../lib/roles";
import { fmtDate, humanise } from "../lib/format";
import { cx } from "./ui";
import ChangePasswordModal from "./ChangePassword";

const ICONS: Record<string, LucideIcon> = {
  ArrowLeftRight, Bell, BookOpen, BookmarkCheck, BrainCircuit, ChartLine, Cpu, Info, LayoutDashboard, Lightbulb, Network, Receipt, ScrollText, Settings,
  ShieldCheck, Users,
};

function NavIcon({ name }: { name: string }) {
  const Icon = ICONS[name] ?? Circle;
  return <Icon className="h-4 w-4 shrink-0" aria-hidden />;
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="7" fill="rgb(var(--ink))" />
        <rect x="7" y="8" width="4" height="16" rx="1" fill="rgb(var(--paper))" />
        <rect x="13" y="6" width="4" height="18" rx="1" fill="rgb(var(--accent))" />
        <rect x="19.5" y="9" width="4" height="15" rx="1" transform="rotate(-12 21.5 16)" fill="rgb(var(--teal))" />
      </svg>
      <div className="leading-tight">
        <p className="font-display text-lg font-semibold">Circulus</p>
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">Library agent</p>
      </div>
    </div>
  );
}

function SideNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const groups = ["Library", "Agent", "Insight", "System"] as const;
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {groups.map((g) => {
        const list = items.filter((i) => i.group === g);
        if (!list.length) return null;
        return (
          <div key={g}>
            <p className="eyebrow mb-1.5 px-3">{g}</p>
            <ul className="flex flex-col gap-0.5">
              {list.map((i) => (
                <li key={i.to}>
                  <NavLink to={i.to} end={i.to === "/"} onClick={onNavigate}
                    className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition",
                      isActive ? "bg-ink text-paper font-medium" : "text-ink2 hover:bg-sunken hover:text-ink")}>
                    <NavIcon name={i.icon} /> {i.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function ClockBadge() {
  const { status, auto, busy } = useAgent();
  const user = useUser();
  const navigate = useNavigate();
  if (!status) return null;
  const content = (
    <>
      <CalendarClock className="h-4 w-4 text-accent" aria-hidden />
      <span className="hidden text-muted sm:inline">Simulated date</span>
      <span className="font-medium">{fmtDate(status.sim_date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</span>
      {auto && <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-medium text-accent"><Zap className={cx("h-3 w-3", busy && "animate-pulse")} aria-hidden />Auto</span>}
    </>
  );
  return user.role === "member" ? (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm">{content}</div>
  ) : (
    <button onClick={() => navigate("/agent")} className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm hover:bg-sunken" title="Open Agent control">
      {content}
    </button>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const user = useUser();
  const { logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const location = useLocation();
  const items = navFor(user.role);

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    const title = items.find((i) => (i.to === "/" ? location.pathname === "/" : location.pathname.startsWith(i.to)))?.label ?? "Circulus";
    document.title = `${title} · Circulus`;
  }, [location.pathname, items]);

  const sidebar = (
    <div className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5">
      <div className="px-2"><Brand /></div>
      <SideNav items={items} onNavigate={() => setOpen(false)} />
      <div className="mt-auto rounded-lg border border-line bg-surface p-3 text-sm">
        <p className="truncate font-medium">{user.name}</p>
        <p className="truncate text-xs text-muted">{humanise(user.role)} · {user.email}</p>
        <button className="btn-ghost mt-2 w-full justify-start px-2" onClick={() => { setOpen(false); setPwOpen(true); }}><KeyRound className="h-4 w-4" aria-hidden /> Change password</button>
        <button className="btn-ghost w-full justify-start px-2" onClick={logout}><LogOut className="h-4 w-4" aria-hidden /> Sign out</button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px,1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[70] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:shadow-lift">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen border-r border-line bg-paper/80 backdrop-blur lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-[min(84vw,290px)] border-r border-line bg-paper shadow-lift">
            <button className="btn-ghost absolute right-2 top-3 p-2" onClick={() => setOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" /></button>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-line bg-paper/85 px-4 py-2.5 backdrop-blur sm:px-6">
          <button className="btn-ghost p-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu className="h-5 w-5" /></button>
          <div className="lg:hidden"><span className="font-display text-lg font-semibold">Circulus</span></div>
          <div className="ml-auto flex items-center gap-2">
            <ClockBadge />
            <button className="btn-ghost p-2" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
        <main id="main" className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
