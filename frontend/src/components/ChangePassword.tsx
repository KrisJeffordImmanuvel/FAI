import { useState, type FormEvent } from "react";
import { post } from "../lib/api";
import { passwordError } from "../lib/validation";
import { Field, Modal, Notice } from "./ui";
import { useToast } from "./toast";

export default function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ current: "", next: "", confirm: "" });
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errors = {
    current: f.current ? null : "Enter your current password",
    next: passwordError(f.next),
    confirm: f.confirm === f.next ? null : "Passwords do not match",
  };
  const close = () => { setF({ current: "", next: "", confirm: "" }); setTouched(false); setError(null); onClose(); };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    setBusy(true);
    setError(null);
    try {
      await post("/api/auth/change-password", { current_password: f.current, new_password: f.next });
      toast("success", "Password changed — use the new one next time you sign in");
      close();
    } catch (ex) {
      setError((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={close} title="Change password">
      <form onSubmit={submit} className="space-y-3" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Current password" htmlFor="cp-cur" error={touched ? errors.current : null}>
          <input id="cp-cur" type="password" className="input" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></Field>
        <Field label="New password" htmlFor="cp-new" error={touched ? errors.next : null} hint="8+ characters, letters and digits">
          <input id="cp-new" type="password" className="input" autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></Field>
        <Field label="Confirm new password" htmlFor="cp-conf" error={touched ? errors.confirm : null}>
          <input id="cp-conf" type="password" className="input" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={close}>Cancel</button><button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Change password"}</button></div>
      </form>
    </Modal>
  );
}
