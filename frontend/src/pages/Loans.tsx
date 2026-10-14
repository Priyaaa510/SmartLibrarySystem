import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, Fine, Loan, Page, Reservation } from '../api';
import { useAuth } from '../auth';
import { FineTable, HoldTable, LoanTable } from '../components/LoanTable';
import { Empty, ErrorBox, Field, Loading, Modal, money, Pagination, useLoad, useToast } from '../components/ui';

function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="tabs tabs-line" role="tablist">
      {tabs.map(([k, label]) => <button key={k} role="tab" aria-selected={value === k} className={value === k ? 'on' : ''} onClick={() => onChange(k)}>{label}</button>)}
    </div>
  );
}

function useListPage<T>(path: string, status: string, q = '') {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [status, q]);
  const res = useLoad(
    () => api.get<Page<T>>(path, { params: { status: status === 'all' ? undefined : status, q: q || undefined, page, size: 20 } }).then((r) => r.data),
    [path, status, q, page],
  );
  return { ...res, page, setPage };
}

export default function Loans() {
  const { isStaff } = useAuth();
  const [params] = useSearchParams();
  const [status, setStatus] = useState(params.get('status') ?? 'active');
  const [q, setQ] = useState('');
  const { data, error, loading, reload, page, setPage } = useListPage<Loan>('/loans', status, q);
  return (
    <>
      <div className="page-head"><div><h1>{isStaff ? 'Loans' : 'My Loans'}</h1><p className="muted">{isStaff ? 'Every book currently or previously on loan.' : 'Books you have borrowed. Renew before the due date to avoid fines.'}</p></div></div>
      <Tabs value={status} onChange={setStatus} tabs={[['active', 'On loan'], ['overdue', 'Overdue'], ...(isStaff ? [['due_today', 'Due today'] as [string, string]] : []), ['returned', 'Returned'], ['lost', 'Lost'], ['all', 'All']]} />
      {isStaff && <input className="search" type="search" placeholder="Search by title, barcode, member name or code…" value={q} onChange={(e) => setQ(e.target.value)} />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && (data.items.length === 0
        ? <Empty icon="📖" title="No loans here" />
        : <div className="card flush"><LoanTable loans={data.items} onChange={reload} showMember={isStaff} /></div>)}
      {data && <Pagination page={page} size={data.size} total={data.total} onPage={setPage} />}
    </>
  );
}

export function Holds() {
  const { isStaff } = useAuth();
  const [status, setStatus] = useState('open');
  const { data, error, loading, reload, page, setPage } = useListPage<Reservation>('/reservations', status);
  return (
    <>
      <div className="page-head"><div><h1>{isStaff ? 'Holds & Reservations' : 'My Holds'}</h1>
        <p className="muted">When a reserved book is returned it is set aside on the hold shelf for the next member in the queue, who has 3 days to collect it.</p></div></div>
      <Tabs value={status} onChange={setStatus} tabs={[['open', 'Open'], ['ready', 'Ready for pickup'], ['waiting', 'Waiting'], ['fulfilled', 'Fulfilled'], ['expired', 'Expired'], ['cancelled', 'Cancelled']]} />
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && (data.items.length === 0
        ? <Empty icon="⏳" title="No holds">{!isStaff && 'Find a book that is checked out and click “Place hold”.'}</Empty>
        : <div className="card flush"><HoldTable holds={data.items} onChange={reload} showMember={isStaff} /></div>)}
      {data && <Pagination page={page} size={data.size} total={data.total} onPage={setPage} />}
    </>
  );
}

function NewFine({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ member_id: '', amount: '', reason: 'other', note: '' });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/fines', { member_id: Number(f.member_id), amount: Number(f.amount), reason: f.reason, note: f.note || null });
      toast.success('Charge added');
      onDone();
    } catch (err) { toast.error(err); }
  };
  return (
    <Modal title="Add a manual charge" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Member ID"><input required type="number" min={1} value={f.member_id} onChange={(e) => setF({ ...f, member_id: e.target.value })} /></Field>
        <Field label="Amount (₹)"><input required type="number" min={1} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label="Reason">
          <select value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })}>
            <option value="other">Other</option><option value="damaged">Damaged</option><option value="lost">Lost</option><option value="overdue">Overdue</option>
          </select>
        </Field>
        <Field label="Note"><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
        <div className="row-end"><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-primary">Add charge</button></div>
      </form>
    </Modal>
  );
}

export function Fines() {
  const { isStaff } = useAuth();
  const [status, setStatus] = useState('unpaid');
  const [adding, setAdding] = useState(false);
  const { data, error, loading, reload, page, setPage } = useListPage<Fine>('/fines', status);
  const pageTotal = data?.items.filter((f) => f.status === 'unpaid').reduce((s, f) => s + f.amount, 0) ?? 0;
  return (
    <>
      <div className="page-head">
        <div><h1>{isStaff ? 'Fines & Payments' : 'My Fines'}</h1><p className="muted">Overdue, damage and lost-book charges.</p></div>
        {isStaff && <button className="btn btn-primary" onClick={() => setAdding(true)}>+ Manual charge</button>}
      </div>
      <Tabs value={status} onChange={setStatus} tabs={[['unpaid', 'Unpaid'], ['paid', 'Paid'], ['waived', 'Waived'], ['all', 'All']]} />
      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {status === 'unpaid' && pageTotal > 0 && <p className="alert alert-warn">Outstanding on this page: <b>{money(pageTotal)}</b></p>}
      {data && (data.items.length === 0
        ? <Empty icon="🎉" title={status === 'unpaid' ? 'No outstanding fines' : 'Nothing here'} />
        : <div className="card flush"><FineTable fines={data.items} onChange={reload} showMember={isStaff} /></div>)}
      {data && <Pagination page={page} size={data.size} total={data.total} onPage={setPage} />}
      {adding && <NewFine onClose={() => setAdding(false)} onDone={() => { setAdding(false); reload(); }} />}
    </>
  );
}
