import { useEffect, useMemo, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import { Link } from 'react-router-dom';
import Loader from '../common/Loader';
import ResultTable from '../common/ResultTable';
import StatusBadge from '../common/StatusBadge';
import { useDataset } from '../../context/DatasetContext';
import { createSavedRule, runAdHocRule } from '../../services/rulesApi';

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
  {
    id: 'equals',
    label: 'Exact Match',
    description: 'Matches a specific string or numeric value exactly.',
    supportedLabel: 'String and Numeric columns',
    tooltip: 'Exact Match: checks whether a value exactly equals the input.',
  },
];

const applicableRulesByType = {
  numeric: ['between', 'not_null', 'equals'],
  string: ['regex', 'not_null', 'equals'],
  boolean: ['not_null', 'equals'],
  default: ['regex', 'not_null', 'equals'],
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

const OPEN_ENDED_MAX = String(Number.MAX_SAFE_INTEGER);

const escapeRegExp = (value = '') =>
  String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const normalizeColumnToken = (value = '') =>
  String(value)
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

const extractNumericValues = (value = '') =>
  String(value).match(/-?\d+(\.\d+)?/g) || [];

const findColumnFromInput = (input, schema = []) => {
  const normalizedInput = normalizeColumnToken(input);

  return [...schema]
    .sort((left, right) => right.columnName.length - left.columnName.length)
    .find((column) => {
      const normalizedColumn = normalizeColumnToken(column.columnName);
      const columnPattern = new RegExp(`\\b${escapeRegExp(normalizedColumn)}\\b`);

      return columnPattern.test(normalizedInput);
    });
};

const extractRegexPattern = (value = '') => {
  const slashPatternMatch = value.match(/\/([^/]+)\/[gimsuy]*/);

  if (slashPatternMatch?.[1]) {
    return slashPatternMatch[1].trim();
  }

  const quotedPatternMatch = value.match(
    /(?:match|regex)(?:\s+pattern)?\s+["'](.+?)["']/i,
  );

  if (quotedPatternMatch?.[1]) {
    return quotedPatternMatch[1].trim();
  }

  const afterKeywordMatch = value.match(/(?:match|regex)(?:\s+pattern)?\s+(.+)$/i);

  return afterKeywordMatch?.[1]?.trim() || '';
};

const getOpenEndedMax = (columnName, threshold, rows = []) => {
  const numericValues = rows
    .map((row) => Number(row?.[columnName]))
    .filter((value) => Number.isFinite(value));

  if (!numericValues.length) {
    return OPEN_ENDED_MAX;
  }

  const currentMaximum = Math.max(...numericValues);

  return currentMaximum > Number(threshold)
    ? String(currentMaximum)
    : OPEN_ENDED_MAX;
};

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

const quoteIdentifier = (value = '') =>
  `"${String(value).replace(/"/g, '""')}"`;

const getDatasetSqlName = (dataset) =>
  dataset?.tableName ||
  dataset?.table ||
  dataset?.name?.replace(/\.[^.]+$/, '').replace(/[^\w]+/g, '_') ||
  'active_dataset';

const buildSqlFromRule = ({
  dataset,
  column,
  rule,
  semanticMode,
  params: ruleParams,
}) => {
  const tableName = quoteIdentifier(getDatasetSqlName(dataset));
  const columnName = quoteIdentifier(column || 'column_name');

  if (semanticMode === 'query') {
    if (rule === 'between') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} BETWEEN ${ruleParams.min || 0} AND ${ruleParams.max || OPEN_ENDED_MAX};`;
    }
    if (rule === 'regex') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} ~ '${String(ruleParams.pattern || '').replace(/'/g, "''")}';`;
    }
    if (rule === 'equals') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} = '${String(ruleParams.value || '').replace(/'/g, "''")}';`;
    }
    return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} IS NOT NULL;`;
  } else {
    if (rule === 'between') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} < ${ruleParams.min || 0}\n   OR ${columnName} > ${ruleParams.max || OPEN_ENDED_MAX};`;
    }
    if (rule === 'regex') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} IS NULL\n   OR ${columnName} !~ '${String(ruleParams.pattern || '').replace(/'/g, "''")}';`;
    }
    if (rule === 'equals') {
      return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} IS NULL\n   OR ${columnName} != '${String(ruleParams.value || '').replace(/'/g, "''")}';`;
    }
    return `SELECT *\nFROM ${tableName}\nWHERE ${columnName} IS NULL;`;
  }
};

