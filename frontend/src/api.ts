import axios, { AxiosError } from 'axios';

export const API_URL: string = import.meta.env.VITE_API_URL ?? '/api';
const TOKEN_KEY = 'smart-library-token';

export const api = axios.create({ baseURL: API_URL });

export const tokenStore = {
  get: (): string | null => {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (t: string | null) => {
    try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

api.interceptors.request.use((config) => {
  const t = tokenStore.get();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError) => {
    if (err.response?.status === 401 && tokenStore.get()) {
      tokenStore.set(null);
      window.dispatchEvent(new Event('auth:logout'));
    }
    return Promise.reject(err);
  },
);

/** Turn an API error into a readable message (handles FastAPI validation errors). */
export function errorMessage(err: unknown): string {
  const e = err as AxiosError<{ detail?: unknown }>;
  const detail = e.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) =>
        `${(d.loc ?? []).filter((x) => x !== 'body').join('.')}: ${d.msg}`)
      .join('; ');
  }
  return e.message || 'Something went wrong';
}

/** Download an authenticated CSV export. */
export async function downloadCsv(kind: string) {
  const r = await api.get(`/reports/export/${kind}.csv`, { responseType: 'blob' });
  const url = URL.createObjectURL(r.data as Blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${kind}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------- types
export interface Page<T> { items: T[]; total: number; page: number; size: number }

export interface Plan {
  id: number; name: string; description: string; max_books: number; loan_days: number;
  max_renewals: number; fine_per_day: number; max_unpaid_fine: number; validity_months: number;
}

export type Role = 'admin' | 'librarian' | 'member';

export interface User {
  id: number; member_code: string | null; name: string; email: string; role: Role;
  phone: string | null; address: string | null; membership_type: Plan | null;
  membership_expiry: string | null; preferred_categories: string[]; is_active: boolean;
  created_at: string;
}
export interface MemberSummary extends User { active_loans: number; overdue_loans: number; unpaid_fines: number }

export interface Category { id: number; name: string; description: string; book_count?: number }

export interface BookSummary {
  id: number; isbn: string; title: string; author: string; publisher: string | null;
  published_year: number | null; language: string; cover_url: string | null;
  shelf_location: string | null; category: Category; total_copies: number;
  available_copies: number; avg_rating: number | null; review_count: number; times_borrowed: number;
}
export interface Copy {
  id: number; book_id: number; barcode: string; status: string; condition: string;
  acquired_on: string | null; price: number | null; notes: string | null;
}
export interface Review { id: number; book_id: number; user_id: number; rating: number; comment: string; created_at: string; reviewer: string }
export interface BookDetail extends BookSummary {
  edition: string | null; pages: number | null; description: string | null; created_at: string;
  copies: Copy[]; holds_waiting: number; reviews: Review[];
}

export interface Loan {
  id: number; status: 'active' | 'returned' | 'lost'; issued_at: string; due_date: string;
  returned_at: string | null; renew_count: number; max_renewals: number; is_overdue: boolean;
  overdue_days: number; accrued_fine: number; member_id: number; member_name: string;
  member_code: string | null; copy_id: number; barcode: string; book_id: number;
  book_title: string; book_author: string; cover_url: string | null;
}
export interface Fine {
  id: number; member_id: number; member_name: string; loan_id: number | null; book_title: string | null;
  amount: number; reason: string; status: 'unpaid' | 'paid' | 'waived'; note: string | null;
  created_at: string; settled_at: string | null;
}
export interface ReturnResult { loan: Loan; fines: Fine[]; hold_assigned_to: string | null }
export interface Reservation {
  id: number; status: string; created_at: string; ready_at: string | null; expires_on: string | null;
  closed_at: string | null; queue_position: number | null; member_id: number; member_name: string;
  book_id: number; book_title: string; book_author: string; barcode: string | null;
}
export interface Eligibility { can_borrow: boolean; reasons: string[]; active_loans: number; max_books: number; unpaid_fines: number }
export interface MemberDetail { member: User; eligibility: Eligibility; loans: Loan[]; reservations: Reservation[]; fines: Fine[] }
export interface MySummary {
  user: User; eligibility: Eligibility; active_loans: Loan[]; reservations: Reservation[];
  unpaid_fines: Fine[]; total_borrowed: number; unread_notifications: number;
}
export interface Notification { id: number; kind: string; title: string; message: string; is_read: boolean; created_at: string }
export interface Audit { id: number; actor: string | null; action: string; entity: string; entity_id: number | null; details: string; created_at: string }

export interface Dashboard {
  titles: number; copies: number; copies_by_status: Record<string, number>; categories: number;
  members: number; active_members: number; active_loans: number; overdue_loans: number;
  due_today: number; issued_today: number; holds_waiting: number; holds_ready: number;
  fines_outstanding: number; fines_collected: number; fines_waived: number;
}
export interface TrendPoint { date: string; issued: number; returned: number }
export interface CategoryStat { category: string; titles: number; loans: number }
export interface MemberReport {
  member_id: number; member_code: string; member: string; plan: string | null; loans: number;
  active: number; returned: number; lost: number; overdue: number; fines_total: number; fines_unpaid: number;
}
