import { FormEvent, useState } from 'react';
import { api, Category, Plan } from '../api';
import { useAuth } from '../auth';
import { Field, Loading, Modal, money, useConfirm, useLoad, useToast } from '../components/ui';

const EMPTY_PLAN = { name: '', description: '', max_books: '3', loan_days: '14', max_renewals: '2', fine_per_day: '5', max_unpaid_fine: '200', validity_months: '12' };

function PlanForm({ plan, onClose, onSaved }: { plan?: Plan; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [f, setF] = useState<Record<keyof typeof EMPTY_PLAN, string>>(
    plan ? (Object.fromEntries(Object.keys(EMPTY_PLAN).map((k) => [k, String(plan[k as keyof Plan])])) as Record<keyof typeof EMPTY_PLAN, string>) : EMPTY_PLAN,
  );
  const set = (k: keyof typeof EMPTY_PLAN) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { ...f, max_books: +f.max_books, loan_days: +f.loan_days, max_renewals: +f.max_renewals, fine_per_day: +f.fine_per_day, max_unpaid_fine: +f.max_unpaid_fine, validity_months: +f.validity_months };
    try {
      if (plan) await api.put(`/membership-types/${plan.id}`, body); else await api.post('/membership-types', body);
      toast.success('Plan saved');
      onSaved();
    } catch (err) { toast.error(err); }
  };
  return (
    <Modal title={plan ? `Edit ${plan.name} plan` : 'New membership plan'} onClose={onClose} wide>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Name"><input required value={f.name} onChange={set('name')} /></Field>
        <Field label="Description"><input value={f.description} onChange={set('description')} /></Field>
        <Field label="Max books on loan"><input type="number" min={1} max={50} required value={f.max_books} onChange={set('max_books')} /></Field>
        <Field label="Loan period (days)"><input type="number" min={1} max={180} required value={f.loan_days} onChange={set('loan_days')} /></Field>
        <Field label="Renewals per loan"><input type="number" min={0} max={10} required value={f.max_renewals} onChange={set('max_renewals')} /></Field>
        <Field label="Fine per overdue day (₹)"><input type="number" min={0} step="0.5" required value={f.fine_per_day} onChange={set('fine_per_day')} /></Field>
        <Field label="Block borrowing above (₹ unpaid)"><input type="number" min={0} required value={f.max_unpaid_fine} onChange={set('max_unpaid_fine')} /></Field>
        <Field label="Validity (months)"><input type="number" min={1} max={120} required value={f.validity_months} onChange={set('validity_months')} /></Field>
        <div className="row-end span-2"><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-primary">Save</button></div>
      </form>
    </Modal>
  );
}

export default function Settings() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { confirm, dialog } = useConfirm();
  const { data: cats, reload: reloadCats } = useLoad(() => api.get<Category[]>('/categories').then((r) => r.data), []);
  const { data: plans, reload: reloadPlans } = useLoad(() => api.get<Plan[]>('/membership-types').then((r) => r.data), []);
  const [cat, setCat] = useState({ name: '', description: '' });
  const [editCat, setEditCat] = useState<Category | null>(null);
  const [plan, setPlan] = useState<Plan | 'new' | null>(null);

  const addCat = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post('/categories', cat); setCat({ name: '', description: '' }); toast.success('Category added'); reloadCats(); } catch (err) { toast.error(err); }
  };
  const saveCat = async (e: FormEvent) => {
    e.preventDefault();
    if (!editCat) return;
    try { await api.put(`/categories/${editCat.id}`, { name: editCat.name, description: editCat.description }); setEditCat(null); reloadCats(); } catch (err) { toast.error(err); }
  };
  const delCat = async (c: Category) => {
    if (!(await confirm(`Delete the '${c.name}' category?`))) return;
    try { await api.delete(`/categories/${c.id}`); toast.success('Category deleted'); reloadCats(); } catch (err) { toast.error(err); }
  };

  return (
    <>
      <div className="page-head"><div><h1>Settings</h1><p className="muted">Subjects and borrowing policies.</p></div></div>

      <section className="card flush">
        <div className="card-head"><h2>Membership plans &amp; borrowing rules</h2>{isAdmin && <button className="btn btn-sm btn-primary" onClick={() => setPlan('new')}>+ New plan</button>}</div>
        {!plans ? <Loading /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plan</th><th className="num">Max books</th><th className="num">Loan days</th><th className="num">Renewals</th><th className="num">Fine / day</th><th className="num">Block above</th><th className="num">Validity</th>{isAdmin && <th />}</tr></thead>
              <tbody>{plans.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong><small className="block muted">{p.description}</small></td>
                  <td className="num">{p.max_books}</td><td className="num">{p.loan_days}</td><td className="num">{p.max_renewals}</td>
                  <td className="num">{money(p.fine_per_day)}</td><td className="num">{money(p.max_unpaid_fine)}</td><td className="num">{p.validity_months} mo</td>
                  {isAdmin && <td className="actions"><button className="btn btn-sm" onClick={() => setPlan(p)}>Edit</button></td>}
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {!isAdmin && <p className="pad muted small">Only administrators can change borrowing rules.</p>}
      </section>

      <section className="card flush">
        <div className="card-head"><h2>Categories</h2></div>
        <form className="toolbar pad" onSubmit={addCat}>
          <input required placeholder="New category name" value={cat.name} onChange={(e) => setCat({ ...cat, name: e.target.value })} />
          <input className="grow" placeholder="Description" value={cat.description} onChange={(e) => setCat({ ...cat, description: e.target.value })} />
          <button className="btn btn-primary">Add</button>
        </form>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Description</th><th className="num">Books</th><th /></tr></thead>
            <tbody>{cats?.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.name}</strong></td><td className="muted">{c.description}</td><td className="num">{c.book_count}</td>
                <td className="actions"><button className="btn btn-sm" onClick={() => setEditCat(c)}>Edit</button><button className="btn btn-sm btn-danger-ghost" disabled={!!c.book_count} title={c.book_count ? 'Move its books first' : ''} onClick={() => delCat(c)}>Delete</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      {editCat && (
        <Modal title="Edit category" onClose={() => setEditCat(null)}>
          <form className="stack" onSubmit={saveCat}>
            <Field label="Name"><input required value={editCat.name} onChange={(e) => setEditCat({ ...editCat, name: e.target.value })} /></Field>
            <Field label="Description"><input value={editCat.description} onChange={(e) => setEditCat({ ...editCat, description: e.target.value })} /></Field>
            <div className="row-end"><button type="button" className="btn btn-ghost" onClick={() => setEditCat(null)}>Cancel</button><button className="btn btn-primary">Save</button></div>
          </form>
        </Modal>
      )}
      {plan && <PlanForm plan={plan === 'new' ? undefined : plan} onClose={() => setPlan(null)} onSaved={() => { setPlan(null); reloadPlans(); }} />}
      {dialog}
    </>
  );
}