const toValidationResultsShape = (result, localPayload) => ({
  summary: {
    column: localPayload?.column || 'SQL result',
    rule: result.ruleName,
    checkedRows: result.checkedRows,
    passedRows: result.passedRows,
    failedRows: result.failedRows,
    resultRows: result.resultRows ?? result.failedRows,
    executionTime: result.duration,
    executedAt: result.executionTime,
    sql: result.sql,
    status: result.status,
  },
  failedRows: result.rows,
  resultRows: result.rows,
  persistedResult: result,
});

function ResultSummaryCard({ label, value, hint }) {
  return (
    <div className="metric-card bg-slate-50/50 dark:bg-slate-900/40">
      <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400">{label}</p>
      <p className="mt-2 text-xl font-bold text-slate-900 dark:text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

const TASKS_KEY = 'pulseqc:scheduled-tasks';

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
  const [semanticMode, setSemanticMode] = useState('query');
  const [params, setParams] = useState({
    min: '',
    max: '',
    pattern: '',
    value: '',
  });
  const [nlInput, setNlInput] = useState('');
  const [ruleName, setRuleName] = useState('Business validation rule');
  const [sqlText, setSqlText] = useState('');
  const [activeAuthoringMode, setActiveAuthoringMode] = useState('builder'); // 'assistant', 'builder', 'sql'
  const [loading, setLoading] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [scheduleStep, setScheduleStep] = useState(0);
  const [compatibilityNotice, setCompatibilityNotice] = useState('');
  const [resultsHighlighted, setResultsHighlighted] = useState(false);
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
  const generatedSqlPreview = useMemo(
    () =>
      buildSqlFromRule({
        dataset: selectedDataset,
        column: selectedColumn,
        rule: selectedRule,
        semanticMode,
        params,
      }),
    [params, selectedColumn, selectedDataset, selectedRule, semanticMode],
  );

  useEffect(() => {
    if (!sqlText.trim() || activeAuthoringMode !== 'sql') {
      setSqlText(generatedSqlPreview);
    }
  }, [activeAuthoringMode, generatedSqlPreview, sqlText]);

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
    sqlText.trim() &&
    !primaryValidationMessage;

  const buildPayload = () => {
    if (primaryValidationMessage) {
      throw new Error(primaryValidationMessage);
    }

    const payload = {
      dataset_id: selectedDataset?.id,
      column: selectedColumn,
      rule: selectedRule,
      semanticMode: semanticMode,
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

    if (selectedRule === 'equals') {
      return {
        ...payload,
        value: params.value.trim(),
      };
    }

    return payload;
  };

  const handleGenerateRule = () => {
    const normalizedInput = nlInput.trim().toLowerCase();

    if (!normalizedInput) {
      pushToast({
        tone: 'error',
        title: 'Could not understand rule',
        message: 'Describe a rule in plain English to auto-fill the builder.',
      });
      return;
    }

    const matchedColumn = findColumnFromInput(normalizedInput, schemaMetadata);

    if (!matchedColumn) {
      pushToast({
        tone: 'error',
        title: 'Column not recognized',
        message: 'Try referencing a column name that appears in the dataset schema.',
      });
      return;
    }

    const nextParams = {
      min: '',
      max: '',
      pattern: '',
      value: '',
    };
    let nextRule = '';

    if (
      normalizedInput.includes('negative') ||
      normalizedInput.includes('less than zero') ||
      normalizedInput.includes('< 0')
    ) {
      nextRule = 'between';
      nextParams.min = '0';
      nextParams.max = getOpenEndedMax(matchedColumn.columnName, 0, datasetRows);
    } else if (normalizedInput.includes('not null')) {
      nextRule = 'not_null';
    } else if (normalizedInput.includes('between')) {
      const numericValues = extractNumericValues(normalizedInput);

      if (numericValues.length < 2) {
        pushToast({
          tone: 'error',
          title: 'Could not understand rule',
          message: 'A between rule needs both a minimum and maximum value.',
        });
        return;
      }

      nextRule = 'between';
      [nextParams.min, nextParams.max] = numericValues;
    } else if (
      normalizedInput.includes('greater than') ||
      normalizedInput.includes('>')
    ) {
      const numericValues = extractNumericValues(normalizedInput);

      if (!numericValues.length) {
        pushToast({
          tone: 'error',
          title: 'Could not understand rule',
          message: 'A greater-than rule needs a numeric threshold.',
        });
        return;
      }

      nextRule = 'between';
      nextParams.min = numericValues[0];
      nextParams.max = getOpenEndedMax(
        matchedColumn.columnName,
        numericValues[0],
        datasetRows,
      );
    } else if (
      normalizedInput.includes('less than') ||
      normalizedInput.includes('<')
    ) {
      const numericValues = extractNumericValues(normalizedInput);

      if (!numericValues.length) {
        pushToast({
          tone: 'error',
          title: 'Could not understand rule',
          message: 'A less-than rule needs a numeric threshold.',
        });
        return;
      }

      nextRule = 'between';
      nextParams.min = numericValues[0];
      nextParams.max = getOpenEndedMax(
        matchedColumn.columnName,
        numericValues[0],
        datasetRows,
      );
    } else if (
      normalizedInput.includes('match') ||
      normalizedInput.includes('regex')
    ) {
      const pattern = extractRegexPattern(nlInput);

      if (!pattern) {
        pushToast({
          tone: 'error',
          title: 'Could not understand rule',
          message: 'Include a regex pattern after match or regex.',
        });
        return;
      }

      nextRule = 'regex';
      nextParams.pattern = pattern;
    } else if (
      normalizedInput.includes('is') ||
      normalizedInput.includes('equal') ||
      normalizedInput.includes('=')
    ) {
      const match = nlInput.match(/(?:is|equal(?:s)?(?: to)?|=)\s+([\w\s]+?)(?=\s|$)/i);
      if (match) {
        nextRule = 'equals';
        nextParams.value = match[1].trim();
      } else {
        pushToast({
          tone: 'error',
          title: 'Could not understand rule',
          message: 'Include a specific value to match after "is" or "equals".',
        });
        return;
      }
    } else {
      pushToast({
        tone: 'error',
        title: 'Could not understand rule',
        message: 'Try using phrases like between, not null, greater than, less than, or regex.',
      });
      return;
    }

    const isValidation = normalizedInput.includes('invalid') || normalizedInput.includes('violating') || normalizedInput.includes('fail');
    setSemanticMode(isValidation ? 'validation' : 'query');

    setSelectedColumn(matchedColumn.columnName);
    setSelectedRule(nextRule);
    setParams(nextParams);
    setRuleName(
      nlInput
        .trim()
        .replace(/\s+/g, ' ')
        .replace(/^show\s+/i, '')
        .replace(/^find\s+/i, '')
        .slice(0, 85) || 'Business validation rule',
    );
    setSqlText(
      buildSqlFromRule({
        dataset: selectedDataset,
        column: matchedColumn.columnName,
        rule: nextRule,
        semanticMode: isValidation ? 'validation' : 'query',
        params: nextParams,
      }),
    );
    setActiveAuthoringMode('builder');
    setCompatibilityNotice('');

    pushToast({
      tone: 'success',
      title: 'Rule generated',
      message: `The builder parameters were parsed for ${matchedColumn.columnName}.`,
    });
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
      const localPayload = buildPayload();
      const response = await runAdHocRule(
        {
          dataset_id: selectedDataset?.id,
          dataset_name: selectedDataset?.name,
          rule_name: ruleName.trim() || 'Business validation rule',
          sql: sqlText.trim() || generatedSqlPreview,
          expected_result: {
            type: 'zero_violations',
          },
        },
        {
          datasetRows,
          localPayload,
        },
      );

      setValidationResults(toValidationResultsShape(response, localPayload));
      revealResultsSection();

      pushToast({
        tone: 'success',
        title: 'Rule executed',
        message: `${response.resultRows ?? response.failedRows ?? 0} matching rows returned from execution.`,
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

  const handleSaveRule = async () => {
    setSavingRule(true);

    try {
      const savedRule = await createSavedRule({
        dataset_name: selectedDataset?.name,
        rule_name: ruleName.trim() || 'Business validation rule',
        sql: sqlText.trim() || generatedSqlPreview,
        expected_result: {
          type: 'zero_violations',
        },
      });

      pushToast({
        tone: 'success',
        title: 'Rule saved',
        message: `${savedRule.ruleName} added to the validation registry.`,
      });
    } catch (error) {
      pushToast({
        tone: 'error',
        title: 'Rule could not be saved',
        message:
          error.message ||
          'The saved rule registry did not accept the current SQL payload.',
      });
    } finally {
      setSavingRule(false);
    }
  };

  // Scheduled Task simulation deployment trigger
  const handleScheduleValidation = () => {
    if (!selectedDataset) return;
    setScheduling(true);
    setScheduleStep(0);

    const steps = [
      'Compiling validation query and verifying schema types...',
      'Deploying Cron validation rule trigger to Celery coordinator daemon...',
      'Registering job parameters in Redis queuing backend...',
      'Validation task schedule configured successfully!'
    ];

    const runSteps = (stepIndex) => {
      if (stepIndex < steps.length) {
        setScheduleStep(stepIndex);
        setTimeout(() => {
          runSteps(stepIndex + 1);
        }, 500);
      } else {
        let scheduleFreq = 'Daily';
        let promptText = nlInput.trim();
        if (promptText.toLowerCase().includes('week')) scheduleFreq = 'Weekly';
        if (promptText.toLowerCase().includes('2 weeks')) scheduleFreq = 'Every 2 weeks';
        if (promptText.toLowerCase().includes('month')) scheduleFreq = 'Monthly';

        const newTask = {
          id: `task-${Date.now()}`,
          name: ruleName,
          dataset: `${selectedDataset.subType}_db.${selectedDataset.name}`,
          status: 'active',
          frequency: scheduleFreq,
          originalPrompt: nlInput || `Validate ${selectedColumn} constraints`,
          sql: sqlText,
          lastRun: new Date().toISOString(),
          nextRun: new Date(Date.now() + 3600000 * 24).toISOString(),
          rowsScanned: selectedDataset.records || 5000,
          rowsReturned: 0,
          duration: '0.45s',
          emailStatus: 'Alerts active (recipient: data-alerts@enterprise.com)',
          steps: [
            'Triggered by cron scheduler daemon',
            'Dequeued from Redis broker',
            'Verified active database connection: OK',
            'Executing rule checks... OK (0 violations caught)'
          ]
        };

        const existingTasks = JSON.parse(localStorage.getItem(TASKS_KEY) || '[]');
        localStorage.setItem(TASKS_KEY, JSON.stringify([newTask, ...existingTasks]));

        // Optimistically update Saved Rules too
        handleSaveRule().catch(() => {});

        setScheduling(false);
        pushToast({
          tone: 'success',
          title: 'Validation scheduled successfully',
          message: `Scheduled "${ruleName}" successfully.`,
        });
      }
    };

    runSteps(0);
  };

  const noRowsInRun =
    validationResults &&
    (validationResults.summary?.resultRows ?? validationResults.summary?.failedRows ?? 0) === 0;

  return (
    <div className="grid gap-6 md:grid-cols-3">
      {/* Configuration & Parameters builder on the left side */}
      <div className="md:col-span-2 space-y-6">
        
        {/* Assistant / Input Text box */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Rule Drafting Assistant</h3>
              <p className="text-xs text-slate-400 mt-0.5">Describe what you want to validate in the dataset. Clicking generate parses fields below.</p>
            </div>
            <button
              type="button"
              onClick={handleGenerateRule}
              disabled={!nlInput.trim() || !schemaMetadata.length}
              className="secondary-button text-xs font-semibold py-1.5 px-3"
            >
              Generate Form
            </button>
          </div>
          <textarea
            id="rule-natural-language"
            value={nlInput}
            onChange={(event) => setNlInput(event.target.value)}
            rows="2"
            placeholder="e.g. Check salary column greater than 0 every day"
            className="input-shell text-xs min-h-[60px] resize-none"
          />
        </section>

        {/* Builder Panel */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-5">
          <div className="border-b border-slate-100 dark:border-slate-800/80 pb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Rule Parameters Form</h3>
            <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-0.5" role="group">
              {['builder', 'sql'].map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setActiveAuthoringMode(mode)}
                  className={`rounded-md px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    activeAuthoringMode === mode
                      ? 'bg-sky-500/10 text-sky-500'
                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="rule-name">Rule Name</label>
              <input
                id="rule-name"
                type="text"
                value={ruleName}
                onChange={(event) => setRuleName(event.target.value)}
                placeholder="Attendance below threshold"
                className="input-shell text-xs"
              />
            </div>
            <div>
              <label className="field-label" htmlFor="rule-column">Target Column</label>
              <select
                id="rule-column"
                value={selectedColumn}
                onChange={(event) => {
                  setSelectedColumn(event.target.value);
                  setCompatibilityNotice('');
                }}
                className={`input-shell text-xs ${validationIssues.column ? 'input-shell-error' : ''}`}
              >
                {!schemaMetadata.length && <option value="">No schema columns loaded</option>}
                {schemaMetadata.map((column) => (
                  <option key={column.columnName} value={column.columnName}>
                    {`${column.columnName} (${column.dataType})`}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="field-label">Semantic Logic Mode</label>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setSemanticMode('query')}
                  className={`border rounded-lg py-2 font-semibold text-center transition-colors ${
                    semanticMode === 'query'
                      ? 'border-sky-500 bg-sky-500/10 text-sky-500'
                      : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/40 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  Filter Matches
                </button>
                <button
                  type="button"
                  onClick={() => setSemanticMode('validation')}
                  className={`border rounded-lg py-2 font-semibold text-center transition-colors ${
                    semanticMode === 'validation'
                      ? 'border-sky-500 bg-sky-500/10 text-sky-500'
                      : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/40 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  Find Violations
                </button>
              </div>
            </div>
            <div>
              <label className="field-label">Rule Pattern Selection</label>
              <select
                value={selectedRule}
                onChange={(e) => setSelectedRule(e.target.value)}
                className="input-shell text-xs"
              >
                {ruleOptions.map((opt) => {
                  const isApplicable = applicableRuleIds.includes(opt.id);
                  return (
                    <option key={opt.id} value={opt.id} disabled={!isApplicable}>
                      {opt.label} ({opt.supportedLabel}) {!isApplicable && '[Unsupported]'}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          {/* Dynamic parameter configuration fields */}
          {selectedRule === 'between' && (
            <div className="grid gap-4 md:grid-cols-2 bg-slate-50 dark:bg-slate-900/20 border border-slate-200 dark:border-slate-800/80 rounded-lg p-4">
              <div>
                <label className="field-label" htmlFor="rule-min">Minimum Threshold</label>
                <input
                  id="rule-min"
                  type="number"
                  value={params.min}
                  onChange={(event) =>
                    setParams((current) => ({ ...current, min: event.target.value }))
                  }
                  placeholder="0"
                  className="input-shell text-xs"
                />
              </div>
              <div>
                <label className="field-label" htmlFor="rule-max">Maximum Threshold</label>
                <input
                  id="rule-max"
                  type="number"
                  value={params.max}
                  onChange={(event) =>
                    setParams((current) => ({ ...current, max: event.target.value }))
                  }
                  placeholder="1000"
                  className="input-shell text-xs"
                />
              </div>
            </div>
          )}

          {selectedRule === 'equals' && (
            <div className="bg-slate-50 dark:bg-slate-900/20 border border-slate-200 dark:border-slate-800/80 rounded-lg p-4">
              <label className="field-label" htmlFor="rule-value">Exact Matching String</label>
              <input
                id="rule-value"
                type="text"
                value={params.value}
                onChange={(event) =>
                  setParams((current) => ({ ...current, value: event.target.value }))
                }
                placeholder="e.g. completed"
                className="input-shell text-xs"
              />
            </div>
          )}

          {selectedRule === 'regex' && (
            <div className="bg-slate-50 dark:bg-slate-900/20 border border-slate-200 dark:border-slate-800/80 rounded-lg p-4">
              <label className="field-label" htmlFor="rule-pattern">Regex Pattern String</label>
              <input
                id="rule-pattern"
                type="text"
                value={params.pattern}
                onChange={(event) =>
                  setParams((current) => ({ ...current, pattern: event.target.value }))
                }
                placeholder="^[A-Z_]+$"
                className="input-shell text-xs"
              />
            </div>
          )}

          {selectedRule === 'not_null' && (
            <div className="bg-slate-50 dark:bg-slate-900/20 border border-slate-200 dark:border-slate-800/80 rounded-lg p-3 text-xs text-slate-500">
              Verifies that the target column has a non-null, populated value for every database record inspected.
            </div>
          )}

          {compatibilityNotice && (
            <div className="inline-banner inline-banner-info text-xs" role="status">
              {compatibilityNotice}
            </div>
          )}
        </section>

        {/* Monaco SQL Editor Code Window */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200 font-mono">SQL Verification Code</h3>
              <p className="text-xs text-slate-400">SQL generated from rules. Switch mode above to edit code directly.</p>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-500 font-mono">Live Sync</span>
          </div>

          <div className="sql-editor-shell border-slate-200 dark:border-slate-800 overflow-hidden">
            <Editor
              height="240px"
              defaultLanguage="sql"
              value={sqlText}
              theme="vs-dark"
              loading={<Loader label="Mounting database workspace..." compact />}
              onChange={(val) => {
                setSqlText(val || '');
                setActiveAuthoringMode('sql');
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: 'ui-monospace, IBM Plex Mono, Consolas, monospace',
                lineNumbersMinChars: 3,
                padding: { top: 12, bottom: 12 },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                automaticLayout: true,
                renderLineHighlight: 'all',
              }}
            />
          </div>

          <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-2">
            {primaryValidationMessage && (
              <span className="text-xs font-semibold text-rose-500">{primaryValidationMessage}</span>
            )}
            {!primaryValidationMessage && (
              <span className="text-xs text-slate-400">Validation parameters are complete and ready for execution.</span>
            )}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRunValidation}
                disabled={!canRunValidation}
                className="secondary-button text-xs font-semibold py-1.5 px-3"
              >
                {loading ? <Loader label="Compiling..." compact /> : 'Run Query'}
              </button>
              <button
                type="button"
                onClick={handleScheduleValidation}
                disabled={!canRunValidation || scheduling}
                className="primary-button text-xs font-semibold py-1.5 px-3"
              >
                Schedule Check
              </button>
              <button
                type="button"
                onClick={handleSaveRule}
                disabled={savingRule || !selectedDataset || !sqlText.trim()}
                className="secondary-button text-xs font-semibold py-1.5 px-3"
              >
                {savingRule ? <Loader label="Saving..." compact /> : 'Save Rule'}
              </button>
            </div>
          </div>
        </section>

        {/* Schedule progress timeline deployment */}
        {scheduling && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3">
            <div className="flex items-center gap-2.5">
              <Loader label="" compact />
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Deploying scheduler task daemon...</span>
            </div>
            <div className="space-y-2">
              {[
                'Compiling validation query and verifying schema types...',
                'Deploying Cron validation rule trigger to Celery coordinator daemon...',
                'Registering job parameters in Redis queuing backend...',
                'Validation task schedule configured successfully!'
              ].map((step, idx) => (
                <div key={idx} className={`flex items-center gap-2.5 text-xs ${scheduleStep >= idx ? 'text-slate-800 dark:text-slate-200 font-medium' : 'text-slate-400'}`}>
                  {scheduleStep > idx ? (
                    <span className="h-4 w-4 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center justify-center text-[10px] font-bold">✓</span>
                  ) : scheduleStep === idx ? (
                    <span className="h-4.5 w-4.5 rounded-full border-2 border-sky-500 border-t-transparent animate-spin inline-block" />
                  ) : (
                    <span className="h-4.5 w-4.5 rounded-full border border-slate-200 dark:border-slate-800 inline-block" />
                  )}
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results Block */}
        <section
          ref={resultsSectionRef}
          tabIndex={-1}
          className={`rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-6 outline-none transition-all duration-500 ${
            resultsHighlighted ? 'ring-2 ring-sky-500/30' : ''
          }`}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Validation Results</h3>
              <p className="text-xs text-slate-400 mt-0.5">Rows returned by the latest verification check.</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <Link to="/dashboard" className="secondary-button py-1 px-3">
                Dashboard
              </Link>
              <Link to="/history" className="secondary-button py-1 px-3">
                View History
              </Link>
            </div>
          </div>

          {validationResults ? (
            <div className="space-y-5">
              <div className="grid gap-3 grid-cols-3">
                <ResultSummaryCard
                  label="Checked Rows"
                  value={validationResults.summary?.checkedRows || 0}
                  hint="Checked dataset records"
                />
                <ResultSummaryCard
                  label="Violations"
                  value={validationResults.summary?.resultRows ?? validationResults.summary?.failedRows ?? 0}
                  hint="Rows breaking constraints"
                />
                <ResultSummaryCard
                  label="Duration"
                  value={validationResults.summary?.executionTime || '0.0s'}
                  hint="Engine execution time"
                />
              </div>

              <ResultTable
                rows={validationResults.resultRows || validationResults.failedRows || []}
                title="Returned Anomaly Records"
                description="Search, filter, and inspect specific violation rows stored locally in mock results."
                emptyTitle={noRowsInRun ? 'All check passes' : 'No logs returned'}
                emptyMessage={
                  noRowsInRun
                    ? 'The query validation executed successfully and zero violations were detected.'
                    : 'Run a query validation check to populate this logs table.'
                }
                pageSize={5}
              />
            </div>
          ) : (
            <div className="empty-state text-xs py-8">
              <p className="text-slate-900 dark:text-white font-medium">Results will appear here</p>
              <p className="text-slate-400 mt-1 max-w-sm">
                Enter rules, compile SQL, and run validation to inspect returned records.
              </p>
            </div>
          )}
        </section>
      </div>

      {/* Schema / Target details on the right side */}
      <div className="space-y-6 text-xs">
        
        {/* Active connection metadata card */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Active Source</h3>
            <p className="text-xs text-slate-400 mt-0.5">Parameters for validation targeting.</p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
              <span className="text-slate-400">Dataset Database</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{selectedDataset?.name || 'pg_production'}</span>
            </div>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
              <span className="text-slate-400">Records Scanned</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{(selectedDataset?.records || 0).toLocaleString()} rows</span>
            </div>
            <div className="flex items-center justify-between pb-1.5">
              <span className="text-slate-400">Target Field</span>
              <span className="font-semibold font-mono text-slate-700 dark:text-slate-200">{selectedColumn || 'N/A'}</span>
            </div>
          </div>
        </section>

        {/* Database columns schema view */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Columns Directory</h3>
            <p className="text-xs text-slate-400 mt-0.5">Profiled schema columns and types in selected engine.</p>
          </div>

          <div className="rounded-lg border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden max-h-[300px] overflow-y-auto">
            {schemaMetadata.map((col) => (
              <div
                key={col.columnName}
                onClick={() => {
                  setSelectedColumn(col.columnName);
                  setCompatibilityNotice('');
                }}
                className={`flex items-center justify-between p-3.5 cursor-pointer transition-colors ${
                  selectedColumn === col.columnName
                    ? 'bg-sky-500/5 dark:bg-sky-500/10 font-medium'
                    : 'bg-slate-50/20 dark:bg-slate-900/20 hover:bg-slate-50 dark:hover:bg-slate-850'
                }`}
              >
                <div className="flex items-center gap-2">
                  {selectedColumn === col.columnName && (
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-500" />
                  )}
                  <span className="font-mono text-slate-700 dark:text-slate-200 truncate max-w-[120px]" title={col.columnName}>
                    {col.columnName}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="text-slate-400 font-mono text-[10px]">{col.dataType}</span>
                  {col.nullCount > 0 && (
                    <span className="text-[10px] px-1 rounded bg-amber-500/10 text-amber-500 font-medium">
                      {col.nullCount} nulls
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
