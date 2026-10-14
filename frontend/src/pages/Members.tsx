import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, Category, MemberSummary, Page, Plan, User } from '../api';
import { useAuth } from '../auth';
import { Badge, Empty, ErrorBox, Field, fmtDate, Loading, Modal, money, Pagination, useLoad, useToast } from '../components/ui';

export function MemberForm({ member, onClose, onSaved }: { member?: User; onClose: () => void; onSaved: (u: User) => void }) {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data: plans } = useLoad(() => api.get<Plan[]>('/membership-types').then((r) => r.data), []);
  const { data: cats } = useLoad(() => api.get<Category[]>('/categories').then((r) => r.data), []);
  const [f, setF] = useState({
    name: member?.name ?? '', email: member?.email ?? '', password: '', phone: member?.phone ?? '', address: member?.address ?? '',
    role: member?.role ?? 'member', membership_type_id: String(member?.membership_type?.id ?? ''),
    membership_expiry: member?.membership_expiry ?? '', preferred_categories: member?.preferred_categories ?? [],
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const base = {
      name: f.name, email: f.email, phone: f.phone || null, address: f.address || null,
      preferred_categories: f.preferred_categories,
      membership_type_id: f.membership_type_id ? Number(f.membership_type_id) : null,
      ...(isAdmin ? { role: f.role } : {}),
    };
    try {
      const r = member
        ? await api.put<User>(`/members/${member.id}`, { ...base, membership_expiry: f.membership_expiry || null })
        : await api.post<User>('/members', { ...base, password: f.password });
      toast.success(member ? 'Member updated' : `Member created — code ${r.data.member_code}`);
      onSaved(r.data);
    } catch (err) { toast.error(err); }
  };

  return (
    <Modal title={member ? `Edit ${member.name}` : 'Register a new member'} onClose={onClose} wide>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Full name *"><input required minLength={2} value={f.name} onChange={set('name')} /></Field>
        <Field label="Email *"><input required type="email" value={f.email} onChange={set('email')} /></Field>
        {!member && <Field label="Initial password *" hint="At least 6 characters — the member can change it later"><input required minLength={6} value={f.password} onChange={set('password')} /></Field>}
        <Field label="Phone"><input value={f.phone} onChange={set('phone')} /></Field>
        <Field label="Address"><input value={f.address} onChange={set('address')} /></Field>
        <Field label="Membership plan">
          <select value={f.membership_type_id} onChange={set('membership_type_id')}>
            <option value="">{member ? 'No plan' : 'Default (Student)'}</option>
            {plans?.map((p) => <option key={p.id} value={p.id}>{p.name} — {p.max_books} books / {p.loan_days} days</option>)}
          </select>
        </Field>
        {member && <Field label="Membership expiry"><input type="date" value={f.membership_expiry} onChange={set('membership_expiry')} /></Field>}
        {isAdmin && (
          <Field label="Role">
            <select value={f.role} onChange={set('role')}><option value="member">Member</option><option value="librarian">Librarian</option><option value="admin">Admin</option></select>
          </Field>
        )}
        <fieldset className="field span-2">
          <span>Interests</span>
          <div className="chips">
            {cats?.map((c) => {
              const on = f.preferred_categories.includes(c.name);
              return <button type="button" key={c.id} className={`chip ${on ? 'on' : ''}`} onClick={() => setF({ ...f, preferred_categories: on ? f.preferred_categories.filter((x) => x !== c.name) : [...f.preferred_categories, c.name] })}>{c.name}</button>;
            })}
          </div>
        </fieldset>
        <div className="row-end span-2"><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-primary">Save</button></div>
      </form>
    </Modal>
  );
}

export default function Members() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [status, setStatus] = useState('');
  const [role, setRole] = useState('member');
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  useEffect(() => { const t = setTimeout(() => { setDebounced(q); setPage(1); }, 250); return () => clearTimeout(t); }, [q]);
  const { data, error, loading, reload } = useLoad(
    () => api.get<Page<MemberSummary>>('/members', { params: { q: debounced, status: status || undefined, role, page, size: 20 } }).then((r) => r.data),
    [debounced, status, role, page],
  );
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <div className="page-head">
        <div><h1>Members</h1><p className="muted">Library patrons, their plans and account standing.</p></div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}>+ Register member</button>
      </div>
      <div className="toolbar">
        <input className="search" type="search" placeholder="Search name, email, phone or member code…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Status">
          <option value="">Any status</option><option value="active">Active</option><option value="expired">Membership expired</option>
          <option value="overdue">Has overdue books</option><option value="fines">Has unpaid fines</option><option value="inactive">Deactivated</option>
        </select>
        {isAdmin && (
          <select value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} aria-label="Role">
            <option value="member">Members</option><option value="librarian">Librarians</option><option value="admin">Admins</option><option value="all">Everyone</option>
          </select>
        )}
      </div>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && data.items.length === 0 && <Empty icon="👥" title="No members found" />}
      {data && data.items.length > 0 && (
        <div className="card flush table-wrap">
          <table>
            <thead><tr><th>Member</th><th>Plan</th><th>Expires</th><th className="num">On loan</th><th className="num">Overdue</th><th className="num">Unpaid</th><th>Status</th></tr></thead>
            <tbody>
              {data.items.map((m) => (
                <tr key={m.id} className="clickable" onClick={() => navigate(`/members/${m.id}`)}>
                  <td><Link to={`/members/${m.id}`}>{m.name}</Link><small className="block muted"><span className="mono">{m.member_code}</span> · {m.email}</small></td>
                  <td>{m.membership_type?.name ?? '—'}</td>
                  <td className={m.membership_expiry && m.membership_expiry < today ? 'text-bad' : ''}>{fmtDate(m.membership_expiry)}</td>
                  <td className="num">{m.active_loans}</td>
                  <td className="num">{m.overdue_loans ? <span className="text-bad">{m.overdue_loans}</span> : 0}</td>
                  <td className="num">{m.unpaid_fines ? <span className="text-bad">{money(m.unpaid_fines)}</span> : '—'}</td>
                  <td>{!m.is_active ? <Badge status="inactive" /> : m.membership_expiry && m.membership_expiry < today ? <Badge status="expired" /> : m.role !== 'member' ? <Badge status={m.role} /> : <Badge status="available" label="active" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} size={data.size} total={data.total} onPage={setPage} />}
      {adding && <MemberForm onClose={() => setAdding(false)} onSaved={(u) => navigate(`/members/${u.id}`)} />}
    </>
  );
}
