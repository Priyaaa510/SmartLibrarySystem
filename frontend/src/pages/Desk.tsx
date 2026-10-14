import { FormEvent, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, BookSummary, Loan, MemberDetail, MemberSummary, Page, ReturnResult } from '../api';
import { Badge, Cover, fmtDate, money, useToast } from '../components/ui';

function useDebounced<T>(value: T, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

function IssuePanel({ onIssued }: { onIssued: (l: Loan) => void }) {
  const toast = useToast();
  const [params] = useSearchParams();
  const [memberQ, setMemberQ] = useState('');
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [member, setMember] = useState<MemberDetail | null>(null);
  const [bookQ, setBookQ] = useState('');
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [book, setBook] = useState<BookSummary | null>(null);
  const [barcode, setBarcode] = useState('');
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const mq = useDebounced(memberQ);
  const bq = useDebounced(bookQ);

  useEffect(() => {
    const id = params.get('book');
    if (id) api.get<BookSummary>(`/books/${id}`).then((r) => setBook(r.data));
    const m = params.get('member');
    if (m) pickMember(Number(m));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!mq.trim() || !memberQ.trim() || member) return setMembers([]);
    api.get<Page<MemberSummary>>('/members', { params: { q: mq, role: 'all', size: 6 } }).then((r) => setMembers(r.data.items));
  }, [mq, memberQ, member]);
  useEffect(() => {
    if (!bq.trim() || !bookQ.trim() || book) return setBooks([]);
    api.get<Page<BookSummary>>('/books', { params: { q: bq, size: 6 } }).then((r) => setBooks(r.data.items));
  }, [bq, bookQ, book]);

  const pickMember = async (id: number) => {
    setMember((await api.get<MemberDetail>(`/members/${id}`)).data);
    setMembers([]);
  };

  const issue = async (e: FormEvent) => {
    e.preventDefault();
    if (!member) return toast.error('Select a member first');
    if (!barcode.trim() && !book) return toast.error('Scan a copy barcode or choose a book');
    setBusy(true);
    try {
      const r = await api.post<Loan>('/loans/checkout', {
        member: String(member.member.id),
        barcode: barcode.trim() || null,
        book_id: barcode.trim() ? null : book?.id,
        due_date: due || null,
      });
      toast.success(`Issued '${r.data.book_title}' (${r.data.barcode}) — due ${fmtDate(r.data.due_date)}`);
      onIssued(r.data);
      setBarcode(''); setBook(null); setBookQ(''); setDue('');
      pickMember(member.member.id);
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  const el = member?.eligibility;
  return (
    <form className="card desk-panel" onSubmit={issue}>
      <h2>📤 Issue a book</h2>
      <div className="step">
        <span className="step-n">1</span>
        <div className="grow">
          <strong>Member</strong>
          {member ? (
            <div className="picked">
              <div>
                <strong>{member.member.name}</strong> <span className="mono muted">{member.member.member_code}</span>
                <small className="block muted">{member.member.membership_type?.name} plan · expires {fmtDate(member.member.membership_expiry)}</small>
              </div>
              <button type="button" className="link" onClick={() => { setMember(null); setMemberQ(''); }}>Change</button>
            </div>
          ) : (
            <div className="combo">
              <input placeholder="Member code, name, email or phone…" value={memberQ} onChange={(e) => setMemberQ(e.target.value)} autoFocus />
              {members.length > 0 && (
                <ul className="combo-list">
                  {members.map((m) => (
                    <li key={m.id}><button type="button" onClick={() => pickMember(m.id)}>
                      <strong>{m.name}</strong> <span className="mono muted">{m.member_code}</span>
                      <small className="block muted">{m.email} · {m.active_loans} on loan{m.unpaid_fines > 0 && ` · ${money(m.unpaid_fines)} due`}</small>
                    </button></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {el && (
            <div className={`alert ${el.can_borrow ? 'alert-good' : 'alert-bad'}`}>
              {el.can_borrow
                ? <>✓ Can borrow — {el.active_loans}/{el.max_books} books on loan{el.unpaid_fines > 0 && `, ${money(el.unpaid_fines)} unpaid`}</>
                : <>✕ Cannot borrow: {el.reasons.join('; ')}. <Link to={`/members/${member!.member.id}`}>Open member</Link></>}
            </div>
          )}
          {member && member.reservations.filter((r) => r.status === 'ready').map((r) => (
            <div key={r.id} className="alert alert-warn">📌 Hold ready: <b>{r.book_title}</b> (copy {r.barcode}) <button type="button" className="link" onClick={() => setBarcode(r.barcode ?? '')}>Use this copy</button></div>
          ))}
        </div>
      </div>
      <div className="step">
        <span className="step-n">2</span>
        <div className="grow">
          <strong>Book</strong>
          <input className="mono" placeholder="Scan copy barcode (e.g. BK00018-001)" value={barcode} onChange={(e) => setBarcode(e.target.value)} />
          <span className="muted small or">— or pick a title (first available copy) —</span>
          {book ? (
            <div className="picked">
              <div className="with-cover"><Cover src={book.cover_url} title={book.title} size="sm" />
                <div><strong>{book.title}</strong><small className="block muted">{book.available_copies} available · shelf {book.shelf_location}</small></div></div>
              <button type="button" className="link" onClick={() => { setBook(null); setBookQ(''); }}>Change</button>
            </div>
          ) : (
            <div className="combo">
              <input placeholder="Search title, author or ISBN…" value={bookQ} onChange={(e) => setBookQ(e.target.value)} />
              {books.length > 0 && (
                <ul className="combo-list">
                  {books.map((b) => (
                    <li key={b.id}><button type="button" onClick={() => { setBook(b); setBooks([]); }}>
                      <strong>{b.title}</strong><small className="block muted">{b.author} · {b.available_copies}/{b.total_copies} available</small>
                    </button></li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="step">
        <span className="step-n">3</span>
        <div className="grow">
          <strong>Due date</strong>
          <input type="date" value={due} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setDue(e.target.value)} />
          <small className="muted">Leave empty to use the plan's loan period{member?.member.membership_type && ` (${member.member.membership_type.loan_days} days)`}.</small>
        </div>
      </div>
      <button className="btn btn-primary btn-block" disabled={busy || !member || (el ? !el.can_borrow : false)}>{busy ? 'Issuing…' : 'Issue book'}</button>
    </form>
  );
}

function ReturnPanel({ onReturned }: { onReturned: () => void }) {
  const toast = useToast();
  const [barcode, setBarcode] = useState('');
  const [damaged, setDamaged] = useState(false);
  const [fee, setFee] = useState('');
  const [notes, setNotes] = useState('');
  const [result, setResult] = useState<ReturnResult | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.post<ReturnResult>('/loans/checkin', {
        barcode, damaged, damage_fee: damaged && fee ? Number(fee) : null, notes: notes || null,
      });
      setResult(r.data);
      toast.success(`Returned '${r.data.loan.book_title}'`);
      setBarcode(''); setDamaged(false); setFee(''); setNotes('');
      onReturned();
    } catch (err) { toast.error(err); }
  };

  return (
    <form className="card desk-panel" onSubmit={submit}>
      <h2>📥 Return a book</h2>
      <input className="mono big-input" placeholder="Scan or type copy barcode" value={barcode} onChange={(e) => setBarcode(e.target.value)} required />
      <label className="check"><input type="checkbox" checked={damaged} onChange={(e) => setDamaged(e.target.checked)} /> Returned damaged</label>
      {damaged && (
        <div className="row">
          <input type="number" min={1} placeholder="Damage fee ₹" value={fee} onChange={(e) => setFee(e.target.value)} />
          <input placeholder="Notes (e.g. torn pages)" value={notes} onChange={(e) => setNotes(e.target.value)} className="grow" />
        </div>
      )}
      <button className="btn btn-primary btn-block">Check in</button>
      {result && (
        <div className="return-result">
          <div className="with-cover"><Cover src={result.loan.cover_url} title={result.loan.book_title} size="sm" />
            <div><strong>{result.loan.book_title}</strong><small className="block muted">from {result.loan.member_name} · {result.loan.overdue_days ? `${result.loan.overdue_days} day(s) late` : 'on time'}</small></div></div>
          {result.fines.map((f) => <div key={f.id} className="alert alert-warn">💰 {f.reason} fine of {money(f.amount)} charged — {f.note}</div>)}
          {result.hold_assigned_to
            ? <div className="alert alert-info">📌 Put this copy on the <b>hold shelf</b> for {result.hold_assigned_to}.</div>
            : <div className="alert alert-good">↩ Return the copy to the shelf.</div>}
        </div>
      )}
    </form>
  );
}

export default function Desk() {
  const [recent, setRecent] = useState<Loan[]>([]);
  const loadRecent = () => api.get<Page<Loan>>('/loans', { params: { status: 'active', size: 100 } })
    .then((r) => setRecent([...r.data.items].sort((a, b) => b.issued_at.localeCompare(a.issued_at)).slice(0, 8)));
  useEffect(() => { loadRecent(); }, []);

  return (
    <>
      <div className="page-head"><div><h1>Circulation Desk</h1><p className="muted">Issue and return books. Barcode scanners work in every barcode field.</p></div></div>
      <div className="desk">
        <IssuePanel onIssued={() => loadRecent()} />
        <ReturnPanel onReturned={() => loadRecent()} />
      </div>
      <section className="card">
        <h2>Latest loans</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Book</th><th>Copy</th><th>Member</th><th>Issued</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>
              {recent.map((l) => (
                <tr key={l.id}>
                  <td><Link to={`/books/${l.book_id}`}>{l.book_title}</Link></td>
                  <td className="mono">{l.barcode}</td>
                  <td><Link to={`/members/${l.member_id}`}>{l.member_name}</Link></td>
                  <td>{fmtDate(l.issued_at)}</td>
                  <td>{fmtDate(l.due_date)}</td>
                  <td>{l.is_overdue ? <Badge status="overdue" label={`${l.overdue_days}d overdue`} /> : <Badge status="active" label="on loan" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
