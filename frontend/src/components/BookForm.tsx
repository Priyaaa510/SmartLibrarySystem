import { FormEvent, useEffect, useState } from 'react';
import { api, BookDetail, Category } from '../api';
import { Field, Modal, useToast } from './ui';

const EMPTY = {
  isbn: '', title: '', author: '', publisher: '', published_year: '', edition: '', language: 'English',
  pages: '', description: '', cover_url: '', shelf_location: '', category_id: '', copies: '1', price: '',
};

export default function BookForm({ book, onClose, onSaved }: { book?: BookDetail; onClose: () => void; onSaved: (b: BookDetail) => void }) {
  const toast = useToast();
  const [cats, setCats] = useState<Category[]>([]);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState<Record<keyof typeof EMPTY, string>>(() =>
    book
      ? {
          ...EMPTY,
          ...Object.fromEntries(
            Object.keys(EMPTY).map((k) => [k, String((book as unknown as Record<string, unknown>)[k] ?? '')]),
          ),
          category_id: String(book.category.id),
        }
      : EMPTY,
  );
  useEffect(() => { api.get<Category[]>('/categories').then((r) => setCats(r.data)); }, []);

  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const num = (v: string) => (v.trim() === '' ? null : Number(v));
    const str = (v: string) => (v.trim() === '' ? null : v.trim());
    const payload: Record<string, unknown> = {
      isbn: f.isbn.trim(), title: f.title.trim(), author: f.author.trim(), publisher: str(f.publisher),
      published_year: num(f.published_year), edition: str(f.edition), language: f.language || 'English',
      pages: num(f.pages), description: str(f.description), cover_url: str(f.cover_url),
      shelf_location: str(f.shelf_location), category_id: Number(f.category_id),
    };
    try {
      let saved: BookDetail;
      if (book) saved = (await api.put<BookDetail>(`/books/${book.id}`, payload)).data;
      else saved = (await api.post<BookDetail>('/books', { ...payload, copies: Number(f.copies || 0), price: num(f.price) })).data;
      toast.success(book ? 'Book updated' : `'${saved.title}' added to the catalog`);
      onSaved(saved);
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={book ? 'Edit book' : 'Add a new book'} onClose={onClose} wide>
      <form onSubmit={submit} className="form-grid">
        <Field label="ISBN *"><input required value={f.isbn} onChange={set('isbn')} /></Field>
        <Field label="Category *">
          <select required value={f.category_id} onChange={set('category_id')}>
            <option value="">Select…</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Title *"><input required value={f.title} onChange={set('title')} /></Field>
        <Field label="Author(s) *"><input required value={f.author} onChange={set('author')} /></Field>
        <Field label="Publisher"><input value={f.publisher} onChange={set('publisher')} /></Field>
        <Field label="Year"><input type="number" min={1000} max={2100} value={f.published_year} onChange={set('published_year')} /></Field>
        <Field label="Edition"><input value={f.edition} onChange={set('edition')} /></Field>
        <Field label="Language"><input value={f.language} onChange={set('language')} /></Field>
        <Field label="Pages"><input type="number" min={1} value={f.pages} onChange={set('pages')} /></Field>
        <Field label="Shelf location" hint="e.g. PR-03"><input value={f.shelf_location} onChange={set('shelf_location')} /></Field>
        <Field label="Cover image URL" hint="Leave blank to use Open Library by ISBN">
          <input value={f.cover_url} onChange={set('cover_url')} placeholder={f.isbn ? `https://covers.openlibrary.org/b/isbn/${f.isbn}-M.jpg?default=false` : ''} />
        </Field>
        {!book && (
          <>
            <Field label="Number of copies"><input type="number" min={0} max={100} value={f.copies} onChange={set('copies')} /></Field>
            <Field label="Price per copy (₹)" hint="Used to charge for lost books"><input type="number" min={0} value={f.price} onChange={set('price')} /></Field>
          </>
        )}
        <Field label="Description"><textarea rows={3} value={f.description} onChange={set('description')} /></Field>
        <div className="row-end span-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}
