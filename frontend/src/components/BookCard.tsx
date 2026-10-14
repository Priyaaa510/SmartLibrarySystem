import { Link } from 'react-router-dom';
import { BookSummary } from '../api';
import { Cover, Stars } from './ui';

export default function BookCard({ book }: { book: BookSummary }) {
  const avail = book.available_copies;
  return (
    <Link to={`/books/${book.id}`} className="book-card">
      <Cover src={book.cover_url} title={book.title} />
      <div className="book-card-body">
        <strong className="clamp-2">{book.title}</strong>
        <span className="muted small clamp-1">{book.author}</span>
        <Stars value={book.avg_rating} count={book.review_count} />
        <span className={`avail ${avail > 0 ? 'avail-yes' : 'avail-no'}`}>
          {avail > 0 ? `${avail} of ${book.total_copies} available` : book.total_copies ? 'All copies out' : 'Not in circulation'}
        </span>
      </div>
    </Link>
  );
}
