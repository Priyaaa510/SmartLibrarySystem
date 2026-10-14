import { FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, BookDetail, BookSummary, Copy } from '../api';
import { useAuth } from '../auth';
import BookCard from '../components/BookCard';
import BookForm from '../components/BookForm';
import {
  Badge, Cover, Empty, ErrorBox, fmtDate, Loading, Modal, money, StarInput, Stars, useConfirm, useLoad, useToast,
} from '../components/ui';

const COPY_STATUSES = ['available', 'maintenance', 'damaged', 'lost', 'withdrawn'];

export default function BookPage() {
  const { id } = useParams();
  const { user, isStaff } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { confirm, dialog } = useConfirm();
  const [editing, setEditing] = useState(false);
  const [addCopies, setAddCopies] = useState(false);
  const [review, setReview] = useState({ rating: 0, comment: '' });

  const { data: book, error, reload } = useLoad(() => api.get<BookDetail>(`/books/${id}`).then((r) => r.data), [id]);
  const { data: similar } = useLoad(() => api.get<BookSummary[]>(`/books/${id}/similar`).then((r) => r.data), [id]);

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!book) return <Loading />;

  const myReview = book.reviews.find((r) => r.user_id === user?.id);

  const placeHold = async () => {
    try {
      const r = await api.post('/reservations', { book_id: book.id });
      toast.success(`Hold placed — you are #${r.data.queue_position} in the queue`);
      reload();
    } catch (e) { toast.error(e); }
  };

  const setCopyStatus = async (c: Copy, status: string) => {
    try {
      await api.patch(`/copies/${c.id}`, { status });
      toast.success(`${c.barcode} marked ${status}`);
      reload();
    } catch (e) { toast.error(e); }
  };

  const remove = async () => {
    if (!(await confirm(`Delete '${book.title}' and all its copies? This cannot be undone.`))) return;
    try { await api.delete(`/books/${book.id}`); toast.success('Book deleted'); navigate('/catalog'); } catch (e) { toast.error(e); }
  };

  const submitReview = async (e: FormEvent) => {
    e.preventDefault();
    if (!review.rating) return toast.error('Pick a star rating first');
    try {
      await api.post(`/books/${book.id}/reviews`, review);
      toast.success('Thanks for your review!');
      setReview({ rating: 0, comment: '' });
      reload();
    } catch (err) { toast.error(err); }
  };

  const deleteReview = async (rid: number) => {
    try { await api.delete(`/reviews/${rid}`); reload(); } catch (e) { toast.error(e); }
  };

  return (
    <>
      <p className="crumbs"><Link to="/catalog">Catalog</Link> › {book.category.name}</p>
      <div className="book-hero card">
        <Cover src={book.cover_url} title={book.title} size="lg" />
        <div className="book-info">
          <span className="eyebrow">{book.category.name}</span>
          <h1>{book.title}</h1>
          <p className="lead">by {book.author}</p>
          <Stars value={book.avg_rating} count={book.review_count} />
          {book.description && <p>{book.description}</p>}
          <dl className="meta">
            <div><dt>ISBN</dt><dd>{book.isbn}</dd></div>
            <div><dt>Publisher</dt><dd>{book.publisher ?? '—'}</dd></div>
            <div><dt>Year</dt><dd>{book.published_year ?? '—'}</dd></div>
            {book.edition && <div><dt>Edition</dt><dd>{book.edition}</dd></div>}
            <div><dt>Pages</dt><dd>{book.pages ?? '—'}</dd></div>
            <div><dt>Language</dt><dd>{book.language}</dd></div>
            <div><dt>Shelf</dt><dd>{book.shelf_location ?? '—'}</dd></div>
            <div><dt>Borrowed</dt><dd>{book.times_borrowed} times</dd></div>
          </dl>
          <div className="availability">
            <strong className={book.available_copies ? 'text-good' : 'text-bad'}>
              {book.available_copies ? `${book.available_copies} of ${book.total_copies} copies on the shelf` : 'All copies are currently out'}
            </strong>
            {book.holds_waiting > 0 && <span className="muted"> · {book.holds_waiting} waiting in the holds queue</span>}
          </div>
          <div className="row">
            {!isStaff && (book.available_copies > 0
              ? <span className="hint">📍 Collect it from shelf <b>{book.shelf_location ?? '—'}</b> and check it out at the desk.</span>
              : <button className="btn btn-primary" onClick={placeHold} disabled={!book.total_copies}>Place hold</button>)}
            {isStaff && (
              <>
                <Link className="btn btn-primary" to={`/desk?book=${book.id}`}>Issue this book</Link>
                <button className="btn" onClick={() => setEditing(true)}>Edit details</button>
                <button className="btn" onClick={() => setAddCopies(true)}>+ Add copies</button>
                <button className="btn btn-danger-ghost" onClick={remove}>Delete</button>
              </>
            )}
          </div>
        </div>
      </div>

      <section className="card">
        <h2>Copies ({book.copies.length})</h2>
        {book.copies.length === 0 ? <Empty title="No copies yet" /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Barcode</th><th>Status</th><th>Condition</th><th>Acquired</th><th>Price</th>{isStaff && <th>Change status</th>}</tr></thead>
              <tbody>
                {book.copies.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.barcode}</td>
                    <td><Badge status={c.status} />{c.notes && <small className="muted block">{c.notes}</small>}</td>
                    <td>{c.condition}</td>
                    <td>{fmtDate(c.acquired_on)}</td>
                    <td>{c.price != null ? money(c.price) : '—'}</td>
                    {isStaff && (
                      <td>
                        {['on_loan', 'on_hold'].includes(c.status) ? <span className="muted small">In circulation</span> : (
                          <select value={c.status} onChange={(e) => setCopyStatus(c, e.target.value)} aria-label={`Status of ${c.barcode}`}>
                            {COPY_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                          </select>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Reviews ({book.reviews.length})</h2>
        {!isStaff && (
          <form className="review-form" onSubmit={submitReview}>
            <strong>{myReview ? 'Update your review' : 'Write a review'}</strong>
            <StarInput value={review.rating || myReview?.rating || 0} onChange={(n) => setReview({ ...review, rating: n })} />
            <textarea rows={2} placeholder="What did you think? (only members who borrowed this book can review it)" value={review.comment} onChange={(e) => setReview({ ...review, comment: e.target.value })} />
            <button className="btn btn-primary btn-sm">Submit</button>
          </form>
        )}
        {book.reviews.length === 0 && <p className="muted">No reviews yet.</p>}
        <ul className="reviews">
          {book.reviews.map((r) => (
            <li key={r.id}>
              <div className="row-between">
                <span><strong>{r.reviewer}</strong> <Stars value={r.rating} /></span>
                <span className="muted small">{fmtDate(r.created_at)}
                  {(isStaff || r.user_id === user?.id) && <button className="link danger" onClick={() => deleteReview(r.id)}>Delete</button>}
                </span>
              </div>
              {r.comment && <p>{r.comment}</p>}
            </li>
          ))}
        </ul>
      </section>

      {similar && similar.length > 0 && (
        <section>
          <h2>You might also like</h2>
          <div className="book-grid">{similar.map((b) => <BookCard key={b.id} book={b} />)}</div>
        </section>
      )}

      {editing && <BookForm book={book} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload(); }} />}
      {addCopies && <AddCopies bookId={book.id} onClose={() => setAddCopies(false)} onDone={() => { setAddCopies(false); reload(); }} />}
      {dialog}
    </>
  );
}

function AddCopies({ bookId, onClose, onDone }: { bookId: number; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [count, setCount] = useState('1');
  const [price, setPrice] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.post(`/books/${bookId}/copies`, { count: Number(count), price: price ? Number(price) : null });
      toast.success(`Added ${r.data.length} copies`);
      onDone();
    } catch (err) { toast.error(err); }
  };
  return (
    <Modal title="Add copies" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label className="field"><span>Number of copies</span><input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} /></label>
        <label className="field"><span>Price per copy (₹)</span><input type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <p className="muted small">Barcodes are generated automatically. New copies go to the first member in the holds queue.</p>
        <div className="row-end"><button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-primary">Add</button></div>
      </form>
    </Modal>
  );
}
