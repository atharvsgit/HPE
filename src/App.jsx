import { Suspense, lazy, useEffect, useState } from 'react';
import { NavLink, Outlet, Route, Routes, Navigate } from 'react-router-dom';
import Loader from './components/common/Loader';
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
    description: 'Validation schedules and operations feed.',
  },
  {
    path: '/rules',
    label: 'Rule Workspace',
    description: 'Connect databases and schedule business rules.',
  },
  {
    path: '/history',
    label: 'Validation History',
    description: 'Timeline audit logs and execution records.',
  },
];

export function AppShell() {
  const {
    selectedDataset,
    toasts,
    dismissToast,
    pushToast,
  } = useDataset();

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [backendStatus, setBackendStatus] = useState('checking'); // checking | online | offline
  const [retrying, setRetrying] = useState(false);
  const [activeSchedulesCount, setActiveSchedulesCount] = useState(0);

  const checkBackendHealth = async (showSuccess = false) => {
    try {
      if (showSuccess) setRetrying(true);
      await api.get('/rules', { timeout: 3000 });
      setBackendStatus('online');
      if (showSuccess) {
        pushToast({
          tone: 'success',
          title: 'Backend connected',
          message: 'Validation scheduling APIs are now online.',
        });
      }
    } catch (error) {
      setBackendStatus('offline');
      if (showSuccess) {
        pushToast({
          tone: 'error',
          title: 'Connection failed',
          message: 'The backend validation server is still unreachable.',
        });
      }
    } finally {
      if (showSuccess) setRetrying(false);
    }
  };

  const updateScheduleCount = () => {
    try {
      const stored = localStorage.getItem('pulseqc:scheduled-tasks');
      if (stored) {
        const tasks = JSON.parse(stored);
        const activeCount = tasks.filter((t) => t.status === 'active').length;
        setActiveSchedulesCount(activeCount);
      } else {
        setActiveSchedulesCount(2); // default seed active schedules count
      }
    } catch {
      setActiveSchedulesCount(0);
    }
  };

  useEffect(() => {
    checkBackendHealth();
    updateScheduleCount();

    const interval = setInterval(() => {
      checkBackendHealth();
    }, 20000);

    // Watch for task additions / updates
    window.addEventListener('storage', updateScheduleCount);
    const localCheck = setInterval(updateScheduleCount, 2500);

    return () => {
      clearInterval(interval);
      clearInterval(localCheck);
      window.removeEventListener('storage', updateScheduleCount);
    };
  }, []);

  return (
    <div className="relative min-h-screen app-shell-surface flex flex-col md:flex-row">
      {/* Mobile Header */}
      <header className="flex md:hidden items-center justify-between border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-slate-900 dark:text-slate-100">DVC Platform</span>
          {backendStatus === 'offline' && (
            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
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
        } md:flex flex-col w-full md:w-60 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 shrink-0 p-4 md:h-screen md:sticky md:top-0`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-slate-950 font-bold text-white text-xs dark:bg-white dark:text-slate-950">
              DVC
            </div>
            <div>
              <h1 className="text-xs font-semibold text-slate-900 dark:text-white leading-tight">Data Quality</h1>
              <p className="text-[9px] text-slate-400 font-medium tracking-wide">ENTERPRISE VALIDATION</p>
            </div>
          </div>
          <button
            onClick={() => setIsSidebarOpen(false)}
            className="hidden max-md:block p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="mt-6 space-y-1 flex-1">
          {navigation.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <div className="flex flex-col text-left">
                <span className="text-xs font-semibold">{item.label}</span>
                <span className="text-[10px] font-normal text-slate-400 mt-0.5 line-clamp-1">
                  {item.description}
                </span>
              </div>
            </NavLink>
          ))}
        </nav>

        {/* Sidebar Footer info */}
        <div className="border-t border-slate-200 dark:border-slate-800 pt-4 mt-auto">
          <div className="rounded bg-slate-50 dark:bg-slate-900 p-3 border border-slate-200 dark:border-slate-800">
            <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-widest block">Active Dataset</span>
            <span className="text-xs font-semibold text-slate-800 dark:text-white mt-1 block truncate">
              {selectedDataset?.name || 'None Connected'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main content workspace */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar header */}
        <header className="hidden md:flex items-center justify-between h-12 px-6 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30">
          {/* Breadcrumbs and Context info */}
          <div className="flex items-center gap-4 text-xs">
            <button
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Toggle sidebar"
            >
              <svg className="h-4.5 w-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h7" />
              </svg>
            </button>
            
            <div className="flex items-center gap-1.5 text-slate-400 font-medium">
              <span>Platform</span>
              <span className="text-slate-300 dark:text-slate-700">/</span>
              <span className="text-slate-600 dark:text-slate-300 font-semibold">Enterprise Validation Hub</span>
            </div>

            <div className="h-3 w-px bg-slate-200 dark:bg-slate-800" />

            <div className="flex items-center gap-3 text-[11px] text-slate-500">
              <span>
                <strong className="text-slate-400 dark:text-slate-600">Active Source:</strong>{' '}
                <span className="text-slate-600 dark:text-slate-300 font-semibold">
                  {selectedDataset?.name || 'None'}
                </span>
              </span>
              <span>•</span>
              <span>
                <strong className="text-slate-400 dark:text-slate-600">Schedules:</strong>{' '}
                <span className="text-slate-600 dark:text-slate-300 font-semibold">{activeSchedulesCount} Active</span>
              </span>
              <span>•</span>
              <span>
                <strong className="text-slate-400 dark:text-slate-600">Sessions:</strong>{' '}
                <span className="text-slate-600 dark:text-slate-300 font-semibold">2 Active</span>
              </span>
              <span>•</span>
              <span>
                <strong className="text-slate-400 dark:text-slate-600">Engine:</strong>{' '}
                <span className="text-emerald-500 font-semibold">Idle</span>
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Redesigned Subtle Connection Badge */}
            <div className="flex items-center gap-2 text-xs">
              {backendStatus === 'online' ? (
                <div className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span className="text-[11px] text-slate-400 font-medium">Online</span>
                </div>
              ) : backendStatus === 'offline' ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => checkBackendHealth(true)}
                    disabled={retrying}
                    className="text-[11px] font-semibold text-sky-500 hover:text-sky-400 disabled:opacity-50"
                  >
                    {retrying ? 'Connecting...' : 'Reconnect'}
                  </button>
                </div>
              ) : (
                <span className="text-[11px] text-slate-400">Verifying...</span>
              )}
            </div>

            <div className="h-3 w-px bg-slate-200 dark:bg-slate-800" />

            <ThemeToggle />
          </div>
        </header>

        {/* Page contents container */}
        <main className="flex-1 p-5 md:p-6 overflow-y-auto">
          <div className="mx-auto max-w-6xl w-full">
            <Suspense
              fallback={
                <div className="flex items-center justify-center min-h-[200px]">
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
