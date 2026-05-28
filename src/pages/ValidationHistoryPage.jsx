import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  deletingRuleId,
  onDuplicateRule
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState('summary'); // 'summary' | 'sql' | 'logs'
  const returnedRows = result.resultRows ?? result.failedRows ?? 0;
  const isRunning = runningRuleId === result.ruleId;
  const isDeleting = deletingRuleId === result.ruleId;

  // Generate mock background operational log timeline (purged of DevOps heavy jargon)
  const mockOrchestrationTimeline = useMemo(() => {
    const uuid = result.id || `task-uuid-${Math.random().toString(36).substring(2, 10)}`;
    const baseTime = new Date(result.executionTime);
    const offsetTime = (sec) => new Date(baseTime.getTime() + sec * 1000).toLocaleTimeString();

    return [
      { time: offsetTime(0), text: `Queue Event: Validation job enqueued (UUID: ${uuid})` },
      { time: offsetTime(0.5), text: `Worker Processing: Job assigned to container node-f8a9` },
      { time: offsetTime(1), text: `Task Step: Connected to connection context "${result.datasetName}"... OK` },
      { time: offsetTime(1.5), text: `Task Step: Initiating SQL query execution... OK` },
      { time: offsetTime(2.2), text: `Validation Processing: Inspected ${result.checkedRows?.toLocaleString() || 5000} rows. Flagged ${returnedRows} violations.` },
      ...(returnedRows > 0
        ? [
            { time: offsetTime(2.5), text: `Notification Sent: Dispatched violation alerts to admin@company.com.` }
          ]
        : [
            { time: offsetTime(2.5), text: `Notification Sent: Summary report logged (No failures caught).` }
          ]
      ),
      { time: offsetTime(3.2), text: `Execution Event: Background Task validation execution completed.` }
    ];
  }, [result, returnedRows]);

  return (
    <article className="border border-slate-200 dark:border-slate-800 rounded-lg bg-white dark:bg-slate-900/30 overflow-hidden transition-all text-xs">
      
      {/* Summary row click-to-expand */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex flex-col md:flex-row md:items-center justify-between p-4 cursor-pointer gap-4 hover:bg-slate-50 dark:hover:bg-slate-900/40"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={`inline-block h-2 w-2 rounded-full ${returnedRows > 0 ? 'bg-amber-500' : 'bg-emerald-500'}`} />
            <h4 className="text-xs font-semibold text-slate-900 dark:text-white truncate">{result.ruleName}</h4>
            <span className="text-slate-200 dark:text-slate-800 hidden md:block">|</span>
            <span className="text-[11px] text-slate-500 truncate">{result.datasetName}</span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-[11px] text-slate-400">
            <span>
              <strong className="text-slate-500 dark:text-slate-600">Inspected:</strong> {result.checkedRows?.toLocaleString() || 0} rows
            </span>
            <span>•</span>
            <span className={returnedRows > 0 ? 'text-amber-500 font-semibold' : ''}>
              <strong className="text-slate-500 dark:text-slate-600">Violations:</strong> {returnedRows}
            </span>
            <span>•</span>
            <span>
              <strong className="text-slate-500 dark:text-slate-600">Executed:</strong> {formatDateTime(result.executionTime)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-600 dark:text-slate-350 transition-colors"
          >
            {expanded ? 'Hide Details' : 'View Audit'}
          </button>
          <button
            onClick={() => onDuplicateRule(result)}
            className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-600 dark:text-slate-350 transition-colors"
          >
            Duplicate Rule
          </button>
          {result.ruleId && (
            <button
              onClick={() => onRunRule(result)}
              disabled={isRunning}
              className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-600 dark:text-slate-350 transition-colors"
            >
              {isRunning ? <Loader label="" compact /> : 'Rerun'}
            </button>
          )}
          <button
            onClick={() => onDeleteRule(result.ruleId, result.ruleName, result.id)}
            disabled={isDeleting}
            className="rounded bg-rose-500/10 hover:bg-rose-500/20 px-2 py-1 font-semibold text-rose-500 transition-colors"
          >
            {isDeleting ? <Loader label="" compact /> : 'Delete'}
          </button>
        </div>
      </div>

      {/* Accordion tabs disclosure */}
      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/20 p-4 space-y-4">
          <div className="flex items-center gap-1.5 border-b border-slate-200 dark:border-slate-800 pb-2">
            {[
              ['summary', 'Execution summary'],
              ['sql', 'SQL Statement'],
              ['logs', 'Orchestrator Timelines']
            ].map(([tabId, label]) => (
              <button
                key={tabId}
                onClick={() => setActiveTab(tabId)}
                className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${
                  activeTab === tabId
                    ? 'bg-slate-200 dark:bg-slate-800 text-slate-900 dark:text-white'
                    : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {activeTab === 'summary' && (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Database / Table Context</span>
                  <span className="text-slate-700 dark:text-slate-200 mt-0.5 block">{result.datasetName}</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Execution duration</span>
                  <span className="text-slate-700 dark:text-slate-200 font-mono mt-0.5 block">{result.duration || '0.8s'}</span>
                </div>
              </div>
              {result.rows && result.rows.length > 0 && (
                <div>
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-2">Anomalous Row Sample</span>
                  <ResultTable
                    rows={result.rows}
                    title=""
                    description=""
                    emptyTitle="No violation rows stored"
                    emptyMessage="Aggregated execution metadata only."
                    pageSize={3}
                  />
                </div>
              )}
            </div>
          )}

          {activeTab === 'sql' && (
            <div>
              <span className="text-[10px] uppercase font-semibold text-slate-400 block">Validation Query</span>
              <pre className="mt-1 bg-slate-950 p-3 rounded border border-slate-800 font-mono text-slate-300 overflow-x-auto leading-relaxed">
                {result.sql || '-- SQL statement not recorded'}
              </pre>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="space-y-3">
              <span className="text-[10px] uppercase font-semibold text-slate-400 block">Background Task execution traces</span>
              <div className="rounded border border-slate-200 dark:border-slate-800 bg-slate-950 p-4 font-mono text-slate-300 space-y-1.5 leading-relaxed">
                {mockOrchestrationTimeline.map((log, idx) => (
                  <div key={idx} className="flex gap-3">
                    <span className="text-slate-500 select-none">[{log.time}]</span>
                    <span className={log.text.includes('violations') || log.text.includes('alerts') ? 'text-amber-450' : 'text-slate-350'}>
                      {log.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function ValidationHistoryPage() {
  const { pushToast } = useDataset();
  const navigate = useNavigate();
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
      setError(loadError.message || 'Validation history logs could not be loaded.');
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

  const handleDuplicateRule = (rule) => {
    // Populate duplicate config in localStorage and redirect to rules workspace page
    const duplicateConfig = {
      nlInput: rule.ruleName.includes('Business') ? '' : rule.ruleName,
      ruleName: `${rule.ruleName} (Copy)`,
      sqlText: rule.sql,
      column: rule.column || '',
    };
    localStorage.setItem('pulseqc:duplicated-rule', JSON.stringify(duplicateConfig));
    pushToast({
      tone: 'info',
      title: 'Rule Duplicated',
      message: 'Rule configuration copied. Loading workspace...',
    });
    navigate('/rules');
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
    <div className="space-y-6 animate-slide-up">
      {/* Title */}
      <div>
        <p className="section-kicker">Audit Trails & Logs</p>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">Validation History Logs</h2>
        <p className="text-xs text-slate-500 mt-1">
          Search and review past validations, SQL query compilations, and background orchestrator event schedules.
        </p>
      </div>

      {/* Main Audit Feed */}
      <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-100 dark:border-slate-850">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Execution Audit Timeline</h3>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by rule, database name..."
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
            <Loader label="Loading audit history..." />
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="empty-state py-8">
            <p className="text-slate-900 dark:text-white font-medium">No validation runs found</p>
            <p className="text-slate-500 text-xs mt-1">
              Verify database connection, run a validation check, or clear search queries.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {filteredHistory.map((item) => (
              <AuditLogItem
                key={item.id}
                result={item}
                onDeleteRule={requestDeleteRule}
                onRunRule={handleRunSavedRule}
                runningRuleId={runningRuleId}
                deletingRuleId={deletingRuleId}
                onDuplicateRule={handleDuplicateRule}
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
