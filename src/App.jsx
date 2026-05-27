import { Suspense, lazy, useEffect, useState } from 'react';
import { NavLink, Outlet, Route, Routes, Navigate } from 'react-router-dom';
import Loader from './components/common/Loader';
import StatusBadge from './components/common/StatusBadge';
import Toast from './components/common/Toast';
import ThemeToggle from './components/common/ThemeToggle';
import { useDataset } from './context/DatasetContext';
import api from './services/api';

const RulePage = lazy(() => import('./pages/RulePage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ValidationHistoryPage = lazy(() => import('./pages/ValidationHistoryPage'));

const navigation = [
  {
    path: '/dashboard',
    label: 'Dashboard',
    description: 'Active scheduled tasks and orchestration activity.',
  },
  {
    path: '/rules',
    label: 'Rule Workspace',
    description: 'Connect databases and author business rules.',
  },
  {
    path: '/history',
    label: 'Validation History',
    description: 'Searchable timeline logs and audit logs.',
  },
];

export function AppShell() {
  const {
    selectedDataset,
    schemaMetadata,
    toasts,
    dismissToast,
    pushToast,
  } = useDataset();

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [backendStatus, setBackendStatus] = useState('checking'); // checking | online | offline
  const [retrying, setRetrying] = useState(false);

  const checkBackendHealth = async (showSuccess = false) => {
    try {
      if (showSuccess) setRetrying(true);
      // Attempt to hit the rules endpoint with a small timeout override
      await api.get('/rules', { timeout: 3000 });
      setBackendStatus('online');
      if (showSuccess) {
        pushToast({
          tone: 'success',
          title: 'Backend connected',
          message: 'Real-time orchestration and execution APIs are now online.',
        });
      }
    } catch (error) {
      setBackendStatus('offline');
      if (showSuccess) {
        pushToast({
          tone: 'error',
          title: 'Connection failed',
          message: 'The backend server on port 8000 is still unreachable.',
        });
      }
    } finally {
      setRetrying(false);
    }
  };

  useEffect(() => {
    // Initial check
    checkBackendHealth();

    // Regular interval poll every 20 seconds
    const interval = setInterval(() => {
      checkBackendHealth();
    }, 20000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative min-h-screen app-shell-surface flex flex-col md:flex-row">
      {/* Mobile Header */}
      <header className="flex md:hidden items-center justify-between border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-slate-900 dark:text-slate-100">DVC Platform</span>
          {backendStatus === 'offline' && (
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500" title="Running in simulated mode" />
          )}
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <button
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16m-7 6h7" />
            </svg>
          </button>
        </div>
      </header>

      {/* Sidebar navigation */}
      <aside
        className={`${
          isSidebarOpen ? 'flex' : 'hidden'
        } md:flex flex-col w-full md:w-64 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shrink-0 p-5 md:h-screen md:sticky md:top-0`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-600 font-bold text-white text-sm">
              DVC
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-900 dark:text-white leading-tight">Data Quality</h1>
              <p className="text-[10px] text-slate-400 font-medium tracking-wide">ENTERPRISE PLATFORM</p>
            </div>
          </div>
          <button
            onClick={() => setIsSidebarOpen(false)}
            className="hidden max-md:block p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="mt-8 space-y-1 flex-1">
          {navigation.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <div className="flex flex-col text-left">
                <span className="text-sm font-semibold">{item.label}</span>
                <span className="text-[11px] font-normal text-slate-400 mt-0.5 line-clamp-1">
                  {item.description}
                </span>
              </div>
            </NavLink>
          ))}
        </nav>

        {/* Sidebar Footer info */}
        <div className="border-t border-slate-200 dark:border-slate-800 pt-5 mt-auto space-y-4">
          <div className="rounded-lg bg-slate-50 dark:bg-slate-900/80 p-3.5 border border-slate-200 dark:border-slate-800/80">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest block">Active Dataset</span>
            <span className="text-sm font-semibold text-slate-800 dark:text-white mt-1.5 block truncate">
              {selectedDataset?.name || 'None Connected'}
            </span>
            {selectedDataset && (
              <span className="text-xs text-slate-500 mt-1 block capitalize">
                {selectedDataset.sourceType} via {selectedDataset.subType}
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* Main content workspace */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar header */}
        <header className="hidden md:flex items-center justify-between h-14 px-8 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 mr-2 p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Toggle sidebar"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h7" />
              </svg>
            </button>
            <span className="text-xs text-slate-400">Workspace / Platform Console</span>
          </div>

          <div className="flex items-center gap-4">
            {/* Backend Health Badge */}
            <div className="flex items-center gap-2">
              {backendStatus === 'online' ? (
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-xs font-medium text-slate-500">API Connected</span>
                </div>
              ) : backendStatus === 'offline' ? (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 px-2 py-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span className="text-[11px] font-semibold text-amber-500 uppercase">Simulated Mode</span>
                  </div>
                  <button
                    onClick={() => checkBackendHealth(true)}
                    disabled={retrying}
                    className="text-xs font-semibold text-sky-500 hover:text-sky-400 disabled:opacity-50"
                  >
                    {retrying ? 'Retrying...' : 'Reconnect'}
                  </button>
                </div>
              ) : (
                <span className="text-xs text-slate-400">Verifying Connection...</span>
              )}
            </div>

            <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />

            <ThemeToggle />
          </div>
        </header>

        {/* Global Offline Banner if in simulated mode */}
        {backendStatus === 'offline' && (
          <div className="bg-amber-500/5 dark:bg-amber-500/10 border-b border-amber-500/25 px-8 py-2 text-xs text-amber-600 dark:text-amber-400 flex items-center justify-between">
            <p>
              <strong>Running in Simulated Offline Mode.</strong> The backend server is unreachable. Validations and rules are run locally and persisted to browser storage.
            </p>
            <button
              onClick={() => checkBackendHealth(true)}
              className="underline font-semibold hover:no-underline"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Page contents container */}
        <main className="flex-1 p-6 md:p-8 overflow-y-auto">
          <div className="mx-auto max-w-6xl w-full">
            <Suspense
              fallback={
                <div className="flex items-center justify-center min-h-[300px]">
                  <Loader label="Loading workspace" />
                </div>
              }
            >
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {/* Main Routes */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/rules" element={<RulePage />} />
        <Route path="/history" element={<ValidationHistoryPage />} />
        {/* Fallbacks */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
