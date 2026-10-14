import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { api, tokenStore, User } from './api';

interface AuthState {
  user: User | null;
  loading: boolean;
  isStaff: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: Record<string, unknown>) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) { setUser(null); setLoading(false); return; }
    try {
      setUser((await api.get<User>('/auth/me')).data);
    } catch {
      tokenStore.set(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onLogout = () => setUser(null);
    window.addEventListener('auth:logout', onLogout);
    return () => window.removeEventListener('auth:logout', onLogout);
  }, [refresh]);

  const accept = (data: { access_token: string; user: User }) => {
    tokenStore.set(data.access_token);
    setUser(data.user);
  };

  const value: AuthState = {
    user,
    loading,
    isStaff: user?.role === 'admin' || user?.role === 'librarian',
    isAdmin: user?.role === 'admin',
    login: async (email, password) => accept((await api.post('/auth/login', { email, password })).data),
    register: async (data) => accept((await api.post('/auth/register', data)).data),
    logout: () => { tokenStore.set(null); setUser(null); },
    refresh,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
