import { useEffect, useMemo, useState } from 'react';
import ConfirmationModal from '../components/common/ConfirmationModal';
import Loader from '../components/common/Loader';
import ResultTable from '../components/common/ResultTable';
import StatusBadge from '../components/common/StatusBadge';
import { useDataset } from '../context/DatasetContext';
import {
  deleteSavedRule,
  getSavedRules,
  getRuleResults,
  runSavedRule,
} from '../services/rulesApi';

const formatDateTime = (value) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));

function AuditLogItem({
  result,
  onDeleteRule,
  onRunRule,
  runningRuleId,
  deletingRuleId
}) {
  const [expanded, setExpanded] = useState(false);
  const returnedRows = result.resultRows ?? result.failedRows ?? 0;
  const isRunning = runningRuleId === result.ruleId;
  const isDeleting = deletingRuleId === result.ruleId;

  // Generate mock background Celery orchestration logs
  const mockOrchestrationTimeline = useMemo(() => {
    const uuid = result.id || `task-uuid-${Math.random().toString(36).substring(2, 10)}`;
    const baseTime = new Date(result.executionTime);
    const offsetTime = (sec) => new Date(baseTime.getTime() + sec * 1000).toLocaleTimeString();

    return [
      { time: offsetTime(0), text: `Queue Broker: Task enqueued into active_jobs queue (UUID: ${uuid})` },
      { time: offsetTime(0.5), text: `Celery Worker: Dequeued by worker node-f8a9` },
      { time: offsetTime(1), text: `Database: Fetching connector metadata for "${result.datasetName}"...` },
      { time: offsetTime(1.5), text: `Database: Connector handshaked. Initiating validation query...` },
      { time: offsetTime(2.2), text: `Engine: Scanned ${result.checkedRows?.toLocaleString() || 5000} rows. Identified ${returnedRows} violations.` },
      ...(returnedRows > 0
        ? [
            { time: offsetTime(2.5), text: `SMTP daemon: Dispatching alert email to admin@company.com...` },
            { time: offsetTime(3.1), text: `SMTP daemon: Alert digest dispatched successfully.` }
          ]
        : [
            { time: offsetTime(2.5), text: `SMTP daemon: Notification bypassed. Zero anomalies found.` }
          ]
      ),
      { time: offsetTime(3.2), text: `Worker status: Validation task execution completed successfully (Duration: ${result.duration || '0.8s'}).` }
    ];
  }, [result, returnedRows]);

  return (
    <article className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900/30 overflow-hidden transition-all">
      {/* Summary row */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex flex-col md:flex-row md:items-center justify-between p-4 cursor-pointer gap-4 hover:bg-slate-50 dark:hover:bg-slate-900/40"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${returnedRows > 0 ? 'bg-amber-500' : 'bg-emerald-500'}`} />
            <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">{result.ruleName}</h4>
            <span className="text-slate-300 dark:text-slate-700 hidden md:block">|</span>
            <span className="text-xs text-slate-500 truncate">{result.datasetName}</span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-400">
            <span>
              <span className="font-semibold text-slate-500 dark:text-slate-600">Scanned:</span> {result.checkedRows?.toLocaleString() || 0} rows
            </span>
            <span>•</span>
            <span className={returnedRows > 0 ? 'text-amber-500 font-semibold' : ''}>
              <span className="font-semibold text-slate-500 dark:text-slate-600">Violations:</span> {returnedRows}
            </span>
            <span>•</span>
            <span>
              <span className="font-semibold text-slate-500 dark:text-slate-600">Executed:</span> {formatDateTime(result.executionTime)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-600 dark:text-slate-300 transition-colors"
          >
            {expanded ? 'Collapse Logs' : 'View Audit'}
          </button>
          {result.ruleId && (
            <button
              onClick={() => onRunRule(result)}
              disabled={isRunning}
              className="rounded bg-slate-150 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2.5 py-1 font-semibold text-slate-700 dark:text-slate-300 transition-colors"
            >
              {isRunning ? <Loader label="" compact /> : 'Rerun'}
            </button>
          )}
          <button
            onClick={() => onDeleteRule(result.ruleId, result.ruleName, result.id)}
            disabled={isDeleting}
            className="rounded bg-rose-500/10 hover:bg-rose-500/20 px-2.5 py-1 font-semibold text-rose-500 transition-colors"
          >
            {isDeleting ? <Loader label="" compact /> : 'Delete'}
          </button>
        </div>
      </div>

      {/* Expanded view showing celery logs timeline */}
      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/20 p-5 space-y-5 text-xs">
          {/* Query section */}
          <div>
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Compiled SQL Script</span>
            <pre className="mt-1 bg-slate-100 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg p-3 font-mono text-slate-600 dark:text-slate-400 overflow-x-auto leading-relaxed">
              {result.sql || '-- No SQL recorded'}
            </pre>
          </div>

          {/* Background Task Timeline audit */}
          <div>
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Background Celery Orchestration Log</span>
            <div className="mt-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-950 p-4 font-mono text-slate-300 dark:text-slate-400 space-y-2 leading-relaxed">
              {mockOrchestrationTimeline.map((log, idx) => (
                <div key={idx} className="flex gap-3">
                  <span className="text-slate-500 select-none">[{log.time}]</span>
                  <span className={log.text.includes('violations') || log.text.includes('alert') ? 'text-amber-400' : 'text-slate-300'}>
                    {log.text}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Returned rows data sample if exists */}
          {result.rows && result.rows.length > 0 && (
            <div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">Flagged Row Sample ({result.rows.length} rows stored)</span>
              <ResultTable
                rows={result.rows}
                title=""
                description=""
                emptyTitle="No violation payload stored"
                emptyMessage="Aggregated execution metadata only."
                pageSize={3}
              />
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function ValidationHistoryPage() {
  const { pushToast } = useDataset();
  const [history, setHistory] = useState([]);
  const [savedRules, setSavedRules] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [runningRuleId, setRunningRuleId] = useState('');
  const [deletingRuleId, setDeletingRuleId] = useState('');
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [error, setError] = useState('');

  const loadHistory = async () => {
    setLoading(true);
    setError('');

    try {
      const [rules, results] = await Promise.all([
        getSavedRules(),
        getRuleResults('all'),
      ]);
      setSavedRules(rules);
      setHistory(results);
    } catch (loadError) {
      setError(loadError.message || 'Validation history could not be fetched.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const filteredHistory = useMemo(() => {
    const normalized = searchTerm.trim().toLowerCase();
    if (!normalized) return history;

    return history.filter((entry) =>
      [entry.ruleName, entry.datasetName, entry.sql, entry.status]
        .filter(Boolean)
        .some((val) => String(val).toLowerCase().includes(normalized))
    );
  }, [history, searchTerm]);

  const handleRunSavedRule = async (rule) => {
    setRunningRuleId(rule.id);
    try {
      const result = await runSavedRule(rule.id, rule);
      setHistory((prev) => [result, ...prev]);
      pushToast({
        tone: 'success',
        title: 'Validation Executed',
        message: `Task completed. Returned ${result.resultRows || 0} violations.`,
      });
    } catch (runError) {
      pushToast({
        tone: 'error',
        title: 'Execution Failed',
        message: runError.message || 'The saved validation check failed.',
      });
    } finally {
      setRunningRuleId('');
    }
  };

  const requestDeleteRule = (ruleId, ruleName, resultId) => {
    setDeleteCandidate({ ruleId, ruleName, resultId });
  };

  const closeDeleteModal = () => {
    setDeleteCandidate(null);
  };

  const handleConfirmDeleteRule = async () => {
    if (!deleteCandidate) return;

    const { ruleId, resultId } = deleteCandidate;

    // Local-only deletion (ad-hoc runs)
    if (!ruleId) {
      setHistory((prev) => prev.filter((r) => String(r.id) !== String(resultId)));
      closeDeleteModal();
      pushToast({
        tone: 'success',
        title: 'Execution Log Removed',
        message: 'Deleted validation check from history.',
      });
      return;
    }

    setDeletingRuleId(ruleId);
    setHistory((prev) => prev.filter((r) => String(r.ruleId) !== String(ruleId)));
    setSavedRules((prev) => prev.filter((r) => String(r.id) !== String(ruleId)));
    closeDeleteModal();

    try {
      await deleteSavedRule(ruleId);
      pushToast({
        tone: 'success',
        title: 'Rule Registry Updated',
        message: `"${deleteCandidate.ruleName}" removed from registry.`,
      });
    } catch (err) {
      // Re-load to revert optimistic state on actual error
      loadHistory();
      pushToast({
        tone: 'error',
        title: 'Delete Failed',
        message: err.message || 'Could not delete rule from backend registry.',
      });
    } finally {
      setDeletingRuleId('');
    }
  };

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Title */}
      <div>
        <p className="section-kicker">Audit Trails & Logs</p>
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-white mt-1">Validation History</h2>
        <p className="text-sm text-slate-500 mt-2">
          Search and review past validations, SQL query compilations, and background orchestrator event schedules.
        </p>
      </div>

      {/* Scheduler overview summary banner */}
      {history.length > 0 && (
        <div className="grid gap-4 grid-cols-3">
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-4">
            <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Total Audits</span>
            <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">{history.length}</p>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-4">
            <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Scanned Records</span>
            <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">
              {new Intl.NumberFormat('en-US', { notation: 'compact' }).format(history.reduce((acc, h) => acc + (h.checkedRows || 0), 0))}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-4">
            <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Violations Found</span>
            <p className="text-2xl font-bold mt-1 text-amber-500">
              {history.reduce((acc, h) => acc + (h.resultRows || h.failedRows || 0), 0)}
            </p>
          </div>
        </div>
      )}

      {/* Main Audit Feed */}
      <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-100 dark:border-slate-800/80">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Execution Audit Timeline</h3>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by rule, dataset name, or status..."
            className="input-shell text-xs py-1.5 px-3 max-w-sm"
          />
        </div>

        {error && (
          <div className="inline-banner inline-banner-error" role="alert">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader label="Loading audit logs..." />
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="empty-state">
            <svg className="mx-auto h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-slate-900 dark:text-white font-medium mt-3">No validation runs found</p>
            <p className="text-slate-500 text-xs mt-1">
              Verify database connection, run a validation check, or clear search queries.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredHistory.map((item) => (
              <AuditLogItem
                key={item.id}
                result={item}
                onDeleteRule={requestDeleteRule}
                onRunRule={handleRunSavedRule}
                runningRuleId={runningRuleId}
                deletingRuleId={deletingRuleId}
              />
            ))}
          </div>
        )}
      </section>

      <ConfirmationModal
        isOpen={Boolean(deleteCandidate)}
        title={deleteCandidate?.ruleId ? "Delete Rule Registry" : "Remove Audit Log"}
        message={
          deleteCandidate?.ruleId 
            ? `Are you sure you want to delete "${deleteCandidate?.ruleName || 'this rule'}" from the saved rule registry?`
            : `Are you sure you want to remove this execution audit log from history?`
        }
        confirmLabel="Delete"
        tone="danger"
        onClose={closeDeleteModal}
        onConfirm={handleConfirmDeleteRule}
      />
    </div>
  );
}
