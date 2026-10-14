import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api, Notification } from '../api';
import { useAuth } from '../auth';
import { fmtDateTime } from './ui';

const STAFF_NAV = [
  ['/', '📊', 'Dashboard'],
  ['/desk', '🛎️', 'Circulation Desk'],
  ['/catalog', '📚', 'Catalog'],
  ['/loans', '📖', 'Loans'],
  ['/holds', '⏳', 'Holds'],
  ['/members', '👥', 'Members'],
  ['/fines', '💰', 'Fines'],
  ['/reports', '📈', 'Reports'],
  ['/settings', '⚙️', 'Settings'],
] as const;

const MEMBER_NAV = [
  ['/', '🏠', 'My Library'],
  ['/catalog', '📚', 'Catalog'],
  ['/recommendations', '✨', 'For You'],
  ['/loans', '📖', 'My Loans'],
  ['/holds', '⏳', 'My Holds'],
  ['/fines', '💰', 'My Fines'],
] as const;

function Bell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const location = useLocation();

  const load = async () => {
    try {
      const [n, c] = await Promise.all([
        api.get<Notification[]>('/notifications', { params: { limit: 15 } }),
        api.get<{ unread: number }>('/notifications/unread-count'),
      ]);
      setItems(n.data);
      setUnread(c.data.unread);
    } catch { /* non-critical */ }
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [location.pathname]);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const readAll = async () => { await api.post('/notifications/read-all'); load(); };
  const read = async (n: Notification) => { if (!n.is_read) { await api.post(`/notifications/${n.id}/read`); load(); } };

  return (
    <div className="bell" ref={ref}>
      <button className="icon-btn" aria-label={`Notifications (${unread} unread)`} onClick={() => setOpen(!open)}>
        🔔{unread > 0 && <span className="bell-count">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div className="bell-panel">
          <header><strong>Notifications</strong>{unread > 0 && <button className="link" onClick={readAll}>Mark all read</button>}</header>
          {items.length === 0 && <p className="muted pad">You're all caught up.</p>}
          <ul>
            {items.map((n) => (
              <li key={n.id} className={n.is_read ? '' : 'unread'} onClick={() => read(n)}>
                <strong>{n.title}</strong>
                <span>{n.message}</span>
                <small className="muted">{fmtDateTime(n.created_at)}</small>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, isStaff, logout } = useAuth();
  const [menu, setMenu] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => setMenu(false), [location.pathname]);
  const nav = isStaff ? STAFF_NAV : MEMBER_NAV;

  return (
    <div className={`app ${menu ? 'menu-open' : ''}`}>
      <aside className="sidebar">
        <div className="brand"><span aria-hidden>📚</span> Smart Library</div>
        <nav>
          {nav.map(([to, icon, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span aria-hidden>{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/profile" className={({ isActive }) => (isActive ? 'active' : '')}><span aria-hidden>👤</span>My Profile</NavLink>
          <button onClick={() => { logout(); navigate('/login'); }}><span aria-hidden>↩</span>Sign out</button>
        </div>
      </aside>
      <div className="scrim" onClick={() => setMenu(false)} />
      <div className="main-wrap">
        <header className="topbar">
          <button className="icon-btn menu-btn" aria-label="Menu" onClick={() => setMenu(!menu)}>☰</button>
          <div className="topbar-user">
            <span className="avatar" aria-hidden>{user?.name.split(' ').map((w) => w[0]).slice(0, 2).join('')}</span>
            <div>
              <strong>{user?.name}</strong>
              <small className="muted">{user?.member_code} · {user?.role}</small>
            </div>
          </div>
          <Bell />
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
