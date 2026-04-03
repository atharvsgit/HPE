import {
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Link } from 'react-router-dom';
import Loader from '../common/Loader';
import StatusBadge from '../common/StatusBadge';
import { useDataset } from '../../context/DatasetContext';
import { runValidation } from '../../services/endpoints';

const ruleOptions = [
  {
    id: 'between',
    label: 'Between',
    description: 'Checks whether a numeric value lies within a minimum and maximum range.',
    supportedLabel: 'Numeric columns',
    tooltip: 'Between: checks whether a numeric value falls inside the configured minimum and maximum bounds.',
  },
  {
    id: 'regex',
    label: 'Regex',
    description: 'Matches text-like values against a regular expression pattern.',
    supportedLabel: 'String, UUID, and timestamp columns',
    tooltip: 'Regex: checks whether a text-like value matches the expected pattern.',
  },
  {
    id: 'not_null',
    label: 'Not Null',
    description: 'Ensures every inspected row has a value for the selected column.',
    supportedLabel: 'All column types',
    tooltip: 'Not Null: checks that the selected column is populated in every inspected row.',
  },
];

const severityClasses = {
  critical: 'border-rose-500/25 bg-rose-500/10 text-rose-100',
  high: 'border-orange-400/25 bg-orange-400/10 text-orange-100',
  medium: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
};

const applicableRulesByType = {
  numeric: ['between', 'not_null'],
  string: ['regex', 'not_null'],
  boolean: ['not_null'],
  default: ['regex', 'not_null'],
};

const numericTypes = [
  'integer',
  'decimal',
  'float',
  'double',
  'number',
  'numeric',
  'bigint',
  'smallint',
];

const booleanTypes = ['boolean', 'bool'];

const stringTypes = [
  'varchar',
  'char',
  'string',
  'text',
  'uuid',
  'timestamp',
  'date',
  'datetime',
];

const getRuleLabel = (ruleId) =>
  ruleOptions.find((option) => option.id === ruleId)?.label || ruleId;

const toColumnTypeGroup = (dataType = '') => {
  const normalizedType = String(dataType || '').trim().toLowerCase();

  if (numericTypes.includes(normalizedType)) {
    return 'numeric';
  }

  if (booleanTypes.includes(normalizedType)) {
    return 'boolean';
  }

  if (stringTypes.includes(normalizedType)) {
    return 'string';
  }

  return 'default';
};

function ResultSummaryCard({ label, value, hint }) {
  return (
    <div className="metric-card">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-bold text-white">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
    </div>
  );
}

