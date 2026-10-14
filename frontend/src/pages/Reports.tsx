import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Audit, BookSummary, CategoryStat, downloadCsv, MemberReport, Page, TrendPoint } from '../api';
import { BarList, LineChart } from '../components/charts';
import { fmtDateTime, Loading, money, Pagination, Stars, useLoad, useToast } from '../components/ui';
import { TREND_SERIES } from './Dashboard';

interface Perf {
  records_scanned: number; linear_seconds: number; dictionary_seconds: number; postgres_indexed_seconds: number;
  linear_complexity: string; dictionary_complexity: string; postgres_complexity: string;
}

const us = (s: number) => `${(s * 1e6).toLocaleString(undefined, { maximumFractionDigits: 1 })} µs`;

export default function Reports() {
  const toast = useToast();
  const [days, setDays] = useState(30);
  const [actPage, setActPage] = useState(1);
  const { data: trend } = useLoad(() => api.get<TrendPoint[]>('/reports/circulation', { params: { days } }).then((r) => r.data), [days]);
  const { data: cats } = useLoad(() => api.get<CategoryStat[]>('/reports/categories').then((r) => r.data), []);
  const { data: top } = useLoad(() => api.get<BookSummary[]>('/reports/top-books', { params: { limit: 10 } }).then((r) => r.data), []);
  const { data: members } = useLoad(() => api.get<MemberReport[]>('/reports/members').then((r) => r.data), []);
  const { data: activity } = useLoad(() => api.get<Page<Audit>>('/activity', { params: { page: actPage, size: 15 } }).then((r) => r.data), [actPage]);
  const [perf, setPerf] = useState<Perf | null>(null);

  const totals = trend?.reduce((a, d) => ({ issued: a.issued + d.issued, returned: a.returned + d.returned }), { issued: 0, returned: 0 });
  const exportCsv = async (kind: string) => { try { await downloadCsv(kind); } catch (e) { toast.error(e); } };

  return (
    <>
      <div className="page-head">
        <div><h1>Reports &amp; Analytics</h1><p className="muted">Circulation trends, collection usage and member activity.</p></div>
        <div className="row">
          <span className="muted small">Export CSV:</span>
          {['books', 'loans', 'overdue', 'fines', 'members'].map((k) => <button key={k} className="btn btn-sm" onClick={() => exportCsv(k)}>{k}</button>)}
        </div>
      </div>

      <div className="toolbar">
        <div className="seg" role="group" aria-label="Time range">
          {[7, 30, 90].map((n) => <button key={n} className={days === n ? 'on' : ''} onClick={() => setDays(n)}>{n} days</button>)}
        </div>
        {totals && <span className="muted">{totals.issued} issued · {totals.returned} returned in the last {days} days</span>}
      </div>

      <section className="card">
        {trend ? <LineChart title={`Daily circulation · last ${days} days`} data={trend as unknown as Record<string, number | string>[]} series={TREND_SERIES} /> : <Loading />}
      </section>

      <div className="grid-2">
        <section className="card">
          {cats ? <BarList title="Loans by category (all time)" data={cats.map((c) => ({ label: c.category, value: c.loans, sub: `${c.titles} titles` }))} /> : <Loading />}
        </section>
        <section className="card flush">
          <div className="card-head"><h2>Top 10 books</h2></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Title</th><th>Rating</th><th className="num">Loans</th></tr></thead>
              <tbody>{top?.map((b, i) => (
                <tr key={b.id}><td>{i + 1}</td><td><Link to={`/books/${b.id}`}>{b.title}</Link><small className="block muted">{b.category.name}</small></td><td><Stars value={b.avg_rating} /></td><td className="num">{b.times_borrowed}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="card flush">
        <div className="card-head"><h2>Member activity</h2><span className="muted small">Generated concurrently (thread pool, one DB session per worker)</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Member</th><th>Plan</th><th className="num">Loans</th><th className="num">Active</th><th className="num">Overdue</th><th className="num">Lost</th><th className="num">Fines (total)</th><th className="num">Unpaid</th></tr></thead>
            <tbody>{members?.map((m) => (
              <tr key={m.member_id}>
                <td><Link to={`/members/${m.member_id}`}>{m.member}</Link><small className="block muted mono">{m.member_code}</small></td>
                <td>{m.plan}</td><td className="num">{m.loans}</td><td className="num">{m.active}</td>
                <td className="num">{m.overdue ? <span className="text-bad">{m.overdue}</span> : 0}</td><td className="num">{m.lost}</td>
                <td className="num">{money(m.fines_total)}</td><td className="num">{m.fines_unpaid ? <span className="text-bad">{money(m.fines_unpaid)}</span> : '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>Search performance</h2>
          <p className="muted small">Why the catalog is indexed: finding one record by key with a linear scan, a hash map and PostgreSQL's B-tree index.</p>
          <button className="btn" onClick={async () => setPerf((await api.get<Perf>('/performance')).data)}>Run benchmark</button>
          {perf && (
            <table className="mt">
              <thead><tr><th>Method</th><th>Complexity</th><th className="num">Time</th></tr></thead>
              <tbody>
                <tr><td>Linear scan of {perf.records_scanned.toLocaleString()} keys</td><td>{perf.linear_complexity}</td><td className="num">{us(perf.linear_seconds)}</td></tr>
                <tr><td>Python dict lookup</td><td>{perf.dictionary_complexity}</td><td className="num">{us(perf.dictionary_seconds)}</td></tr>
                <tr><td>PostgreSQL indexed query</td><td>{perf.postgres_complexity}</td><td className="num">{us(perf.postgres_indexed_seconds)}</td></tr>
              </tbody>
            </table>
          )}
        </section>
        <section className="card flush">
          <div className="card-head"><h2>Audit log</h2></div>
          <ul className="list activity">
            {activity?.items.map((a) => (
              <li key={a.id}><div><strong>{a.actor}</strong> <span className="muted">{a.action}</span><small className="block muted">{a.entity} #{a.entity_id} {a.details}</small></div><small className="muted">{fmtDateTime(a.created_at)}</small></li>
            ))}
          </ul>
          {activity && <div className="pad"><Pagination page={actPage} size={activity.size} total={activity.total} onPage={setActPage} /></div>}
        </section>
      </div>
    </>
  );
}
