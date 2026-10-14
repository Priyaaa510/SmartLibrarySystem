import { FormEvent, useState } from 'react';
import { api, Category } from '../api';
import { useAuth } from '../auth';
import { Field, fmtDate, money, useLoad, useToast } from '../components/ui';

export default function Profile() {
  const { user, refresh } = useAuth();
  const toast = useToast();
  const { data: cats } = useLoad(() => api.get<Category[]>('/categories').then((r) => r.data), []);
  const [f, setF] = useState({ name: user?.name ?? '', phone: user?.phone ?? '', address: user?.address ?? '', preferred_categories: user?.preferred_categories ?? [] });
  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' });
  if (!user) return null;
  const plan = user.membership_type;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.put('/auth/me', { ...f, phone: f.phone || null, address: f.address || null }); await refresh(); toast.success('Profile saved'); } catch (err) { toast.error(err); }
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault();
    if (pw.new_password !== pw.confirm) return toast.error('New passwords do not match');
    try { await api.post('/auth/change-password', { current_password: pw.current_password, new_password: pw.new_password }); toast.success('Password changed'); setPw({ current_password: '', new_password: '', confirm: '' }); } catch (err) { toast.error(err); }
  };

  return (
    <>
      <div className="page-head"><div><h1>My Profile</h1><p className="muted">Member code <span className="mono">{user.member_code}</span> · {user.email}</p></div></div>
      <div className="two-col">
        <form className="card stack" onSubmit={save}>
          <h2>Personal details</h2>
          <Field label="Full name"><input required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Phone"><input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Field label="Address"><input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
          <fieldset className="field">
            <span>Interests (used for recommendations)</span>
            <div className="chips">
              {cats?.map((c) => {
                const on = f.preferred_categories.includes(c.name);
                return <button type="button" key={c.id} className={`chip ${on ? 'on' : ''}`} onClick={() => setF({ ...f, preferred_categories: on ? f.preferred_categories.filter((x) => x !== c.name) : [...f.preferred_categories, c.name] })}>{c.name}</button>;
              })}
            </div>
          </fieldset>
          <button className="btn btn-primary">Save changes</button>
        </form>
        <div className="stack">
          <section className="card">
            <h2>Membership</h2>
            {plan ? (
              <dl className="meta">
                <div><dt>Plan</dt><dd>{plan.name}</dd></div>
                <div><dt>Valid until</dt><dd>{fmtDate(user.membership_expiry)}</dd></div>
                <div><dt>Borrowing limit</dt><dd>{plan.max_books} books</dd></div>
                <div><dt>Loan period</dt><dd>{plan.loan_days} days</dd></div>
                <div><dt>Renewals</dt><dd>{plan.max_renewals} per loan</dd></div>
                <div><dt>Late fine</dt><dd>{money(plan.fine_per_day)} / day</dd></div>
              </dl>
            ) : <p className="muted">No membership plan.</p>}
          </section>
          <form className="card stack" onSubmit={changePw}>
            <h2>Change password</h2>
            <Field label="Current password"><input type="password" required autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label="New password"><input type="password" required minLength={6} autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
            <Field label="Confirm new password"><input type="password" required minLength={6} autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></Field>
            <button className="btn">Update password</button>
          </form>
        </div>
      </div>
    </>
  );
}
