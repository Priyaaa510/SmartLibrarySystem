import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, BookSummary, Category, Page } from '../api';
import { useAuth } from '../auth';
import BookCard from '../components/BookCard';
import BookForm from '../components/BookForm';
import { Cover, Empty, ErrorBox, Loading, Pagination, Stars, useLoad } from '../components/ui';

export default function Catalog() {
  const { isStaff } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [adding, setAdding] = useState(false);
  const page = Number(params.get('page') ?? 1);
  const category = params.get('category_id') ?? '';
  const language = params.get('language') ?? '';
  const sort = params.get('sort') ?? 'title';
  const available = params.get('available_only') === 'true';

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!('page' in patch)) next.delete('page');
    setParams(next, { replace: true });
  };

  // debounce typing into the URL
  useEffect(() => {
    const t = setTimeout(() => { if ((params.get('q') ?? '') !== q) update({ q: q || null }); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const { data: cats } = useLoad(() => api.get<Category[]>('/categories').then((r) => r.data), []);
  const { data: langs } = useLoad(() => api.get<string[]>('/books/languages').then((r) => r.data), []);
  const { data, error, loading, reload } = useLoad(
    () => api.get<Page<BookSummary>>('/books', { params: { ...Object.fromEntries(params), size: 24 } }).then((r) => r.data),
    [params.toString()],
  );

  return (
    <>
      <div className="page-head">
        <div><h1>Catalog</h1><p className="muted">Search {data ? data.total : '…'} titles by title, author, ISBN, publisher or subject.</p></div>
        {isStaff && <button className="btn btn-primary" onClick={() => setAdding(true)}>+ Add book</button>}
      </div>

      <div className="toolbar">
        <input className="search" type="search" placeholder="Search books…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search books" />
        <select value={category} onChange={(e) => update({ category_id: e.target.value || null })} aria-label="Category">
          <option value="">All categories</option>
          {cats?.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.book_count})</option>)}
        </select>
        <select value={language} onChange={(e) => update({ language: e.target.value || null })} aria-label="Language">
          <option value="">Any language</option>
          {langs?.map((l) => <option key={l}>{l}</option>)}
        </select>
        <select value={sort} onChange={(e) => update({ sort: e.target.value })} aria-label="Sort by">
          <option value="title">Title A–Z</option>
          <option value="author">Author</option>
          <option value="newest">Recently added</option>
          <option value="year">Publication year</option>
          <option value="popular">Most borrowed</option>
          <option value="rating">Top rated</option>
        </select>
        <label className="check"><input type="checkbox" checked={available} onChange={(e) => update({ available_only: e.target.checked ? 'true' : null })} /> Available now</label>
        <div className="seg" role="group" aria-label="View">
          <button className={view === 'grid' ? 'on' : ''} onClick={() => setView('grid')} aria-label="Grid view">▦</button>
          <button className={view === 'list' ? 'on' : ''} onClick={() => setView('list')} aria-label="List view">☰</button>
        </div>
      </div>

      {error && <ErrorBox error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && data.items.length === 0 && <Empty icon="🔍" title="No books match your search">Try a different keyword or clear the filters.</Empty>}
      {data && data.items.length > 0 && (view === 'grid' ? (
        <div className={`book-grid ${loading ? 'fading' : ''}`}>{data.items.map((b) => <BookCard key={b.id} book={b} />)}</div>
      ) : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Title</th><th>Category</th><th>Shelf</th><th>Rating</th><th>Borrowed</th><th>Available</th></tr></thead>
            <tbody>
              {data.items.map((b) => (
                <tr key={b.id} className="clickable" onClick={() => navigate(`/books/${b.id}`)}>
                  <td><div className="with-cover"><Cover src={b.cover_url} title={b.title} size="sm" /><div><Link to={`/books/${b.id}`}>{b.title}</Link><small className="muted block">{b.author} · {b.isbn}</small></div></div></td>
                  <td>{b.category.name}</td>
                  <td>{b.shelf_location ?? '—'}</td>
                  <td><Stars value={b.avg_rating} /></td>
                  <td className="num">{b.times_borrowed}</td>
                  <td className="num"><span className={b.available_copies ? 'text-good' : 'text-bad'}>{b.available_copies}</span> / {b.total_copies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {data && <Pagination page={page} size={data.size} total={data.total} onPage={(p) => update({ page: String(p) })} />}

      {adding && <BookForm onClose={() => setAdding(false)} onSaved={(b) => navigate(`/books/${b.id}`)} />}
    </>
  );
}
