import { FormEvent, useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { api, Category } from '../api';
import { useAuth } from '../auth';
import { Field, useToast } from '../components/ui';

const DEMO = [
  ['Admin', 'admin@library.com', 'admin123'],
  ['Librarian', 'librarian@library.com', 'librarian123'],
  ['Member', 'rahul@example.com', 'member123'],
];

export default function Login() {
  const { user, login, register } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '', phone: '' });
  const [cats, setCats] = useState<Category[]>([]);
  const [prefs, setPrefs] = useState<string[]>([]);

  useEffect(() => { api.get<Category[]>('/categories').then((r) => setCats(r.data)).catch(() => {}); }, []);
  if (user) return <Navigate to="/" replace />;

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === 'login') await login(form.email, form.password);
      else await register({ ...form, phone: form.phone || null, preferred_categories: prefs });
      navigate('/');
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-hero">
        <div className="brand"><span aria-hidden>📚</span> Smart Library</div>
        <h1>Your library, <br />online.</h1>
        <p>Search the catalog, reserve books, renew loans and track fines — all in one place.</p>
        <ul>
          <li>📖 Borrow, renew &amp; place holds</li>
          <li>✨ Personalised recommendations</li>
          <li>🔔 Due-date reminders</li>
        </ul>
      </section>
      <section className="login-card">
        <div className="tabs">
          <button className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>Sign in</button>
          <button className={mode === 'register' ? 'on' : ''} onClick={() => setMode('register')}>Become a member</button>
        </div>
        <form onSubmit={submit} className="stack">
          {mode === 'register' && <Field label="Full name"><input required minLength={2} value={form.name} onChange={set('name')} /></Field>}
          <Field label="Email"><input type="email" required autoComplete="email" value={form.email} onChange={set('email')} /></Field>
          <Field label="Password"><input type="password" required minLength={mode === 'register' ? 6 : 1} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={form.password} onChange={set('password')} /></Field>
          {mode === 'register' && (
            <>
              <Field label="Phone (optional)"><input value={form.phone} onChange={set('phone')} /></Field>
              <fieldset className="field">
                <span>Interests (for recommendations)</span>
                <div className="chips">
                  {cats.map((c) => (
                    <button type="button" key={c.id} className={`chip ${prefs.includes(c.name) ? 'on' : ''}`}
                      onClick={() => setPrefs(prefs.includes(c.name) ? prefs.filter((p) => p !== c.name) : [...prefs, c.name])}>
                      {c.name}
                    </button>
                  ))}
                </div>
              </fieldset>
            </>
          )}
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
        </form>
        {mode === 'login' && (
          <div className="demo">
            <span className="muted small">Demo accounts — click to fill:</span>
            <div className="chips">
              {DEMO.map(([label, email, pw]) => (
                <button key={email} type="button" className="chip" onClick={() => setForm({ ...form, email, password: pw })}>{label}</button>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