export default function RuleBuilder() {
  const {
    schemaMetadata,
    selectedDataset,
    datasetRows,
    validationResults,
    setValidationResults,
    pushToast,
  } = useDataset();

  const [selectedColumn, setSelectedColumn] = useState('');
  const [selectedRule, setSelectedRule] = useState('between');
  const [params, setParams] = useState({
    min: '',
    max: '',
    pattern: '',
  });
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [compatibilityNotice, setCompatibilityNotice] = useState('');
  const [resultsHighlighted, setResultsHighlighted] = useState(false);
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const resultsSectionRef = useRef(null);
  const resultsHighlightTimeoutRef = useRef(null);

  useEffect(() => {
    if (!selectedColumn && schemaMetadata[0]?.columnName) {
      setSelectedColumn(schemaMetadata[0].columnName);
    }
  }, [schemaMetadata, selectedColumn]);

  useEffect(
    () => () => {
      if (resultsHighlightTimeoutRef.current) {
        window.clearTimeout(resultsHighlightTimeoutRef.current);
      }
    },
    [],
  );

  const selectedColumnMeta = useMemo(
    () =>
      schemaMetadata.find((column) => column.columnName === selectedColumn) || null,
    [schemaMetadata, selectedColumn],
  );

  const selectedColumnType = selectedColumnMeta?.dataType || 'unknown';
  const selectedColumnTypeGroup = toColumnTypeGroup(selectedColumnType);
  const applicableRuleIds =
    applicableRulesByType[selectedColumnTypeGroup] ||
    applicableRulesByType.default;

  useEffect(() => {
    if (!selectedColumnMeta || applicableRuleIds.includes(selectedRule)) {
      return;
    }

    const fallbackRule = applicableRuleIds[0] || 'not_null';

    setSelectedRule(fallbackRule);
    setCompatibilityNotice(
      `${getRuleLabel(selectedRule)} is not applicable for ${selectedColumnType} columns. Switched to ${getRuleLabel(fallbackRule)}.`,
    );
  }, [applicableRuleIds, selectedColumnMeta, selectedColumnType, selectedRule]);

  const validationIssues = useMemo(() => {
    const issues = {};

    if (!selectedDataset) {
      issues.dataset = 'Upload a dataset to start validation.';
    }

    if (!schemaMetadata.length) {
      issues.schema = 'Schema metadata is required before validation can run.';
    }

    if (!selectedColumn) {
      issues.column = 'Choose a target column before running validation.';
    }

    if (!selectedRule) {
      issues.ruleSelection = 'Choose a rule before running validation.';
    }

    if (
      selectedColumnMeta &&
      !applicableRuleIds.includes(selectedRule)
    ) {
      issues.rule = `This rule is not applicable for ${selectedColumnType} columns.`;
    }

    if (selectedRule === 'between') {
      if (params.min === '') {
        issues.min = 'Enter a minimum value.';
      }

      if (params.max === '') {
        issues.max = 'Enter a maximum value.';
      }

      if (
        params.min !== '' &&
        params.max !== '' &&
        !Number.isNaN(Number(params.min)) &&
        !Number.isNaN(Number(params.max)) &&
        Number(params.min) > Number(params.max)
      ) {
        issues.range = 'Minimum cannot be greater than maximum.';
      }
    }

    if (selectedRule === 'regex') {
      if (!params.pattern.trim()) {
        issues.pattern = 'Provide a regex pattern before running validation.';
      } else {
        try {
          new RegExp(params.pattern.trim());
        } catch {
          issues.pattern = 'Provide a valid regex pattern.';
        }
      }
    }

    return issues;
  }, [
    applicableRuleIds,
    params.max,
    params.min,
    params.pattern,
    schemaMetadata.length,
    selectedColumn,
    selectedColumnMeta,
    selectedColumnType,
    selectedDataset,
    selectedRule,
  ]);

  const primaryValidationMessage =
    validationIssues.dataset ||
    validationIssues.schema ||
    validationIssues.column ||
    validationIssues.ruleSelection ||
    validationIssues.rule ||
    validationIssues.range ||
    validationIssues.min ||
    validationIssues.max ||
    validationIssues.pattern ||
    '';

  const canRunValidation =
    !loading &&
    selectedDataset &&
    schemaMetadata.length > 0 &&
    !primaryValidationMessage;

  const filteredRows = useMemo(() => {
    const rows = validationResults?.failedRows || [];
    const normalizedSearch = deferredSearchTerm.trim().toLowerCase();

    if (!normalizedSearch) {
      return rows;
    }

    return rows.filter((row) =>
      [row.rowId, row.column, row.message, row.value]
        .filter(Boolean)
        .some((field) =>
          String(field).toLowerCase().includes(normalizedSearch),
        ),
    );
  }, [deferredSearchTerm, validationResults]);

  const buildPayload = () => {
    if (primaryValidationMessage) {
      throw new Error(primaryValidationMessage);
    }

    const payload = {
      dataset_id: selectedDataset?.id,
      column: selectedColumn,
      rule: selectedRule,
    };

    if (selectedRule === 'between') {
      return {
        ...payload,
        min: Number(params.min),
        max: Number(params.max),
      };
    }

    if (selectedRule === 'regex') {
      return {
        ...payload,
        pattern: params.pattern.trim(),
      };
    }

    return payload;
  };

  const revealResultsSection = () => {
    window.setTimeout(() => {
      resultsSectionRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
      resultsSectionRef.current?.focus({ preventScroll: true });
      setResultsHighlighted(true);

      if (resultsHighlightTimeoutRef.current) {
        window.clearTimeout(resultsHighlightTimeoutRef.current);
      }

      resultsHighlightTimeoutRef.current = window.setTimeout(() => {
        setResultsHighlighted(false);
      }, 1800);
    }, 120);
  };

  const handleRunValidation = async () => {
    setLoading(true);

    try {
      const payload = buildPayload();
      const response = await runValidation(payload, datasetRows);

      setValidationResults(response);
      revealResultsSection();

      pushToast({
        tone: 'success',
        title: 'Validation completed successfully',
        message: `${response.summary?.failedRows || 0} rows were flagged for review.`,
      });
    } catch (error) {
      pushToast({
        tone: 'error',
        title: 'Validation failed',
        message:
          error.message ||
          'We could not run the rule. Review the selected parameters.',
      });
    } finally {
      setLoading(false);
    }
  };

  const noFailedRowsInRun =
    validationResults &&
    (validationResults.summary?.failedRows || 0) === 0 &&
    !deferredSearchTerm.trim();

  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr] xl:gap-6">
      <section className="glass-panel p-4 sm:p-6">
        <div className="border-b border-white/10 pb-6">
          <p className="section-kicker">Author Rule</p>
          <h3 className="mt-3 text-2xl font-semibold text-white">
            Configure a validation check
          </h3>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Rule suggestions are now filtered by the selected column type so the
            builder only presents checks that make sense for the active schema.
          </p>
        </div>

        <div className="mt-6 space-y-6">
          <div className="subtle-card">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="field-label mb-0" htmlFor="rule-column">
                Target Column
              </label>
              {selectedColumnMeta && (
                <StatusBadge tone="pending">
                  {selectedColumnMeta.dataType}
                </StatusBadge>
              )}
            </div>
            <select
              id="rule-column"
              value={selectedColumn}
              onChange={(event) => {
                setSelectedColumn(event.target.value);
                setCompatibilityNotice('');
              }}
              className={`input-shell ${validationIssues.column ? 'input-shell-error' : ''}`}
              title="Choose the column you want to validate."
            >
              {!schemaMetadata.length && (
                <option value="">No schema available yet</option>
              )}
              {schemaMetadata.map((column) => (
                <option key={column.columnName} value={column.columnName}>
                  {`${column.columnName} (${column.dataType})`}
                </option>
              ))}
            </select>
            {validationIssues.column ? (
              <p className="field-error">{validationIssues.column}</p>
            ) : (
              <p className="field-hint">
                {selectedColumnMeta
                  ? `Selected column ${selectedColumnMeta.columnName} is typed as ${selectedColumnMeta.dataType}.`
                  : 'Pick a schema column to see the recommended rule set.'}
              </p>
            )}
          </div>

          {selectedColumnMeta && (
            <div className="subtle-card">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {selectedColumnMeta.columnName}
                  </p>
                  <p className="field-hint">
                    Available rules: {applicableRuleIds.map(getRuleLabel).join(', ')}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                    Null Count
                  </p>
                  <p className="mt-2 text-lg font-bold text-white">
                    {selectedColumnMeta.nullCount}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="field-label mb-0">Rule Type</p>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Data-type aware recommendations
              </p>
            </div>
            <div className="mt-3 space-y-3">
              {ruleOptions.map((ruleOption) => {
                const isActive = selectedRule === ruleOption.id;
                const isApplicable = applicableRuleIds.includes(ruleOption.id);

                return (
                  <button
                    key={ruleOption.id}
                    type="button"
                    onClick={() => {
                      if (!isApplicable) {
                        return;
                      }

                      setSelectedRule(ruleOption.id);
                      setCompatibilityNotice('');
                    }}
                    disabled={!isApplicable}
                    title={ruleOption.tooltip}
                    className={`selection-card w-full ${
                      isActive ? 'selection-card-active' : ''
                    } ${!isApplicable ? 'cursor-not-allowed opacity-50' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-base font-semibold text-white">
                            {ruleOption.label}
                          </p>
                          <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-slate-300">
                            {ruleOption.supportedLabel}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-400">
                          {ruleOption.description}
                        </p>
                        {!isApplicable && (
                          <p className="field-error">
                            This rule is not applicable for the selected column type.
                          </p>
                        )}
                      </div>
                      <span
                        className={`mt-1 h-2.5 w-2.5 rounded-full ${
                          isActive ? 'bg-cyan-300' : 'bg-slate-600'
                        }`}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
            {compatibilityNotice && (
              <div className="inline-banner inline-banner-info mt-4" role="status">
                {compatibilityNotice}
              </div>
            )}
          </div>

          {selectedRule === 'between' && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="subtle-card">
                <label className="field-label" htmlFor="rule-min">
                  Minimum
                </label>
                <input
                  id="rule-min"
                  type="number"
                  value={params.min}
                  onChange={(event) =>
                    setParams((current) => ({
                      ...current,
                      min: event.target.value,
                    }))
                  }
                  placeholder="0"
                  title="Example: 0"
                  className={`input-shell ${
                    validationIssues.min || validationIssues.range
                      ? 'input-shell-error'
                      : ''
                  }`}
                />
                {(validationIssues.min || validationIssues.range) && (
                  <p className="field-error">
                    {validationIssues.min || validationIssues.range}
                  </p>
                )}
              </div>
              <div className="subtle-card">
                <label className="field-label" htmlFor="rule-max">
                  Maximum
                </label>
                <input
                  id="rule-max"
                  type="number"
                  value={params.max}
                  onChange={(event) =>
                    setParams((current) => ({
                      ...current,
                      max: event.target.value,
                    }))
                  }
                  placeholder="1000"
                  title="Example: 1000"
                  className={`input-shell ${
                    validationIssues.max || validationIssues.range
                      ? 'input-shell-error'
                      : ''
                  }`}
                />
                {(validationIssues.max || validationIssues.range) && (
                  <p className="field-error">
                    {validationIssues.max || validationIssues.range}
                  </p>
                )}
              </div>
            </div>
          )}

          {selectedRule === 'regex' && (
            <div className="subtle-card">
              <label className="field-label" htmlFor="rule-pattern">
                Regex Pattern
              </label>
              <input
                id="rule-pattern"
                type="text"
                value={params.pattern}
                onChange={(event) =>
                  setParams((current) => ({
                    ...current,
                    pattern: event.target.value,
                  }))
                }
                placeholder="^[A-Z_]+$"
                title="Example: ^[A-Z_]+$"
                className={`input-shell ${validationIssues.pattern ? 'input-shell-error' : ''}`}
              />
              {validationIssues.pattern ? (
                <p className="field-error">{validationIssues.pattern}</p>
              ) : (
                <p className="field-hint">
                  Example: `^[A-Z_]+$` matches uppercase status codes.
                </p>
              )}
            </div>
          )}

          {selectedRule === 'not_null' && (
            <div className="subtle-card">
              <p className="text-sm font-semibold text-white">No parameters required</p>
              <p className="field-hint">
                This rule verifies that the selected column contains a value for
                every inspected record.
              </p>
            </div>
          )}

          {primaryValidationMessage && (
            <div className="inline-banner inline-banner-error" role="alert">
              {primaryValidationMessage}
            </div>
          )}

          <div className="subtle-card">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
              Payload Preview
            </p>
            <pre className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/75 p-4 text-xs leading-6 text-slate-300">
{JSON.stringify(
  (() => {
    try {
      return buildPayload();
    } catch {
      return {
        column: selectedColumn,
        rule: selectedRule,
      };
    }
  })(),
  null,
  2,
)}
            </pre>
          </div>

          <button
            type="button"
            onClick={handleRunValidation}
            disabled={!canRunValidation}
            title={
              canRunValidation
                ? 'Run the selected validation rule against the active dataset.'
                : primaryValidationMessage || 'Load a dataset to start validation.'
            }
            className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <Loader label="Running validation" compact />
            ) : (
              'Run Validation'
            )}
          </button>
        </div>
      </section>

      <section
        ref={resultsSectionRef}
        tabIndex={-1}
        className={`glass-panel p-4 outline-none transition-all duration-500 sm:p-6 ${
          resultsHighlighted ? 'section-focus-flash' : ''
        }`}
      >
        <div className="flex flex-col gap-4 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-kicker">Validation Results</p>
            <h3 className="mt-3 text-2xl font-semibold text-white">
              Failed rows and operational detail
            </h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
              After each run, the builder scrolls you directly into the results
              section so you can review failures, triage severity, and jump to the
              observability dashboard without losing context.
            </p>
          </div>

          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            {validationResults?.summary && (
              <div className="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 sm:w-auto">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Last Run
                </p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {validationResults.summary.executionTime} on{' '}
                  {validationResults.summary.column}
                </p>
              </div>
            )}
            <Link
              to="/dashboard"
              className="secondary-button w-full sm:w-auto"
              title="Open the observability dashboard for aggregate signals."
            >
              Open Dashboard
            </Link>
          </div>
        </div>

        {validationResults ? (
          <div className="mt-6 space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <ResultSummaryCard
                label="Checked Rows"
                value={validationResults.summary?.checkedRows || 0}
                hint="Records evaluated in this run"
              />
              <ResultSummaryCard
                label="Passed Rows"
                value={validationResults.summary?.passedRows || 0}
                hint="Rows meeting rule expectations"
              />
              <ResultSummaryCard
                label="Failed Rows"
                value={validationResults.summary?.failedRows || 0}
                hint="Rows requiring review"
              />
            </div>

            <div className="subtle-card">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="field-label mb-0">Search Failed Rows</p>
                  <p className="field-hint">
                    Filter by row id, column, value, or error message.
                  </p>
                </div>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search failed rows"
                  title="Search within the current failed-row result set."
                  className="input-shell w-full sm:max-w-xs"
                />
              </div>
            </div>

            <div className="table-shell">
              <div className="table-scroll max-h-[480px]">
                <table className="data-table">
                  <thead className="data-table-head">
                    <tr>
                      <th className="data-table-header-cell">Row ID</th>
                      <th className="data-table-header-cell">Column</th>
                      <th className="data-table-header-cell">Value</th>
                      <th className="data-table-header-cell">Error Message</th>
                      <th className="data-table-header-cell">Severity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filteredRows.map((row) => (
                      <tr
                        key={row.rowId}
                        className="data-table-row-danger bg-rose-500/[0.03]"
                      >
                        <td className="data-table-cell font-semibold text-white">
                          {row.rowId}
                        </td>
                        <td className="data-table-cell">{row.column}</td>
                        <td className="data-table-cell text-rose-100">{row.value}</td>
                        <td className="data-table-cell">{row.message}</td>
                        <td className="data-table-cell">
                          <span
                            className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                              severityClasses[row.severity] || severityClasses.medium
                            }`}
                          >
                            {row.severity}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {!filteredRows.length && (
              <div className="empty-state min-h-[180px]">
                <p className="text-lg font-semibold text-white">
                  {noFailedRowsInRun ? 'No failed rows detected' : 'No matching failed rows'}
                </p>
                <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
                  {noFailedRowsInRun
                    ? 'This validation run completed successfully. Open the dashboard for the aggregate quality view or run another rule for a different column.'
                    : 'Adjust the search term or rerun the rule to inspect a different slice of the failures.'}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-state mt-6">
            <p className="text-lg font-semibold text-white">
              Validation results will appear here
            </p>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
              Load a dataset, select a compatible rule, and run validation to see
              failed rows, error messages, and execution metrics.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
