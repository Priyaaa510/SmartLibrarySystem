import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { errorMessage } from '../api';

// ---------------------------------------------------------------- toasts
type Toast = { id: number; kind: 'success' | 'error' | 'info'; text: string };
const ToastContext = createContext<(kind: Toast['kind'], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`} onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
            <span aria-hidden>{t.kind === 'success' ? '✓' : t.kind === 'error' ? '!' : 'i'}</span>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  return {
    success: (t: string) => push('success', t),
    info: (t: string) => push('info', t),
    error: (e: unknown) => push('error', typeof e === 'string' ? e : errorMessage(e)),
  };
}

// ---------------------------------------------------------------- data loading
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(errorMessage(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

// ---------------------------------------------------------------- formatting
export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s.length === 10 ? `${s}T00:00:00` : s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
export const fmtDateTime = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
export const money = (n: number) => `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
export const daysUntil = (d: string) => Math.round((new Date(`${d}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()) / 864e5);

// ---------------------------------------------------------------- small components
const BADGE: Record<string, string> = {
  available: 'good', returned: 'neutral', paid: 'good', fulfilled: 'good', ready: 'good', active: 'info',
  on_loan: 'info', waiting: 'info', on_hold: 'warn', maintenance: 'warn', unpaid: 'warn', due_soon: 'warn',
  overdue: 'bad', lost: 'bad', damaged: 'bad', expired: 'neutral', cancelled: 'neutral', withdrawn: 'neutral',
  waived: 'neutral', inactive: 'neutral', admin: 'bad', librarian: 'info', member: 'neutral',
};
export function Badge({ status, label }: { status: string; label?: string }) {
  return <span className={`badge badge-${BADGE[status] ?? 'neutral'}`}>{label ?? status.replace('_', ' ')}</span>;
}

export function Stars({ value, count }: { value: number | null; count?: number }) {
  if (value == null) return <span className="muted small">No ratings</span>;
  const full = Math.round(value);
  return (
    <span className="stars" title={`${value.toFixed(1)} out of 5`}>
      <span aria-hidden>{'★'.repeat(full)}<span className="stars-off">{'★'.repeat(5 - full)}</span></span>
      <span className="small muted"> {value.toFixed(1)}{count != null && ` (${count})`}</span>
    </span>
  );
}

export function StarInput({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <span className="star-input" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button type="button" key={n} role="radio" aria-checked={value === n} className={n <= value ? 'on' : ''} onClick={() => onChange(n)}>★</button>
      ))}
    </span>
  );
}

export function Cover({ src, title, size = 'md' }: { src: string | null; title: string; size?: 'sm' | 'md' | 'lg' }) {
  const [failed, setFailed] = useState(false);
  const initials = title.split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  let hue = 0;
  for (const ch of title) hue = (hue * 31 + ch.charCodeAt(0)) % 360;
  if (!src || failed) {
    return <div className={`cover cover-${size} cover-fallback`} style={{ ['--hue' as string]: hue }}><span>{initials}</span></div>;
  }
  return <img className={`cover cover-${size}`} src={src} alt="" loading="lazy" onError={() => setFailed(true)}
    onLoad={(e) => { if ((e.target as HTMLImageElement).naturalWidth < 5) setFailed(true); }} />;
}

export function Pagination({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (total <= size) return <p className="muted small pager-info">{total} result{total === 1 ? '' : 's'}</p>;
  return (
    <div className="pager">
      <span className="muted small">{(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}</span>
      <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Prev</button>
      <span className="small">Page {page} / {pages}</span>
      <button className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next ›</button>
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close">✕</button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

/** In-app confirmation (never a blocking browser dialog). */
export function useConfirm() {
  const [state, setState] = useState<{ text: string; resolve: (ok: boolean) => void } | null>(null);
  const confirm = (text: string) => new Promise<boolean>((resolve) => setState({ text, resolve }));
  const close = (ok: boolean) => { state?.resolve(ok); setState(null); };
  const dialog = state && (
    <Modal title="Please confirm" onClose={() => close(false)}>
      <p>{state.text}</p>
      <div className="row-end">
        <button className="btn btn-ghost" onClick={() => close(false)}>Cancel</button>
        <button className="btn btn-primary" autoFocus onClick={() => close(true)}>Confirm</button>
      </div>
    </Modal>
  );
  return { confirm, dialog };
}

export function Empty({ icon = '📭', title, children }: { icon?: string; title: string; children?: ReactNode }) {
  return <div className="empty"><div className="empty-icon" aria-hidden>{icon}</div><strong>{title}</strong>{children && <div className="muted">{children}</div>}</div>;
}

export function Loading() { return <div className="loading" aria-label="Loading"><span /><span /><span /></div>; }

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return <div className="alert alert-bad">{error} {onRetry && <button className="btn btn-sm btn-ghost" onClick={onRetry}>Retry</button>}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'bad' | 'warn' | 'good' }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ''}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small className="muted">{hint}</small>}</label>;
}
