import {
  BrowserRouter,
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
} from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { getHealth } from './api/client';
import { EmptyState, LoadingState } from './components/ui';
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const TransactionsPage = lazy(() => import('./pages/TransactionsPage'));
const AlertsPage = lazy(() => import('./pages/AlertsPage'));

function Layout() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 30_000,
  });
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="Transaction Monitoring home">
          <span className="brand-mark">T</span>
          <span>
            Transaction
            <span className="brand-subtitle">MONITORING PLATFORM</span>
          </span>
        </Link>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <NavLink to="/" end>
            ▦ Overview
          </NavLink>
          <NavLink to="/transactions">⇄ Transactions</NavLink>
          <NavLink to="/alerts">◇ Alerts</NavLink>
        </nav>
        <div className="sidebar-note">
          <span className="live-dot" /> Connected operations
          <p>Visibility into every transaction.</p>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>OPERATIONS / MONITORING</span>
          <div
            className={`connection ${health.isError ? 'offline' : ''}`}
            role="status"
          >
            <span className="live-dot" />
            {health.isPending
              ? 'Checking API…'
              : health.isError
                ? 'API unavailable'
                : `API online · v${health.data.version}`}
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </main>
        <footer>
          Transaction Monitoring{' '}
          <span>Live operational data · UTC reporting</span>
        </footer>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route
            path="*"
            element={
              <EmptyState
                title="Page not found"
                description="Choose a page from the navigation to continue."
              />
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
