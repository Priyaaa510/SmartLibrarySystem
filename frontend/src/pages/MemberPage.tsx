import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, BookSummary, MemberDetail } from '../api';
import { useAuth } from '../auth';
import BookCard from '../components/BookCard';
import { FineTable, HoldTable, LoanTable } from '../components/LoanTable';
import { Badge, ErrorBox, fmtDate, Loading, money, Stat, useConfirm, useLoad, useToast } from '../components/ui';
import { MemberForm } from './Members';

export default function MemberPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const { confirm, dialog } = useConfirm();
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState<'loans' | 'history' | 'holds' | 'fines' | 'recs'>('loans');
  const { data, error, reload } = useLoad(() => api.get<MemberDetail>(`/members/${id}`).then((r) => r.data), [id]);
  const { data: recs } = useLoad(() => api.get<BookSummary[]>('/recommendations', { params: { member_id: id, limit: 6 } }).then((r) => r.data), [id]);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const m = data.member;
  const el = data.eligibility;
  const active = data.loans.filter((l) => l.status === 'active');
  const history = data.loans.filter((l) => l.status !== 'active');
  const expired = m.membership_expiry && m.membership_expiry < new Date().toISOString().slice(0, 10);
  const unpaid = data.fines.filter((f) => f.status === 'unpaid');

  const renew = async () => {
    try { const r = await api.post(`/members/${m.id}/renew-membership`); toast.success(`Membership extended to ${fmtDate(r.data.membership_expiry)}`); reload(); } catch (e) { toast.error(e); }
  };
  const toggle = async () => {
    if (m.is_active) {
      if (!(await confirm(`Deactivate ${m.name}? They will no longer be able to sign in or borrow.`))) return;
      try { await api.delete(`/members/${m.id}`); toast.success('Member deactivated'); reload(); } catch (e) { toast.error(e); }
    } else {
      try { await api.put(`/members/${m.id}`, { is_active: true }); toast.success('Member reactivated'); reload(); } catch (e) { toast.error(e); }
    }
  };

  return (
    <>
      <p className="crumbs"><Link to="/members">Members</Link> › {m.name}</p>
      <div className="card member-head">
        <span className="avatar avatar-lg" aria-hidden>{m.name.split(' ').map((w) => w[0]).slice(0, 2).join('')}</span>
        <div className="grow">
          <h1>{m.name} {!m.is_active && <Badge status="inactive" />} {m.role !== 'member' && <Badge status={m.role} />}</h1>
          <p className="muted"><span className="mono">{m.member_code}</span> · {m.email}{m.phone && ` · ${m.phone}`}</p>
          <p className="small">
            <b>{m.membership_type?.name ?? 'No'} plan</b>
            {m.membership_type && ` · ${m.membership_type.max_books} books · ${m.membership_type.loan_days}-day loans · ${money(m.membership_type.fine_per_day)}/day fine`}
            {' · '}<span className={expired ? 'text-bad' : ''}>{expired ? 'Expired' : 'Valid until'} {fmtDate(m.membership_expiry)}</span>
          </p>
          {m.preferred_categories.length > 0 && <div className="chips">{m.preferred_categories.map((c) => <span key={c} className="chip static">{c}</span>)}</div>}
        </div>
        <div className="col-actions">
          <Link className={`btn btn-primary ${!el.can_borrow ? 'disabled' : ''}`} to={`/desk?member=${m.id}`}>Issue book</Link>
          <button className="btn" onClick={() => setEditing(true)}>Edit</button>
          <button className="btn" onClick={renew}>Renew membership</button>
          {m.id !== user?.id && <button className={`btn ${m.is_active ? 'btn-danger-ghost' : ''}`} onClick={toggle}>{m.is_active ? 'Deactivate' : 'Reactivate'}</button>}
        </div>
      </div>

      <div className={`alert ${el.can_borrow ? 'alert-good' : 'alert-bad'}`}>
        {el.can_borrow ? '✓ In good standing — can borrow books.' : `✕ Borrowing blocked: ${el.reasons.join('; ')}`}
      </div>

      <div className="stats">
        <Stat label="On loan" value={`${el.active_loans} / ${el.max_books}`} />
        <Stat label="Overdue" value={active.filter((l) => l.is_overdue).length} tone={active.some((l) => l.is_overdue) ? 'bad' : undefined} />
        <Stat label="Unpaid fines" value={money(el.unpaid_fines)} tone={el.unpaid_fines ? 'warn' : undefined} />
        <Stat label="Total borrowed" value={data.loans.length} />
      </div>

      <div className="tabs tabs-line" role="tablist">
        {([['loans', `On loan (${active.length})`], ['history', `History (${history.length})`], ['holds', `Holds (${data.reservations.length})`], ['fines', `Fines (${unpaid.length} unpaid)`], ['recs', 'Recommendations']] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div className="card flush">
        {tab === 'loans' && (active.length ? <LoanTable loans={active} onChange={reload} showMember={false} /> : <p className="pad muted">Nothing on loan.</p>)}
        {tab === 'history' && (history.length ? <LoanTable loans={history} onChange={reload} showMember={false} /> : <p className="pad muted">No history yet.</p>)}
        {tab === 'holds' && (data.reservations.length ? <HoldTable holds={data.reservations} onChange={reload} showMember={false} /> : <p className="pad muted">No holds.</p>)}
        {tab === 'fines' && (data.fines.length ? <FineTable fines={data.fines} onChange={reload} showMember={false} /> : <p className="pad muted">No fines.</p>)}
        {tab === 'recs' && <div className="book-grid pad">{recs?.map((b) => <BookCard key={b.id} book={b} />)}</div>}
      </div>
      {editing && <MemberForm member={m} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload(); }} />}
      {dialog}
    </>
  );
}
