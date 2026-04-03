import { Suspense, lazy } from 'react';
import { NavLink, Outlet, Route, Routes } from 'react-router-dom';
import Loader from './components/common/Loader';
import StatusBadge from './components/common/StatusBadge';
import ThemeToggle from './components/common/ThemeToggle';
import Toast from './components/common/Toast';
import { useDataset } from './context/DatasetContext';
import dataOrbit from './assets/data-orbit.svg';
import dataWave from './assets/data-wave.svg';

const IngestionPage = lazy(() => import('./pages/IngestionPage'));
const RulePage = lazy(() => import('./pages/RulePage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));

const navigation = [
  {
    path: '/',
    label: 'Dataset Intake',
    description: 'Connect files, databases, APIs, and cloud warehouses.',
    eyebrow: 'Connect',
  },
  {
    path: '/rules',
    label: 'Rule Builder',
    description: 'Author targeted quality checks and inspect failures.',
    eyebrow: 'Validate',
  },
  {
    path: '/dashboard',
    label: 'Observability',
    description: 'Track health, anomalies, drift, and error volume.',
    eyebrow: 'Observe',
  },
];

const formatCompactNumber = (value) =>
  new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value || 0);

const getWorkspaceStatus = ({ selectedDataset, validationResults, failedRows }) => {
  if (!selectedDataset) {
    return {
      label: 'No Dataset',
      tone: 'pending',
      helper: 'Connect a source to unlock validation and observability.',
    };
  }

  if (validationResults) {
    return failedRows > 0
      ? {
          label: 'Validation Completed',
          tone: 'error',
          helper: `${failedRows} rows still need attention in the latest run.`,
        }
      : {
          label: 'Validation Completed',
          tone: 'success',
          helper: 'The latest run finished without any failed rows.',
        };
  }

  return {
    label: 'Dataset Loaded',
    tone: 'success',
    helper: 'Schema metadata is ready for rule authoring.',
  };
};

function MetricTile({ label, value, hint }) {
  return (
    <div className="metric-card">
      <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-cyan-200/50 to-transparent" />
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p>
      <p className="mt-3 text-2xl font-bold text-white">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
    </div>
  );
}

function AppShell() {
  const {
    selectedDataset,
    schemaMetadata,
    validationResults,
    toasts,
    dismissToast,
  } = useDataset();

  const failedRows =
    validationResults?.summary?.failedRows ??
    validationResults?.failedRows?.length ??
    0;
  const isRuleBuilderLocked = !selectedDataset || !schemaMetadata.length;
  const workspaceStatus = getWorkspaceStatus({
    selectedDataset,
    validationResults,
    failedRows,
  });

  return (
    <div className="relative min-h-screen overflow-hidden app-shell-surface">
      <div className="pointer-events-none absolute inset-0">
        <img
          src={dataWave}
          alt=""
          className="scene-image absolute left-0 top-0 h-full w-full object-cover opacity-40"
        />
        <img
          src={dataOrbit}
          alt=""
          className="scene-image scene-image-orbit absolute right-[-6rem] top-[-8rem] h-[34rem] w-[34rem] opacity-35"
        />
        <div className="absolute left-[-8rem] top-10 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute right-[-7rem] top-24 h-64 w-64 rounded-full bg-rose-500/10 blur-3xl" />
        <div className="absolute bottom-0 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-emerald-400/10 blur-3xl" />
        <div className="grid-overlay absolute inset-0 opacity-55" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1600px] flex-col gap-4 px-4 py-4 sm:gap-6 sm:py-6 lg:flex-row lg:px-6">
        <aside className="glass-panel hidden w-full max-w-sm flex-col justify-between overflow-hidden p-5 lg:flex xl:max-w-md xl:p-6">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <p className="section-kicker">Enterprise Console</p>
                <h1 className="mt-3 text-3xl font-semibold text-white">
                  Data Validity Checker
                </h1>
              </div>
              <div className="brand-badge flex h-14 w-14 items-center justify-center rounded-[1.4rem] text-lg font-semibold text-cyan-100">
                DVC
              </div>
            </div>

            <p className="mt-4 text-sm leading-6 text-slate-400">
              A richer control plane for onboarding data, building rules, and
              visualizing validity signals with live or locally-derived metrics.
            </p>

            <div className="mt-6 flex flex-wrap gap-2">
              {['Schema-aware', 'Locally profiled CSVs', '3D glass UI'].map((chip) => (
                <span
                  key={chip}
                  className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-slate-300"
                >
                  {chip}
                </span>
              ))}
            </div>

            <div className="mt-8 space-y-3">
              {navigation.map((item) => (
                item.path === '/rules' && isRuleBuilderLocked ? (
                  <div
                    key={item.path}
                    className="nav-link nav-link-disabled"
                    title="Upload a dataset to start validation."
                    aria-disabled="true"
                  >
                    <span>
                      <span className="text-[0.68rem] uppercase tracking-[0.24em] text-slate-500">
                        {item.eyebrow}
                      </span>
                      <span className="block text-base font-semibold text-inherit">
                        {item.label}
                      </span>
                      <span className="mt-1 block text-xs text-slate-500">
                        Upload a dataset to unlock this workspace.
                      </span>
                    </span>
                    <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
                      Locked
                    </span>
                  </div>
                ) : (
                  <NavLink
                    key={item.path}
                    end={item.path === '/'}
                    to={item.path}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? 'nav-link-active' : ''}`
                    }
                  >
                    <span>
                      <span className="text-[0.68rem] uppercase tracking-[0.24em] text-cyan-300/70">
                        {item.eyebrow}
                      </span>
                      <span className="block text-base font-semibold text-inherit">
                        {item.label}
                      </span>
                      <span className="mt-1 block text-xs text-slate-400">
                        {item.description}
                      </span>
                    </span>
                    <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
                      Open
                    </span>
                  </NavLink>
                )
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <ThemeToggle />

            <div className="subtle-card">
              <p className="section-kicker">Active Dataset</p>
              <div className="mt-3">
                <StatusBadge tone={workspaceStatus.tone}>
                  {workspaceStatus.label}
                </StatusBadge>
              </div>
              <h2 className="mt-3 text-lg font-semibold text-white">
                {selectedDataset?.name || 'No dataset connected'}
              </h2>
              <p className="mt-2 text-sm text-slate-400">
                {selectedDataset
                  ? `${selectedDataset.sourceType} source via ${selectedDataset.subType}`
                  : 'Connect a source to unlock schema-aware validation and live observability.'}
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                {workspaceStatus.helper}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <MetricTile
                label="Columns"
                value={formatCompactNumber(schemaMetadata.length)}
                hint="Schema fields profiled"
              />
              <MetricTile
                label="Records"
                value={formatCompactNumber(selectedDataset?.records)}
                hint="Rows represented in the current source"
              />
              <MetricTile
                label="Failed Rows"
                value={formatCompactNumber(failedRows)}
                hint="Most recent validation run"
              />
            </div>
          </div>
        </aside>

        <div className="flex-1">
          <header className="glass-panel p-4 sm:p-5 lg:p-6">
            <div className="flex flex-col gap-5 lg:gap-6 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <p className="section-kicker">Data Quality Workspace</p>
                <h2 className="mt-3 text-3xl font-semibold text-white">
                  Validate data with a control room that feels alive
                </h2>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
                  Move from ingestion to validation to observability without
                  leaving the control plane. When the backend is unavailable, the
                  dashboard now derives its signals from your connected schema and
                  rule outputs instead of inventing numbers.
                </p>

                <div className="mt-5 flex flex-wrap gap-2.5 sm:gap-3">
                  <StatusBadge tone={workspaceStatus.tone}>
                    {workspaceStatus.label}
                  </StatusBadge>
                  <span className="status-chip">
                    Live source awareness
                  </span>
                  <span className="status-chip">
                    Derived observability
                  </span>
                  <span className="status-chip">
                    Theme toggle
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-4 xl:max-w-[36rem]">
                <div className="flex justify-end xl:hidden">
                  <ThemeToggle />
                </div>

                <div className="hero-visual">
                  <div className="hero-visual-copy">
                    <p className="text-xs uppercase tracking-[0.24em] text-cyan-300/70">
                      Live Command Deck
                    </p>
                    <p className="mt-2 text-lg font-semibold text-white">
                      {selectedDataset?.name || 'Waiting for a connected dataset'}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      {selectedDataset
                        ? `Tracking ${selectedDataset.records || 0} rows across ${schemaMetadata.length} columns.`
                        : 'Connect a source to light up schema metrics, validation outputs, and observability charts.'}
                    </p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    <MetricTile
                      label="Dataset"
                      value={selectedDataset ? 'Ready' : 'Pending'}
                      hint={selectedDataset?.name || 'Awaiting source connection'}
                    />
                    <MetricTile
                      label="Schema"
                      value={schemaMetadata.length || 0}
                      hint="Profiled columns"
                    />
                    <MetricTile
                      label="Alerts"
                      value={failedRows}
                      hint="Open validation failures"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-6 flex gap-3 overflow-x-auto pb-1 lg:hidden">
              {navigation.map((item) => (
                item.path === '/rules' && isRuleBuilderLocked ? (
                  <span
                    key={item.path}
                    className="pill-button pill-button-disabled whitespace-nowrap"
                    title="Upload a dataset to start validation."
                  >
                    {item.label}
                  </span>
                ) : (
                  <NavLink
                    key={item.path}
                    end={item.path === '/'}
                    to={item.path}
                    className={({ isActive }) =>
                      `pill-button whitespace-nowrap ${
                        isActive ? 'pill-button-active' : ''
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                )
              ))}
            </div>
          </header>

          <main className="py-4 sm:py-6">
            <Suspense
              fallback={
                <div className="glass-panel p-6">
                  <Loader label="Loading workspace" />
                </div>
              }
            >
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<IngestionPage />} />
        <Route path="/rules" element={<RulePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Route>
    </Routes>
  );
}
