/**
 * Shared simulated-clock state + "auto mode" (advance one day and run a cycle on
 * an interval). Lives above the router so auto mode keeps running while the
 * user navigates between pages.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { get, post } from "../lib/api";
import type { AgentStatus } from "../lib/types";
import { useAuth } from "./AuthContext";

interface AgentCtx {
  status: AgentStatus | null;
  refresh: () => Promise<void>;
  auto: boolean;
  setAuto: (on: boolean) => void;
  busy: boolean;
  lastError: string | null;
  tick: number; // increments whenever the environment changed (pages can re-fetch)
  bump: () => void;
}

const Ctx = createContext<AgentCtx | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [auto, setAutoState] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const running = useRef(false);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      setStatus(await get<AgentStatus>("/api/agent/status"));
    } catch {
      /* surfaced by pages */
    }
  }, [user]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const bump = useCallback(() => {
    setTick((t) => t + 1);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!auto || !user || user.role === "member") return;
    const ms = Math.max(1, status?.auto_interval_sec ?? 4) * 1000;
    const id = window.setInterval(async () => {
      if (running.current) return;
      running.current = true;
      setBusy(true);
      try {
        await post("/api/agent/advance", { days: 1, run_agent: true });
        setLastError(null);
        bump();
      } catch (e) {
        setLastError((e as Error).message);
        setAutoState(false);
      } finally {
        running.current = false;
        setBusy(false);
      }
    }, ms);
    return () => window.clearInterval(id);
  }, [auto, user, status?.auto_interval_sec, bump]);

  useEffect(() => {
    if (!user) setAutoState(false);
  }, [user]);

  return (
    <Ctx.Provider value={{ status, refresh, auto, setAuto: setAutoState, busy, lastError, tick, bump }}>{children}</Ctx.Provider>
  );
}

export function useAgent(): AgentCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAgent outside provider");
  return ctx;
}
