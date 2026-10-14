import { Link } from 'react-router-dom';
import { api, Fine, Loan, Reservation, ReturnResult } from '../api';
import { useAuth } from '../auth';
import { Badge, Cover, daysUntil, fmtDate, money, useConfirm, useToast } from './ui';

export function DueLabel({ loan }: { loan: Loan }) {
  if (loan.status !== 'active') return <Badge status={loan.status} />;
  if (loan.is_overdue) return <Badge status="overdue" label={`${loan.overdue_days}d overdue`} />;
  const d = daysUntil(loan.due_date);
  if (d === 0) return <Badge status="due_soon" label="due today" />;
  if (d <= 2) return <Badge status="due_soon" label={`due in ${d}d`} />;
  return <Badge status="active" label={`${d} days left`} />;
}

export function LoanTable({ loans, onChange, showMember = true }: { loans: Loan[]; onChange: () => void; showMember?: boolean }) {
  const { isStaff } = useAuth();
  const toast = useToast();
  const { confirm, dialog } = useConfirm();

  const act = async (loan: Loan, action: 'renew' | 'return' | 'lost') => {
    if (action === 'lost' && !(await confirm(`Mark '${loan.book_title}' as lost? The member will be charged the replacement cost.`))) return;
    try {
      const r = await api.post(`/loans/${loan.id}/${action}`);
      if (action === 'renew') toast.success(`Renewed — now due ${fmtDate((r.data as Loan).due_date)}`);
      else {
        const res = r.data as ReturnResult;
        const total = res.fines.reduce((s, f) => s + f.amount, 0);
        toast.success(`${action === 'lost' ? 'Marked lost' : 'Returned'}${total ? ` · ${money(total)} charged` : ''}${res.hold_assigned_to ? ` · hold shelf for ${res.hold_assigned_to}` : ''}`);
      }
      onChange();
    } catch (e) { toast.error(e); }
  };

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Book</th>{showMember && <th>Member</th>}<th>Issued</th><th>Due</th><th>Status</th><th className="num">Fine</th><th /></tr>
        </thead>
        <tbody>
          {loans.map((l) => (
            <tr key={l.id} className={l.is_overdue ? 'row-bad' : ''}>
              <td>
                <div className="with-cover"><Cover src={l.cover_url} title={l.book_title} size="sm" />
                  <div><Link to={`/books/${l.book_id}`}>{l.book_title}</Link><small className="block muted mono">{l.barcode}</small></div></div>
              </td>
              {showMember && <td>{isStaff ? <Link to={`/members/${l.member_id}`}>{l.member_name}</Link> : l.member_name}<small className="block muted mono">{l.member_code}</small></td>}
              <td>{fmtDate(l.issued_at)}</td>
              <td>{fmtDate(l.due_date)}{l.renew_count > 0 && <small className="block muted">renewed {l.renew_count}×</small>}</td>
              <td>{l.status === 'returned' ? <><Badge status="returned" /><small className="block muted">{fmtDate(l.returned_at)}</small></> : <DueLabel loan={l} />}</td>
              <td className="num">{l.accrued_fine ? <span className="text-bad">{money(l.accrued_fine)}</span> : '—'}</td>
              <td className="actions">
                {l.status === 'active' && (
                  <>
                    <button className="btn btn-sm" disabled={l.is_overdue || l.renew_count >= l.max_renewals}
                      title={l.renew_count >= l.max_renewals ? 'Renewal limit reached' : l.is_overdue ? 'Overdue items cannot be renewed' : ''}
                      onClick={() => act(l, 'renew')}>Renew</button>
                    {isStaff && <button className="btn btn-sm btn-primary" onClick={() => act(l, 'return')}>Return</button>}
                    {isStaff && <button className="btn btn-sm btn-danger-ghost" onClick={() => act(l, 'lost')}>Lost</button>}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {dialog}
    </div>
  );
}

export function HoldTable({ holds, onChange, showMember = true }: { holds: Reservation[]; onChange: () => void; showMember?: boolean }) {
  const { isStaff } = useAuth();
  const toast = useToast();
  const { confirm, dialog } = useConfirm();
  const cancel = async (h: Reservation) => {
    if (!(await confirm(`Cancel the hold on '${h.book_title}'?`))) return;
    try { await api.post(`/reservations/${h.id}/cancel`); toast.success('Hold cancelled'); onChange(); } catch (e) { toast.error(e); }
  };
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Book</th>{showMember && <th>Member</th>}<th>Placed</th><th>Status</th><th>Details</th><th /></tr></thead>
        <tbody>
          {holds.map((h) => (
            <tr key={h.id}>
              <td><Link to={`/books/${h.book_id}`}>{h.book_title}</Link><small className="block muted">{h.book_author}</small></td>
              {showMember && <td>{isStaff ? <Link to={`/members/${h.member_id}`}>{h.member_name}</Link> : h.member_name}</td>}
              <td>{fmtDate(h.created_at)}</td>
              <td><Badge status={h.status} label={h.status === 'ready' ? 'ready for pickup' : h.status} /></td>
              <td className="small">
                {h.status === 'waiting' && <>#{h.queue_position} in queue</>}
                {h.status === 'ready' && <>Copy <span className="mono">{h.barcode}</span> · collect by <b>{fmtDate(h.expires_on)}</b></>}
                {!['waiting', 'ready'].includes(h.status) && fmtDate(h.closed_at)}
              </td>
              <td className="actions">
                {['waiting', 'ready'].includes(h.status) && <button className="btn btn-sm btn-danger-ghost" onClick={() => cancel(h)}>Cancel</button>}
                {isStaff && h.status === 'ready' && <Link className="btn btn-sm btn-primary" to={`/desk?member=${h.member_id}`}>Issue</Link>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {dialog}
    </div>
  );
}

export function FineTable({ fines, onChange, showMember = true }: { fines: Fine[]; onChange: () => void; showMember?: boolean }) {
  const { isStaff } = useAuth();
  const toast = useToast();
  const { confirm, dialog } = useConfirm();
  const settle = async (f: Fine, action: 'pay' | 'waive') => {
    const msg = action === 'pay'
      ? (isStaff ? `Record a payment of ${money(f.amount)} from ${f.member_name}?` : `Pay ${money(f.amount)} now? (demo payment — no card is charged)`)
      : `Waive the ${money(f.amount)} fine for ${f.member_name}?`;
    if (!(await confirm(msg))) return;
    try { await api.post(`/fines/${f.id}/${action}`); toast.success(action === 'pay' ? 'Payment recorded' : 'Fine waived'); onChange(); } catch (e) { toast.error(e); }
  };
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{showMember && <th>Member</th>}<th>Reason</th><th>Book</th><th>Date</th><th className="num">Amount</th><th>Status</th><th /></tr></thead>
        <tbody>
          {fines.map((f) => (
            <tr key={f.id}>
              {showMember && <td>{isStaff ? <Link to={`/members/${f.member_id}`}>{f.member_name}</Link> : f.member_name}</td>}
              <td className="cap">{f.reason}{f.note && <small className="block muted">{f.note}</small>}</td>
              <td>{f.book_title ?? '—'}</td>
              <td>{fmtDate(f.created_at)}</td>
              <td className="num"><strong>{money(f.amount)}</strong></td>
              <td><Badge status={f.status} />{f.settled_at && <small className="block muted">{fmtDate(f.settled_at)}</small>}</td>
              <td className="actions">
                {f.status === 'unpaid' && (
                  <>
                    <button className="btn btn-sm btn-primary" onClick={() => settle(f, 'pay')}>{isStaff ? 'Record payment' : 'Pay now'}</button>
                    {isStaff && <button className="btn btn-sm btn-ghost" onClick={() => settle(f, 'waive')}>Waive</button>}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {dialog}
    </div>
  );
}
