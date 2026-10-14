import { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import Layout from './components/Layout';
import { Loading, ToastProvider } from './components/ui';
import BookPage from './pages/BookPage';
import Catalog from './pages/Catalog';
import Dashboard from './pages/Dashboard';
import Desk from './pages/Desk';
import Fines from './pages/Fines';
import Holds from './pages/Holds';
import Loans from './pages/Loans';
import Login from './pages/Login';
import MemberHome from './pages/MemberHome';
import MemberPage from './pages/MemberPage';
import Members from './pages/Members';
import Profile from './pages/Profile';
import Recommendations from './pages/Recommendations';
import Reports from './pages/Reports';
import Settings from './pages/Settings';

function Protected({ children, staff }: { children: ReactNode; staff?: boolean }) {
  const { user, loading, isStaff } = useAuth();
  if (loading) return <div className="center-screen"><Loading /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (staff && !isStaff) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function Home() {
  const { isStaff } = useAuth();
  return isStaff ? <Dashboard /> : <MemberHome />;
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route index element={<Home />} />
              <Route path="catalog" element={<Catalog />} />
              <Route path="books/:id" element={<BookPage />} />
              <Route path="recommendations" element={<Recommendations />} />
              <Route path="loans" element={<Loans />} />
              <Route path="holds" element={<Holds />} />
              <Route path="fines" element={<Fines />} />
              <Route path="profile" element={<Profile />} />
              <Route path="desk" element={<Protected staff><Desk /></Protected>} />
              <Route path="members" element={<Protected staff><Members /></Protected>} />
              <Route path="members/:id" element={<Protected staff><MemberPage /></Protected>} />
              <Route path="reports" element={<Protected staff><Reports /></Protected>} />
              <Route path="settings" element={<Protected staff><Settings /></Protected>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
