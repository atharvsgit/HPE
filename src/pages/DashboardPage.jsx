import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Loader from '../components/common/Loader';
import ResultTable from '../components/common/ResultTable';
import Skeleton from '../components/common/Skeleton';
import StatusBadge from '../components/common/StatusBadge';
import { useDataset } from '../context/DatasetContext';
import {
  getRuleResults,
  getSavedRules,
  getSchedulerRules,
} from '../services/rulesApi';

const formatDateTime = (value) => {
  if (!value) {
    return 'No executions yet';
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
};

function WorkspaceMetric({ label, value, hint, tone = 'neutral' }) {
  const toneClass =
    tone === 'danger'
      ? 'border-rose-400/25'
      : tone === 'success'
        ? 'border-emerald-400/25'
        : 'border-white/10';

  return (
    <div className={`metric-card min-h-[168px] ${toneClass}`}>
      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-4 text-3xl font-bold text-white">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-400">{hint}</p>
    </div>
  );
}

function ExecutionFeed({ executions }) {
  if (!executions.length) {
    return (
      <div className="empty-state">
        <p className="text-lg font-semibold text-white">No rule executions yet</p>
        <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
          Run a business rule from the Rule Workspace to start building permanent
          validation intelligence for this dataset.
        </p>
        <Link to="/rules" className="primary-button mt-6">
          Open Rule Workspace
        </Link>
      </div>
    );
  }

  return (
    <div className="relative border-l border-slate-800 ml-3 md:ml-4 space-y-6">
      {executions.slice(0, 8).map((execution) => (
        <div key={execution.id} className="relative pl-6 md:pl-8 group">
          <div className={`absolute -left-[5px] top-2 h-2.5 w-2.5 rounded-full border-2 border-[#111827] ${execution.status === 'completed' || execution.status === 'active' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-semibold text-white">{execution.ruleName}</h3>
                <span className="text-xs text-slate-500">{formatDateTime(execution.executionTime)}</span>
              </div>
              <p className="mt-1 text-xs text-slate-400 font-mono truncate">{execution.sql || 'No SQL recorded'}</p>
              <div className="mt-3 flex items-center gap-4 text-xs font-medium text-slate-300">
                <span className="flex items-center gap-1.5"><span className="text-slate-500">Dataset:</span> {execution.datasetName}</span>
                <span className="flex items-center gap-1.5"><span className="text-slate-500">Returned:</span> {execution.resultRows ?? execution.failedRows ?? 0}</span>
                <span className="flex items-center gap-1.5"><span className="text-slate-500">Scanned:</span> {execution.checkedRows}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <Link to="/history" className="rounded-md border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-500 hover:text-white transition-colors">
                View History
              </Link>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { selectedDataset, schemaMetadata, validationResults, datasetRows } = useDataset();
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState([]);
  const [savedRules, setSavedRules] = useState([]);
  const [schedulerRules, setSchedulerRules] = useState([]);

  useEffect(() => {
    let isMounted = true;

    const loadWorkspace = async () => {
      setLoading(true);

      try {
        const [rules, scheduler, globalHistory] = await Promise.all([
          getSavedRules(),
          getSchedulerRules(),
          getRuleResults('all'),
        ]);

        if (!isMounted) {
          return;
        }

        setSavedRules(rules);
        setSchedulerRules(scheduler);
        setHistory(globalHistory);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadWorkspace();

    return () => {
      isMounted = false;
    };
  }, [validationResults]);

  const workspaceSummary = useMemo(() => {
    const totalResults = history.reduce(
      (total, entry) => total + Number(entry.resultRows ?? entry.failedRows ?? 0),
      0,
    );
    const latestExecution = history[0];

    return {
      totalResults,
      latestExecution,
      activeRows: datasetRows.length || selectedDataset?.records || 0,
    };
  }, [datasetRows.length, history, selectedDataset?.records]);

  return (
    <div className="space-y-10">
      <section className="glass-panel animate-slide-up p-6 sm:p-10 lg:p-14">
        <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="section-kicker">Enterprise Validation Workspace</p>
            <h2 className="mt-4 max-w-4xl text-4xl font-semibold text-white">
              Business rule operations for governed datasets
            </h2>
            <p className="mt-5 max-w-4xl text-base leading-7 text-slate-400">
              A simple workspace for daily use: connect a dataset, run the rules
              you care about, and revisit the rows returned by each run.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[32rem]">
            <Link to="/" className="secondary-button">
              Dataset Workspace
            </Link>
            <Link to="/rules" className="primary-button">
              Execute Rule
            </Link>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="grid gap-5 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="glass-panel p-4 sm:p-6">
              <Skeleton className="h-40 w-full" />
            </div>
          ))}
          <div className="glass-panel p-4 sm:p-6 xl:col-span-4">
            <Loader label="Loading validation workspace" />
          </div>
        </div>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <WorkspaceMetric
              label="Active Dataset"
              value={selectedDataset ? 'Ready' : 'Pending'}
              hint={selectedDataset?.name || 'Connect an enterprise dataset to begin.'}
              tone={selectedDataset ? 'success' : 'neutral'}
            />
            <WorkspaceMetric
              label="Schema Fields"
              value={schemaMetadata.length}
              hint={`${workspaceSummary.activeRows} rows available for validation.`}
            />
            <WorkspaceMetric
              label="Saved Rules"
              value={savedRules.length}
              hint={`${schedulerRules.length} scheduler classifications available from backend.`}
            />
            <WorkspaceMetric
              label="Rows Returned"
              value={workspaceSummary.totalResults}
              hint="Total rows returned across saved executions."
              tone={workspaceSummary.totalResults ? 'success' : 'neutral'}
            />
          </section>

          <section className="space-y-8">
            <div className="glass-panel p-6 sm:p-8 lg:p-10">
              <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="section-kicker">Recent Validations</p>
                  <h3 className="mt-3 text-2xl font-semibold text-white">
                    Execution feed
                  </h3>
                </div>
                <Link to="/history" className="secondary-button">
                  Open Full History
                </Link>
              </div>

              <div className="mt-6">
                <ExecutionFeed executions={history} />
              </div>
            </div>

            <div className="glass-panel p-6 sm:p-8 lg:p-10">
              <ResultTable
                rows={workspaceSummary.latestExecution?.rows || []}
                title="Latest Returned Rows"
                description="The newest execution result is shown as a real data table with search and pagination."
                emptyTitle="No returned rows yet"
                emptyMessage="Run a rule from the Rule Workspace to populate this table from backend execution results."
              />
            </div>

            <div className="glass-panel p-6 sm:p-8 lg:p-10">
                <p className="section-kicker">Dataset Activity</p>
                <h3 className="mt-3 text-2xl font-semibold text-white">
                  Source summary
                </h3>
                <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    ['Dataset', selectedDataset?.name || 'Not connected'],
                    ['Source Type', selectedDataset?.sourceType || 'Pending'],
                    ['Connector', selectedDataset?.subType || 'Pending'],
                    ['Last Execution', formatDateTime(workspaceSummary.latestExecution?.executionTime)],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"
                    >
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                        {label}
                      </p>
                      <p className="mt-2 text-sm font-semibold text-white">{value}</p>
                    </div>
                  ))}
                </div>
            </div>

              <div className="glass-panel p-6 sm:p-8 lg:p-10">
                <p className="section-kicker">Validation Lifecycle</p>
                <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    ['Connect source', Boolean(selectedDataset)],
                    ['Load schema', schemaMetadata.length > 0],
                    ['Save rules', savedRules.length > 0],
                    ['Persist results', history.length > 0],
                  ].map(([label, done]) => (
                    <div
                      key={label}
                      className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"
                    >
                      <span className="text-sm font-medium text-slate-200">{label}</span>
                      <StatusBadge tone={done ? 'success' : 'pending'}>
                        {done ? 'Done' : 'Pending'}
                      </StatusBadge>
                    </div>
                  ))}
                </div>
              </div>
          </section>
        </>
      )}
    </div>
  );
}
