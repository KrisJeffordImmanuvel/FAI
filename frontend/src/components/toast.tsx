import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { cx } from "./ui";

interface Toast { id: number; tone: "success" | "error"; text: string }
const Ctx = createContext<(tone: Toast["tone"], text: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, tone, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 7000 : 4000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,380px)] flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className={cx("card animate-slide-in pointer-events-auto flex items-start gap-2 px-3 py-2.5 text-sm shadow-lift",
            t.tone === "error" ? "border-crit/50" : "border-good/40")} role={t.tone === "error" ? "alert" : "status"}>
            {t.tone === "error" ? <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-crit" aria-hidden /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-good" aria-hidden />}
            <p className="flex-1">{t.text}</p>
            <button className="text-muted hover:text-ink" aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);

/** Run an async action and surface success/failure as a toast. Returns the result or null. */
export function useAction() {
  const toast = useToast();
  return useCallback(async <T,>(fn: () => Promise<T>, success?: string | ((r: T) => string)): Promise<T | null> => {
    try {
      const r = await fn();
      if (success) toast("success", typeof success === "function" ? success(r) : success);
      return r;
    } catch (e) {
      toast("error", (e as Error).message);
      return null;
    }
  }, [toast]);
}
