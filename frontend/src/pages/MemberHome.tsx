import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, BookSummary, MySummary } from '../api';
import BookCard from '../components/BookCard';
import { HoldTable, LoanTable } from '../components/LoanTable';
import { ErrorBox, fmtDate, Loading, money, Stat, useLoad } from '../components/ui';

export default function MemberHome() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const { data, error, reload } = useLoad(() => api.get<MySummary>('/me/summary').then((r) => r.data), []);
  const { data: recs } = useLoad(() => api.get<BookSummary[]>('/recommendations', { params: { limit: 6 } }).then((r) => r.data), []);
  const { data: popular } = useLoad(() => api.get<{ items: BookSummary[] }>('/books', { params: { sort: 'newest', size: 6 } }).then((r) => r.data.items), []);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const el = data.eligibility;
  const overdue = data.active_loans.filter((l) => l.is_overdue);
  const ready = data.reservations.filter((r) => r.status === 'ready');
  const owed = data.unpaid_fines.reduce((s, f) => s + f.amount, 0) + data.active_loans.reduce((s, l) => s + l.accrued_fine, 0);

  return (
    <>
      <div className="welcome card">
        <div>
          <h1>Hello, {data.user.name.split(' ')[0]} 👋</h1>
          <p className="muted">Member <span className="mono">{data.user.member_code}</span> · {data.user.membership_type?.name} plan · valid until {fmtDate(data.user.membership_expiry)}</p>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); navigate(`/catalog?q=${encodeURIComponent(q)}`); }} className="welcome-search">
          <input type="search" placeholder="Search the catalog…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the catalog" />
          <button className="btn btn-primary">Search</button>
        </form>
      </div>

      {ready.map((r) => <div key={r.id} className="alert alert-good">📌 <b>{r.book_title}</b> is ready for pickup at the desk — collect it by {fmtDate(r.expires_on)}.</div>)}
      {overdue.length > 0 && <div className="alert alert-bad">⚠ You have {overdue.length} overdue book(s). Please return them — fines grow every day.</div>}
      {!el.can_borrow && overdue.length === 0 && <div className="alert alert-warn">Borrowing is paused: {el.reasons.join('; ')}</div>}

      <div className="stats">
        <Stat label="Books on loan" value={`${el.active_loans} / ${el.max_books}`} hint={`${data.user.membership_type?.loan_days ?? '—'}-day loan period`} />
        <Stat label="Holds" value={data.reservations.length} hint={ready.length ? `${ready.length} ready for pickup` : 'in queue'} tone={ready.length ? 'good' : undefined} />
        <Stat label="Fines owed" value={money(owed)} hint={<Link to="/fines">View &amp; pay</Link>} tone={owed ? 'warn' : undefined} />
        <Stat label="Books borrowed" value={data.total_borrowed} hint="all time" />
      </div>

      <section className="card flush">
        <div className="card-head"><h2>Currently borrowed</h2><Link to="/loans">History →</Link></div>
        {data.active_loans.length ? <LoanTable loans={data.active_loans} onChange={reload} showMember={false} /> : <p className="pad muted">You have no books on loan. <Link to="/catalog">Browse the catalog</Link>.</p>}
      </section>

      {data.reservations.length > 0 && (
        <section className="card flush">
          <div className="card-head"><h2>My holds</h2></div>
          <HoldTable holds={data.reservations} onChange={reload} showMember={false} />
        </section>
      )}

      {recs && recs.length > 0 && (
        <section>
          <div className="card-head bare"><h2>Recommended for you</h2><Link to="/recommendations">More →</Link></div>
          <div className="book-grid">{recs.map((b) => <BookCard key={b.id} book={b} />)}</div>
        </section>
      )}
      {popular && (
        <section>
          <div className="card-head bare"><h2>New arrivals</h2><Link to="/catalog?sort=newest">See all →</Link></div>
          <div className="book-grid">{popular.map((b) => <BookCard key={b.id} book={b} />)}</div>
        </section>
      )}
    </>
  );
}
