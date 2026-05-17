import { Suspense, lazy } from 'react';
import { NavLink, Outlet, Route, Routes } from 'react-router-dom';
import Loader from './components/common/Loader';
import StatusBadge from './components/common/StatusBadge';
import Toast from './components/common/Toast';
import { useDataset } from './context/DatasetContext';

const IngestionPage = lazy(() => import('./pages/IngestionPage'));
const RulePage = lazy(() => import('./pages/RulePage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ValidationHistoryPage = lazy(() => import('./pages/ValidationHistoryPage'));

const navigation = [
  {
    path: '/',
    label: 'Dataset Workspace',
    description: 'Register enterprise datasets, SQL sources, APIs, and warehouses.',
    eyebrow: 'Connect',
  },
  {
    path: '/rules',
    label: 'Rule Workspace',
    description: 'Author business rules with assistant, builder, or SQL mode.',
    eyebrow: 'Validate',
  },
  {
    path: '/dashboard',
    label: 'Command Center',
    description: 'Review rule execution activity and business validation status.',
    eyebrow: 'Operate',
  },
  {
    path: '/history',
    label: 'Validation History',
    description: 'Revisit saved rules, executions, SQL, and returned rows.',
    eyebrow: 'Audit',
  },
];

const formatCompactNumber = (value) =>
  new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value || 0);

const getWorkspaceStatus = ({ selectedDataset, validationResults, resultRows }) => {
  if (!selectedDataset) {
    return {
      label: 'No Dataset',
      tone: 'pending',
      helper: 'Connect a source to unlock validation and history.',
    };
  }

  if (validationResults) {
    return {
      label: 'Rule Completed',
      tone: 'success',
      helper: `${resultRows} rows were returned in the latest run.`,
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

  const resultRows =
    validationResults?.summary?.resultRows ??
    validationResults?.summary?.failedRows ??
    validationResults?.failedRows?.length ??
    0;
  const isRuleBuilderLocked = !selectedDataset || !schemaMetadata.length;
  const workspaceStatus = getWorkspaceStatus({
    selectedDataset,
    validationResults,
    resultRows,
  });

  return (
    <div className="relative min-h-screen overflow-hidden app-shell-surface bg-slate-950">
      <div className="relative mx-auto flex min-h-screen w-full max-w-[1800px] flex-col gap-6 px-4 py-4 sm:py-6 lg:flex-row lg:px-8">
        <aside className="glass-panel hidden h-[calc(100vh-3rem)] w-64 shrink-0 flex-col overflow-hidden p-5 lg:sticky lg:top-6 lg:flex">
          <div className="flex items-center justify-between">
            <div>
              <p className="section-kicker">Validation</p>
              <h1 className="mt-2 text-xl font-semibold text-white">DVC Workspace</h1>
            </div>
            <div className="brand-badge flex h-11 w-11 items-center justify-center rounded-2xl text-sm font-semibold text-cyan-100">
              DVC
            </div>
          </div>

          <div className="mt-6 space-y-2">
            {navigation.map((item) =>
              item.path === '/rules' && isRuleBuilderLocked ? (
                <div
                  key={item.path}
                  className="nav-link nav-link-disabled"
                  title="Connect a dataset to start rule execution."
                  aria-disabled="true"
                >
                  <span>
                    <span className="block text-sm font-semibold text-inherit">
                      {item.label}
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">
                      Connect a dataset first.
                    </span>
                  </span>
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">
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
                    <span className="block text-sm font-semibold text-inherit">
                      {item.label}
                    </span>
                    <span className="mt-1 block text-xs text-slate-400">
                      {item.description}
                    </span>
                  </span>
                </NavLink>
              ),
            )}
          </div>

          <div className="mt-auto space-y-4">
            <div className="subtle-card">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Active Dataset
              </p>
              <div className="mt-3">
                <StatusBadge tone={workspaceStatus.tone}>
                  {workspaceStatus.label}
                </StatusBadge>
              </div>
              <p className="mt-3 text-sm font-semibold text-white">
                {selectedDataset?.name || 'No dataset connected'}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                {workspaceStatus.helper}
              </p>
            </div>
          </div>
        </aside>
        <aside className="hidden">
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
                  executing business rules, and preserving validation evidence for
                  analysts, operations, and compliance teams.
            </p>

            <div className="mt-6 flex flex-wrap gap-2">
              {['Schema-aware', 'Persistent history', 'SQL execution'].map((chip) => (
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
                  : 'Connect a source to unlock schema-aware validation and execution history.'}
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
                label="Result Rows"
                value={formatCompactNumber(resultRows)}
                hint="Rows returned by latest rule"
              />
            </div>
          </div>
        </aside>

        <div className="flex-1">
          <header className="glass-panel p-6 sm:p-8 lg:p-10">
            <div className="flex flex-col gap-5 lg:gap-6 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <p className="section-kicker">Data Quality Workspace</p>
                <h2 className="mt-3 text-3xl font-semibold text-white">
                  Enterprise Validation Workspace
                </h2>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
                  Move from dataset onboarding to rule entry, SQL execution, saved
                  rules, and history in one clear sequence.
                </p>

                <div className="mt-5 flex flex-wrap gap-2.5 sm:gap-3">
                  <StatusBadge tone={workspaceStatus.tone}>
                    {workspaceStatus.label}
                  </StatusBadge>
                  <span className="status-chip">
                    Dataset governance
                  </span>
                  <span className="status-chip">
                    Saved executions
                  </span>
                  <span className="status-chip">
                    Backend-ready APIs
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-4 xl:max-w-[36rem]">
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
                      : 'Connect a source to populate schema metadata, business rules, and validation history.'}
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
                      label="Results"
                      value={resultRows}
                      hint="Rows returned by latest rule"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-8 flex gap-3 overflow-x-auto pb-1 lg:hidden">
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
        <Route path="/history" element={<ValidationHistoryPage />} />
      </Route>
    </Routes>
  );
}
