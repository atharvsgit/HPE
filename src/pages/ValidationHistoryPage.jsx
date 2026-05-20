import { useEffect, useMemo, useState } from 'react';
import ConfirmationModal from '../components/common/ConfirmationModal';
import Loader from '../components/common/Loader';
import ResultTable from '../components/common/ResultTable';
import StatusBadge from '../components/common/StatusBadge';
import { useDataset } from '../context/DatasetContext';
import {
  createSavedRule,
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

const statusTone = (status) => {
  const normalized = String(status || '').toUpperCase();

  if (['PASS', 'COMPLETED', 'ACTIVE'].includes(normalized)) {
    return 'success';
  }

  if (normalized === 'FAIL' || normalized === 'ERROR') {
    return 'error';
  }

  return 'pending';
};

function ResultPanel({ result, onDeleteRule, onRunRule, onSaveRule, runningRuleId }) {
  const [expanded, setExpanded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const canDeleteRule = Boolean(result.ruleId);
  const observedValue = result.resultRows ?? result.failedRows ?? 0;

  const isRunning = runningRuleId === result.ruleId;

  const handleSave = async () => {
    setIsSaving(true);
    await onSaveRule(result);
    setIsSaving(false);
  };

  return (
    <article className="border-b border-slate-800/80 last:border-0 py-4 transition-colors hover:bg-slate-800/20 px-4 -mx-4 rounded-lg">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${statusTone(result.status) === 'success' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            <h3 className="text-sm font-semibold text-slate-200 truncate">{result.ruleName}</h3>
            <span className="text-slate-600">/</span>
            <span className="text-xs text-slate-400">
              {result.datasetName}
            </span>
            <span className="text-slate-600">/</span>
            <span className="text-xs text-slate-400">
              {formatDateTime(result.executionTime)}
            </span>
            <span className="text-slate-600">/</span>
            <span className="text-xs font-medium text-slate-300">
              {observedValue} observed
            </span>
          </div>

          <div className="mt-2 overflow-hidden rounded-md border border-slate-800 bg-[#0d1117]/80 px-3 py-2">
            <code className="block truncate font-mono text-xs text-slate-400">
              {result.sql || 'No SQL provided'}
            </code>
          </div>
        </div>

        <div className="flex items-center gap-1 lg:ml-4 lg:shrink-0 pt-1">
          {!canDeleteRule && (
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300 transition-colors"
            >
              {isSaving ? <Loader label="" compact /> : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                  </svg>
                  Save
                </>
              )}
            </button>
          )}

          {canDeleteRule && (
            <button
              type="button"
              onClick={() => onRunRule(result.ruleId)}
              disabled={isRunning}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            >
              {isRunning ? <Loader label="" compact /> : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Run
                </>
              )}
            </button>
          )}

          {canDeleteRule && (
            <button
              type="button"
              onClick={() => onDeleteRule(result.ruleId, result.ruleName, result.id)}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </button>
          )}

          <button
            type="button"
            onClick={() => setExpanded((curr) => !curr)}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            View
          </button>

          {!canDeleteRule && (
            <button
              type="button"
              onClick={() => onDeleteRule(result.ruleId, result.ruleName, result.id)}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Remove
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
          <div>
            <p className="field-label">Full SQL Query</p>
            <pre className="overflow-x-auto rounded-md border border-slate-800 bg-[#0d1117] p-3 font-mono text-xs leading-relaxed text-slate-300">
              {result.sql || 'SQL was not included in this backend result.'}
            </pre>
          </div>

          <div>
            <p className="field-label">Stored Outcome</p>
            <div className="grid gap-3 md:grid-cols-3">
              {[
                ['Status', result.status || 'Unknown'],
                ['Observed Value', observedValue],
                ['Duration', result.duration ?? 'backend recorded'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-slate-800 bg-[#0d1117]/80 px-3 py-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-200">{value}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Saved history stores the aggregate outcome. Manual runs can also
              return a live preview of violating rows.
            </p>
          </div>

          <ResultTable
            rows={result.rows || []}
            title="Violating Rows Preview"
            description="Rows are shown when this item came from a freshly executed rule response."
            emptyTitle="No row preview on this history item"
            emptyMessage="Stored history keeps aggregate results; run the saved rule again to view a fresh row preview."
            pageSize={5}
          />
        </div>
      )}
    </article>
  );
}

export default function ValidationHistoryPage() {
  const { pushToast } = useDataset();
  const [history, setHistory] = useState([]);
  const [savedRules, setSavedRules] = useState([]);
  const [selectedRuleId, setSelectedRuleId] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [runningRuleId, setRunningRuleId] = useState('');
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [error, setError] = useState('');

  const loadHistory = async (ruleId = selectedRuleId) => {
    setLoading(true);
    setError('');

    try {
      const [rules, results] = await Promise.all([
        getSavedRules(),
        getRuleResults(ruleId),
      ]);
      setSavedRules(rules);
      setHistory(results);
    } catch (loadError) {
      setError(loadError.message || 'Validation history could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory('all');
  }, []);

  const filteredHistory = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    if (!normalizedSearch) {
      return history;
    }

    return history.filter((entry) =>
      [entry.ruleName, entry.datasetName, entry.sql, entry.status]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedSearch)),
    );
  }, [history, searchTerm]);

  const handleRuleFilter = async (ruleId) => {
    setSelectedRuleId(ruleId);
    await loadHistory(ruleId);
  };

  const handleRunSavedRule = async (rule) => {
    setRunningRuleId(rule.id);

    try {
      const result = await runSavedRule(rule.id, rule);
      setHistory((currentHistory) => [result, ...currentHistory]);
    } catch (runError) {
      setError(runError.message || 'Saved rule execution failed.');
    } finally {
      setRunningRuleId('');
    }
  };

  const handleRunHistoryRule = async (ruleId) => {
    const rule = savedRules.find((r) => String(r.id) === String(ruleId));
    if (!rule) {
      pushToast({ tone: 'error', title: 'Cannot run', message: 'The rule is no longer saved.' });
      return;
    }
    await handleRunSavedRule(rule);
  };

  const handleSaveHistoryRule = async (result) => {
    try {
      const savedRule = await createSavedRule({
        ruleName: result.ruleName || 'Ad hoc business rule',
        sql: result.sql,
        datasetName: result.datasetName,
        expectedResult: result.expectedResult || { type: 'zero_violations' },
      });
      setSavedRules((current) => [savedRule, ...current]);
      pushToast({
        tone: 'success',
        title: 'Rule saved',
        message: 'The execution was saved to the registry.',
      });
    } catch (saveError) {
      pushToast({
        tone: 'error',
        title: 'Could not save rule',
        message: saveError.message || 'An error occurred while saving the rule.',
      });
    }
  };

  const requestDeleteRule = (ruleId, ruleName, resultId) => {
    setDeleteCandidate({ ruleId, ruleName, resultId });
  };

  const closeDeleteModal = () => {
    setDeleteCandidate(null);
  };

  const handleConfirmDeleteRule = async () => {
    if (!deleteCandidate) {
      return;
    }

    const { ruleId, resultId } = deleteCandidate;

    // If it's an ad-hoc run, just remove it from the UI history state
    if (!ruleId) {
      setHistory((currentHistory) =>
        currentHistory.filter((entry) => String(entry.id) !== String(resultId)),
      );
      closeDeleteModal();
      return;
    }

    try {
      await deleteSavedRule(ruleId);
      const nextSelectedRuleId =
        String(selectedRuleId) === String(ruleId) ? 'all' : selectedRuleId;
      setSelectedRuleId(nextSelectedRuleId);
      setSavedRules((currentRules) =>
        currentRules.filter((rule) => String(rule.id) !== String(ruleId)),
      );
      await loadHistory(nextSelectedRuleId);
      pushToast({
        tone: 'success',
        title: 'Rule deleted',
        message: 'The saved rule was removed from the registry.',
      });
    } catch (deleteError) {
      setError(deleteError.message || 'Saved rule could not be deleted.');
      pushToast({
        tone: 'error',
        title: 'Delete failed',
        message: deleteError.message || 'The saved rule registry rejected the delete request.',
      });
    } finally {
      closeDeleteModal();
    }
  };

  return (
    <div className="space-y-10">
      <section className="glass-panel animate-slide-up p-6 sm:p-10 lg:p-14">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="section-kicker">Validation History</p>
            <h2 className="mt-4 text-4xl font-semibold text-white">
              Persistent rule execution timeline
            </h2>
            <p className="mt-5 max-w-4xl text-base leading-7 text-slate-400">
              Every rule run is retained with database context, SQL, status, observed values,
              and execution time so analysts and compliance reviewers can revisit
              older validations alongside the newest runs.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[34rem]">
            <div className="metric-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Runs</p>
              <p className="mt-3 text-2xl font-bold text-white">{history.length}</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">Stored executions</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Rules</p>
              <p className="mt-3 text-2xl font-bold text-white">{savedRules.length}</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">Registry entries</p>
            </div>
            <div className="metric-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Observed Values</p>
              <p className="mt-3 text-2xl font-bold text-white">
                {history.reduce(
                  (total, entry) => total + Number(entry.resultRows ?? entry.failedRows ?? 0),
                  0,
                )}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-400">Aggregate values returned by rules</p>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-8">
        <aside className="glass-panel p-6 sm:p-8 lg:p-10">
          <p className="section-kicker">Saved Queries</p>
          <h3 className="mt-3 text-2xl font-semibold text-white">Rule explorer</h3>

          <button
            type="button"
            onClick={() => handleRuleFilter('all')}
            className={`selection-card mt-5 w-full ${selectedRuleId === 'all' ? 'selection-card-active' : ''}`}
          >
            <p className="text-sm font-semibold text-white">All executions</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Search across backend-normalized validation history.
            </p>
          </button>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {savedRules.map((rule) => (
              <div key={rule.id} className="selection-card">
                <button
                  type="button"
                  onClick={() => handleRuleFilter(rule.id)}
                  className="w-full text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-white">{rule.ruleName}</p>
                    <StatusBadge tone={statusTone(rule.status)}>{rule.status}</StatusBadge>
                  </div>
                  <p className="mt-2 max-h-12 overflow-hidden text-sm leading-6 text-slate-400">
                    {rule.sql}
                  </p>
                  <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                    {rule.scheduleCron ? `Schedule ${rule.scheduleCron}` : 'Manual only'}
                  </p>
                </button>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => handleRunSavedRule(rule)}
                    disabled={Boolean(runningRuleId)}
                    className="secondary-button w-full"
                  >
                    {runningRuleId === rule.id ? <Loader label="Running" compact /> : 'Run Saved Rule'}
                  </button>
                  <button
                    type="button"
                    onClick={() => requestDeleteRule(rule.id, rule.ruleName, null)}
                    className="secondary-button w-full border-rose-400/30 text-rose-200 hover:border-rose-300/60 hover:text-rose-100"
                  >
                    Delete Rule
                  </button>
                </div>
              </div>
            ))}
          </div>

          {!savedRules.length && (
            <div className="empty-state mt-5 min-h-[180px]">
              <p className="text-lg font-semibold text-white">No saved rules yet</p>
              <p className="mt-3 max-w-sm text-sm leading-6 text-slate-400">
                Save a rule from the Rule Workspace to create a reusable business query.
              </p>
            </div>
          )}
        </aside>

        <section className="glass-panel p-6 sm:p-8 lg:p-10">
          <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="section-kicker">Execution Results</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">
                Searchable validation feed
              </h3>
            </div>
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search by rule, database, SQL, or status"
              className="input-shell lg:max-w-sm"
            />
          </div>

          {error && (
            <div className="inline-banner inline-banner-error mt-5" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="mt-8">
              <Loader label="Loading validation history" />
            </div>
          ) : filteredHistory.length ? (
            <div className="mt-6 space-y-4">
              {filteredHistory.map((result) => (
                <ResultPanel
                  key={result.id}
                  result={result}
                  runningRuleId={runningRuleId}
                  onDeleteRule={requestDeleteRule}
                  onRunRule={handleRunHistoryRule}
                  onSaveRule={handleSaveHistoryRule}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state mt-6">
              <p className="text-lg font-semibold text-white">No matching executions</p>
              <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
                Run a rule from the Rule Workspace or adjust the search and rule filters.
              </p>
            </div>
          )}
        </section>
      </section>

      <ConfirmationModal
        isOpen={Boolean(deleteCandidate)}
        title={deleteCandidate?.ruleId ? "Delete saved rule" : "Remove from history"}
        message={
          deleteCandidate?.ruleId
            ? `Delete "${deleteCandidate?.ruleName || 'this rule'}" from the saved rule registry? Existing execution history remains available in the overall history feed.`
            : `Remove "${deleteCandidate?.ruleName || 'this execution'}" from your local view?`
        }
        confirmLabel="Delete"
        tone="danger"
        onClose={closeDeleteModal}
        onConfirm={handleConfirmDeleteRule}
      />
    </div>
  );
}
