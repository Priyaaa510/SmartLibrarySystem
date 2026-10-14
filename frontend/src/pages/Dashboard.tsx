import { Link } from 'react-router-dom';
import { api, Audit, BookSummary, Dashboard as D, Loan, Page, Reservation, TrendPoint } from '../api';
import { useAuth } from '../auth';
import { LineChart } from '../components/charts';
import { Cover, ErrorBox, fmtDate, fmtDateTime, Loading, money, Stat, useLoad, useToast } from '../components/ui';

export const TREND_SERIES = [
  { key: 'issued', label: 'Issued', color: 'var(--series-1)' },
  { key: 'returned', label: 'Returned', color: 'var(--series-2)' },
];

export default function Dashboard() {
  const { user } = useAuth();
  const toast = useToast();
  const { data: d, error, reload } = useLoad(() => api.get<D>('/reports/dashboard').then((r) => r.data), []);
  const { data: trend } = useLoad(() => api.get<TrendPoint[]>('/reports/circulation', { params: { days: 30 } }).then((r) => r.data), []);
  const { data: overdue } = useLoad(() => api.get<Loan[]>('/reports/overdue').then((r) => r.data), []);
  const { data: ready } = useLoad(() => api.get<Page<Reservation>>('/reservations', { params: { status: 'ready', size: 5 } }).then((r) => r.data.items), []);
  const { data: top } = useLoad(() => api.get<BookSummary[]>('/reports/top-books', { params: { limit: 5 } }).then((r) => r.data), []);
  const { data: activity } = useLoad(() => api.get<Page<Audit>>('/activity', { params: { size: 8 } }).then((r) => r.data.items), []);

  const runJobs = async () => {
    try {
      const r = await api.post('/admin/run-daily-jobs');
      toast.success(`Daily jobs done: ${r.data.expired_holds} holds expired, ${r.data.due_soon_notices} due-soon and ${r.data.overdue_notices} overdue reminders sent`);
      reload();
    } catch (e) { toast.error(e); }
  };

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!d) return <Loading />;

  return (
    <>
      <div className="page-head">
        <div><h1>Good {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, {user?.name.split(' ')[0]}</h1>
          <p className="muted">Here's what is happening in the library today, {fmtDate(new Date().toISOString())}.</p></div>
        <div className="row">
          <button className="btn" onClick={runJobs} title="Expire uncollected holds and send reminders">Run daily jobs</button>
          <Link className="btn btn-primary" to="/desk">Open circulation desk</Link>
        </div>
      </div>

      <div className="stats">
        <Stat label="Books on loan" value={d.active_loans} hint={`${d.issued_today} issued today`} />
        <Stat label="Overdue" value={d.overdue_loans} hint={`${d.due_today} due today`} tone={d.overdue_loans ? 'bad' : undefined} />
        <Stat label="Holds" value={d.holds_waiting} hint={`${d.holds_ready} on the hold shelf`} tone={d.holds_ready ? 'warn' : undefined} />
        <Stat label="Fines outstanding" value={money(d.fines_outstanding)} hint={`${money(d.fines_collected)} collected`} />
        <Stat label="Collection" value={d.titles} hint={`${d.copies} copies · ${d.copies_by_status.available ?? 0} on shelf`} />
        <Stat label="Members" value={d.active_members} hint={`${d.members - d.active_members} inactive/expired`} />
      </div>

      <div className="grid-2">
        <section className="card span-2">
          {trend ? <LineChart title="Circulation · last 30 days" data={trend as unknown as Record<string, number | string>[]} series={TREND_SERIES} /> : <Loading />}
        </section>

        <section className="card flush">
          <div className="card-head"><h2>Overdue ({overdue?.length ?? 0})</h2><Link to="/loans?status=overdue">All loans →</Link></div>
          {overdue && overdue.length === 0 && <p className="pad muted">No overdue books 🎉</p>}
          <ul className="list">
            {overdue?.slice(0, 6).map((l) => (
              <li key={l.id}>
                <div><Link to={`/members/${l.member_id}`}><strong>{l.member_name}</strong></Link><small className="block muted">{l.book_title} · <span className="mono">{l.barcode}</span></small></div>
                <div className="right"><span className="text-bad">{l.overdue_days}d late</span><small className="block muted">{money(l.accrued_fine)}</small></div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card flush">
          <div className="card-head"><h2>Hold shelf</h2><Link to="/holds">All holds →</Link></div>
          {ready && ready.length === 0 && <p className="pad muted">Nothing waiting for pickup.</p>}
          <ul className="list">
            {ready?.map((r) => (
              <li key={r.id}>
                <div><strong>{r.book_title}</strong><small className="block muted">for {r.member_name} · <span className="mono">{r.barcode}</span></small></div>
                <div className="right"><small className="muted">collect by</small><small className="block">{fmtDate(r.expires_on)}</small></div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card flush">
          <div className="card-head"><h2>Most borrowed</h2><Link to="/reports">Reports →</Link></div>
          <ul className="list">
            {top?.map((b, i) => (
              <li key={b.id}>
                <div className="with-cover"><span className="rank">{i + 1}</span><Cover src={b.cover_url} title={b.title} size="sm" />
                  <div><Link to={`/books/${b.id}`}>{b.title}</Link><small className="block muted">{b.author}</small></div></div>
                <span className="muted small">{b.times_borrowed} loans</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card flush">
          <div className="card-head"><h2>Recent activity</h2></div>
          {activity && activity.length === 0 && <p className="pad muted">No activity recorded yet.</p>}
          <ul className="list activity">
            {activity?.map((a) => (
              <li key={a.id}><div><strong>{a.actor}</strong> <span className="muted">{a.action.replace('.', ' · ')}</span><small className="block muted">{a.details}</small></div><small className="muted">{fmtDateTime(a.created_at)}</small></li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
