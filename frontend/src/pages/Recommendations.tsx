import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, BookSummary } from '../api';
import { useAuth } from '../auth';
import BookCard from '../components/BookCard';
import { Empty, Loading, useLoad } from '../components/ui';

export default function Recommendations() {
  const { user } = useAuth();
  const [strategy, setStrategy] = useState('hybrid');
  const { data: strategies } = useLoad(() => api.get<{ name: string; description: string }[]>('/recommendations/strategies').then((r) => r.data), []);
  const { data, loading } = useLoad(() => api.get<BookSummary[]>('/recommendations', { params: { strategy, limit: 16 } }).then((r) => r.data), [strategy]);
  const current = strategies?.find((s) => s.name === strategy);

  return (
    <>
      <div className="page-head"><div><h1>Recommended for you</h1><p className="muted">{current?.description}</p></div></div>
      <div className="seg seg-wide" role="group" aria-label="Recommendation strategy">
        {strategies?.map((s) => <button key={s.name} className={strategy === s.name ? 'on' : ''} onClick={() => setStrategy(s.name)}>{s.name === 'hybrid' ? 'Best picks' : s.name === 'category' ? 'My interests' : s.name === 'history' ? 'Based on history' : 'Popular'}</button>)}
      </div>
      {loading && !data && <Loading />}
      {data && data.length === 0 && (
        <Empty icon="✨" title="Nothing to recommend yet">
          {strategy === 'category' && (user?.preferred_categories.length ? 'You have read everything in your interests!' : <>Add some interests on your <Link to="/profile">profile</Link>.</>)}
          {strategy === 'history' && 'Borrow a few books and we will suggest similar ones.'}
        </Empty>
      )}
      {data && data.length > 0 && <div className={`book-grid ${loading ? 'fading' : ''}`}>{data.map((b) => <BookCard key={b.id} book={b} />)}</div>}
    </>
  );
}
