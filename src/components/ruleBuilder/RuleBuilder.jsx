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

const quoteQualifiedIdentifier = (value = '') =>
  String(value || 'business_data.employees')
    .split('.')
    .filter(Boolean)
    .map(quoteIdentifier)
    .join('.');

const getDatasetSqlName = (dataset) =>
  dataset?.tableName ||
  dataset?.table ||
  dataset?.name?.replace(/\.[^.]+$/, '').replace(/[^\w]+/g, '_') ||
  'business_data.employees';

const buildSqlFromRule = ({
  dataset,
  column,
  rule,
  semanticMode,
  params: ruleParams,
}) => {
  const tableName = quoteQualifiedIdentifier(getDatasetSqlName(dataset));
  const columnName = quoteIdentifier(column || 'column_name');

  if (semanticMode === 'query') {
    if (rule === 'between') {
      return `SELECT COUNT(*) AS observed_value\nFROM ${tableName}\nWHERE ${columnName} BETWEEN ${ruleParams.min || 0} AND ${ruleParams.max || OPEN_ENDED_MAX};`;
    }
    if (rule === 'regex') {
      return `SELECT COUNT(*) AS observed_value\nFROM ${tableName}\nWHERE ${columnName} ~ '${String(ruleParams.pattern || '').replace(/'/g, "''")}';`;
    }
    if (rule === 'equals') {
      return `SELECT COUNT(*) AS observed_value\nFROM ${tableName}\nWHERE ${columnName} = '${String(ruleParams.value || '').replace(/'/g, "''")}';`;
    }
    return `SELECT COUNT(*) AS observed_value\nFROM ${tableName}\nWHERE ${columnName} IS NOT NULL;`;
  } else {
    if (rule === 'between') {
      return `SELECT COUNT(*) AS violation_count\nFROM ${tableName}\nWHERE ${columnName} < ${ruleParams.min || 0}\n   OR ${columnName} > ${ruleParams.max || OPEN_ENDED_MAX};`;
    }
    if (rule === 'regex') {
      return `SELECT COUNT(*) AS violation_count\nFROM ${tableName}\nWHERE ${columnName} IS NULL\n   OR ${columnName} !~ '${String(ruleParams.pattern || '').replace(/'/g, "''")}';`;
    }
    if (rule === 'equals') {
      return `SELECT COUNT(*) AS violation_count\nFROM ${tableName}\nWHERE ${columnName} IS NULL\n   OR ${columnName} != '${String(ruleParams.value || '').replace(/'/g, "''")}';`;
    }
    return `SELECT COUNT(*) AS violation_count\nFROM ${tableName}\nWHERE ${columnName} IS NULL;`;
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

const scheduleOptions = [
  {
    id: 'manual',
    label: 'Do not schedule',
    cron: null,
    description: 'Save this rule for manual execution only.',
  },
  {
    id: 'every_5_minutes',
    label: 'Every 5 minutes',
    cron: '*/5 * * * *',
    description: 'Useful for quick demos and high-frequency checks.',
  },
  {
    id: 'every_15_minutes',
    label: 'Every 15 minutes',
    cron: '*/15 * * * *',
    description: 'Runs four times per hour.',
  },
  {
    id: 'every_30_minutes',
    label: 'Every 30 minutes',
    cron: '*/30 * * * *',
    description: 'Runs twice per hour.',
  },
  {
    id: 'hourly',
    label: 'Every hour',
    cron: '0 * * * *',
    description: 'Runs at the start of every hour.',
  },
  {
    id: 'daily',
    label: 'Every day',
    cron: '0 9 * * *',
    description: 'Runs daily at 09:00 UTC.',
  },
  {
    id: 'weekly',
    label: 'Every week',
    cron: '0 9 * * 1',
    description: 'Runs every Monday at 09:00 UTC.',
  },
  {
    id: 'monthly',
    label: 'Every month',
    cron: '0 9 1 * *',
    description: 'Runs on the first day of each month at 09:00 UTC.',
  },
  {
    id: 'yearly',
    label: 'Every year',
    cron: '0 9 1 1 *',
    description: 'Runs every January 1 at 09:00 UTC.',
  },
];

const expectationOptions = [
  {
    id: 'zero_violations',
    label: 'Zero violations',
    description: 'Pass when the returned aggregate is exactly 0.',
  },
  {
    id: 'min_threshold',
    label: 'Minimum threshold',
    description: 'Pass when the returned aggregate is greater than or equal to the threshold.',
  },
  {
    id: 'max_threshold',
    label: 'Maximum threshold',
    description: 'Pass when the returned aggregate is less than or equal to the threshold.',
  },
  {
    id: 'equals',
    label: 'Exact aggregate',
    description: 'Pass when the returned aggregate equals the configured value.',
  },
];

const expectationNeedsValue = (type) => type !== 'zero_violations';

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
  const [semanticMode, setSemanticMode] = useState('validation');
  const [params, setParams] = useState({
    min: '',
    max: '',
    pattern: '',
    value: '',
  });
  const [nlInput, setNlInput] = useState('');
  const [ruleName, setRuleName] = useState('Business validation rule');
  const [sqlText, setSqlText] = useState('');
  const [activeAuthoringMode, setActiveAuthoringMode] = useState('assistant');
  const [loading, setLoading] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  const [schedulePreset, setSchedulePreset] = useState('manual');
  const [queryMinThreshold, setQueryMinThreshold] = useState('1');
  const [customExpectationEnabled, setCustomExpectationEnabled] = useState(false);
  const [expectationType, setExpectationType] = useState('min_threshold');
  const [expectationValue, setExpectationValue] = useState('1');
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
  const selectedScheduleOption =
    scheduleOptions.find((option) => option.id === schedulePreset) ||
    scheduleOptions[0];
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

  const expectedResult = useMemo(() => {
    if (customExpectationEnabled) {
      return expectationNeedsValue(expectationType)
        ? { type: expectationType, value: Number(expectationValue) }
        : { type: expectationType };
    }

    if (semanticMode === 'query') {
      return { type: 'min_threshold', value: Number(queryMinThreshold) };
    }

    return { type: 'zero_violations' };
  }, [
    customExpectationEnabled,
    expectationType,
    expectationValue,
    queryMinThreshold,
    semanticMode,
  ]);

  const validationIssues = useMemo(() => {
    const issues = {};

    if (!selectedDataset) {
      issues.dataset = 'Connect the company database to start validation.';
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

    if (
      semanticMode === 'query' &&
      !customExpectationEnabled &&
      (queryMinThreshold === '' || !Number.isFinite(Number(queryMinThreshold)))
    ) {
      issues.expectation = 'Enter a numeric minimum threshold for query mode.';
    }

    if (
      customExpectationEnabled &&
      expectationNeedsValue(expectationType) &&
      (expectationValue === '' || !Number.isFinite(Number(expectationValue)))
    ) {
      issues.expectation = 'Enter a numeric value for the selected expectation.';
    }

    return issues;
  }, [
    applicableRuleIds,
    params.max,
    params.min,
    params.pattern,
    queryMinThreshold,
    schemaMetadata.length,
    selectedColumn,
    selectedColumnMeta,
    selectedColumnType,
    selectedDataset,
    selectedRule,
    semanticMode,
    customExpectationEnabled,
    expectationType,
    expectationValue,
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
    validationIssues.expectation ||
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
        message: 'Try referencing a column name that appears in the database table schema.',
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
        .slice(0, 80) || 'Business validation rule',
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
    setActiveAuthoringMode('sql');
    setCompatibilityNotice('');

    pushToast({
      tone: 'success',
      title: 'Rule generated',
      message: `The builder was auto-filled for ${matchedColumn.columnName}.`,
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
          expected_result: expectedResult,
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
        message: `Observed value ${response.resultRows ?? response.failedRows ?? 0} was saved in history.`,
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
        expected_result: expectedResult,
        schedule_cron: selectedScheduleOption.cron,
        is_enabled: true,
      });

      pushToast({
        tone: 'success',
        title: 'Rule saved',
        message: selectedScheduleOption.cron
          ? `${savedRule.ruleName} was saved to run ${selectedScheduleOption.label.toLowerCase()}. Restart the scheduler container if it was already running.`
          : `${savedRule.ruleName} is available in saved validation history.`,
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

  return (
    <div className="space-y-10">
      <section className="glass-panel p-6 sm:p-8 lg:p-10">
        <div className="border-b border-white/10 pb-8">
          <p className="section-kicker">Author Rule</p>
          <h3 className="mt-4 text-3xl font-semibold text-white">
            Ask a question from your database
          </h3>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-400">
            Enter a plain-English rule or write SQL directly. The backend runs a
            safe aggregate query against the connected company database.
          </p>
        </div>

        <div className="mt-8 space-y-8">
          <div className="subtle-card p-6 sm:p-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <label className="field-label mb-0" htmlFor="rule-natural-language">
                  Rule Assistant
                </label>
                <p className="field-hint">
                  Describe the database condition you want to validate. The generated SQL remains editable.
                </p>
              </div>
              <button
                type="button"
                onClick={handleGenerateRule}
                disabled={!nlInput.trim() || !schemaMetadata.length}
                title="Generate a rule from the description and auto-fill the form below."
                className="secondary-button w-full sm:w-auto"
              >
                Generate Rule
              </button>
            </div>

            <textarea
              id="rule-natural-language"
              value={nlInput}
              onChange={(event) => setNlInput(event.target.value)}
              rows="4"
              placeholder="Show employees with negative salary"
              className="input-shell mt-4 min-h-[120px] resize-y"
            />

            <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Examples
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                age should be between 0 and 120
                <br />
                show employees with negative salary
                <br />
                email should not be null
                <br />
                salary greater than 10000
              </p>
            </div>
          </div>

          <div className="subtle-card p-6 sm:p-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="field-label mb-0">Authoring Mode</p>
                <p className="field-hint">
                  Use the assistant, guided fields, or direct SQL editing against the active database table.
                </p>
              </div>
              <div className="inline-flex rounded-2xl border border-white/10 bg-slate-950/60 p-1">
                {[
                  ['assistant', 'Assistant'],
                  ['builder', 'Builder'],
                  ['sql', 'SQL'],
                ].map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setActiveAuthoringMode(mode)}
                    className={`rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-[0.2em] transition-all ${
                      activeAuthoringMode === mode
                        ? 'bg-cyan-400/15 text-cyan-100'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-6">
              <div>
                <label className="field-label" htmlFor="rule-name">
                  Rule Name
                </label>
                <input
                  id="rule-name"
                  type="text"
                  value={ruleName}
                  onChange={(event) => setRuleName(event.target.value)}
                  placeholder="Attendance below threshold"
                  className="input-shell max-w-xl"
                />
                <p className="field-hint">
                  This name appears in saved rules and history.
                </p>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="field-label mb-0" htmlFor="rule-sql-editor">
                    SQL Workspace
                  </label>
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-sky-400">Live Editor</span>
                </div>
                <div id="rule-sql-editor" className="sql-editor-shell overflow-hidden p-0 border-slate-700">
                  <Editor
                    height="340px"
                    defaultLanguage="sql"
                    value={sqlText}
                    theme="vs-dark"
                    loading={<Loader label="Loading SQL editor" compact />}
                    onChange={(value) => {
                      setSqlText(value || '');
                      setActiveAuthoringMode('sql');
                    }}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 14,
                      fontFamily:
                        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                      lineNumbersMinChars: 3,
                      padding: { top: 16, bottom: 16 },
                      scrollBeyondLastLine: false,
                      wordWrap: 'on',
                      automaticLayout: true,
                      contextmenu: true,
                      renderLineHighlight: "all",
                      minimap: { enabled: true, scale: 0.75 },
                    }}
                  />
                </div>
                <p className="field-hint">
                  This SQL is sent to `/rules/run`, and the aggregate result is saved in history.
                </p>
              </div>
            </div>
          </div>

          <div className="subtle-card p-6 sm:p-8">
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
              title="Choose the column you want to use for this rule."
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
                  : 'Pick a schema column to build the rule.'}
              </p>
            )}
          </div>

          {selectedColumnMeta && (
            <div className="subtle-card p-6 sm:p-8">
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
              <p className="field-label mb-0">Semantic Mode</p>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                SQL logic generation
              </p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSemanticMode('query')}
                className={`selection-card ${semanticMode === 'query' ? 'selection-card-active' : ''}`}
              >
                <p className="text-sm font-semibold text-white">Query Mode</p>
                <p className="mt-1 text-xs text-slate-400">Count rows that match the condition</p>
              </button>
              <button
                type="button"
                onClick={() => setSemanticMode('validation')}
                className={`selection-card ${semanticMode === 'validation' ? 'selection-card-active' : ''}`}
              >
                <p className="text-sm font-semibold text-white">Validation Mode</p>
                <p className="mt-1 text-xs text-slate-400">Count rows that violate the condition</p>
              </button>
            </div>
          </div>

          <div className="subtle-card">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-sm font-semibold text-white">Expected Result</p>
                <p className="field-hint">
                  This controls how the backend turns the aggregate returned by your SQL into PASS or FAIL.
                </p>
              </div>
              <label className="inline-flex items-center gap-3 text-sm font-semibold text-slate-200">
                <input
                  type="checkbox"
                  checked={customExpectationEnabled}
                  onChange={(event) => setCustomExpectationEnabled(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-cyan-400 focus:ring-cyan-400"
                />
                Custom expectation
              </label>
            </div>

            {!customExpectationEnabled && semanticMode === 'query' && (
              <div className="mt-4 max-w-sm">
                <label className="field-label" htmlFor="query-min-threshold">
                  Minimum Passing Count
                </label>
                <input
                  id="query-min-threshold"
                  type="number"
                  value={queryMinThreshold}
                  onChange={(event) => setQueryMinThreshold(event.target.value)}
                  min="0"
                  className={`input-shell ${validationIssues.expectation ? 'input-shell-error' : ''}`}
                />
                {validationIssues.expectation ? (
                  <p className="field-error">{validationIssues.expectation}</p>
                ) : (
                  <p className="field-hint">
                    Query mode passes when the aggregate is at least this value.
                  </p>
                )}
              </div>
            )}

            {!customExpectationEnabled && semanticMode === 'validation' && (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                <p className="text-sm font-semibold text-white">Zero violations</p>
                <p className="field-hint">
                  Validation mode passes when the aggregate returned by SQL is 0.
                </p>
              </div>
            )}

            {customExpectationEnabled && (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <label className="field-label" htmlFor="expectation-type">
                    Expectation Type
                  </label>
                  <select
                    id="expectation-type"
                    value={expectationType}
                    onChange={(event) => setExpectationType(event.target.value)}
                    className="input-shell"
                  >
                    {expectationOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="field-hint">
                    {
                      expectationOptions.find((option) => option.id === expectationType)
                        ?.description
                    }
                  </p>
                </div>

                {expectationNeedsValue(expectationType) && (
                  <div>
                    <label className="field-label" htmlFor="expectation-value">
                      Expected Value
                    </label>
                    <input
                      id="expectation-value"
                      type="number"
                      value={expectationValue}
                      onChange={(event) => setExpectationValue(event.target.value)}
                      className={`input-shell ${validationIssues.expectation ? 'input-shell-error' : ''}`}
                    />
                    {validationIssues.expectation && (
                      <p className="field-error">{validationIssues.expectation}</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="field-label mb-0">Rule Type</p>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Simple options
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

          {selectedRule === 'equals' && (
            <div className="subtle-card">
              <label className="field-label" htmlFor="rule-value">
                Exact Match Value
              </label>
              <input
                id="rule-value"
                type="text"
                value={params.value}
                onChange={(event) =>
                  setParams((current) => ({
                    ...current,
                    value: event.target.value,
                  }))
                }
                placeholder="e.g. Joy"
                title="Exact string to match"
                className="input-shell"
              />
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
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-white">Schedule saved rule</p>
                <p className="field-hint">
                  Choose how often the scheduler should run this saved rule.
                </p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">
                {selectedScheduleOption.cron ? 'Scheduled' : 'Manual'}
              </span>
            </div>

            <div className="mt-4 max-w-xl">
              <div>
                <label className="field-label" htmlFor="rule-schedule-preset">
                  Schedule
                </label>
                <select
                  id="rule-schedule-preset"
                  value={schedulePreset}
                  onChange={(event) => setSchedulePreset(event.target.value)}
                  className="input-shell"
                >
                  {scheduleOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="field-hint">
              {selectedScheduleOption.description} If the scheduler is already running, restart it after saving a new scheduled rule.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <button
              type="button"
              onClick={handleRunValidation}
              disabled={!canRunValidation}
              title={
                canRunValidation
                  ? 'Run the selected rule and save the aggregate result.'
                  : primaryValidationMessage || 'Connect the database to start validation.'
              }
              className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <Loader label="Executing rule" compact />
              ) : (
                'Run Rule'
              )}
            </button>

            <button
              type="button"
              onClick={handleSaveRule}
              disabled={
                savingRule ||
                !selectedDataset ||
                !sqlText.trim() ||
                Boolean(primaryValidationMessage)
              }
              className="secondary-button w-full sm:w-auto"
            >
              {savingRule ? <Loader label="Saving" compact /> : 'Save Rule'}
            </button>
          </div>
        </div>
      </section>

      <section
        ref={resultsSectionRef}
        tabIndex={-1}
        className={`glass-panel p-6 outline-none transition-all duration-500 sm:p-8 lg:p-10 ${
          resultsHighlighted ? 'section-focus-flash' : ''
        }`}
      >
        <div className="flex flex-col gap-5 border-b border-white/10 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-kicker">Rule Results</p>
            <h3 className="mt-4 text-3xl font-semibold text-white">
              Aggregate result returned by your rule
            </h3>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-400">
              The daemon persists the aggregate value, pass/fail status, SQL,
              execution time, and error details for each run.
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
              title="Open the enterprise validation workspace."
            >
              Open Workspace
            </Link>
            <Link
              to="/history"
              className="secondary-button w-full sm:w-auto"
              title="Open persisted validation history."
            >
              View History
            </Link>
          </div>
        </div>

        {validationResults ? (
          <div className="mt-6 space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <ResultSummaryCard
                label="Database Rows"
                value={validationResults.summary?.checkedRows || 0}
                hint="Rows scanned for this rule"
              />
              <ResultSummaryCard
                label="Observed"
                value={
                  validationResults.summary?.resultRows ??
                  validationResults.summary?.failedRows ??
                  0
                }
                hint="Aggregate value returned by the rule"
              />
              <ResultSummaryCard
                label="Rule"
                value={validationResults.summary?.column || 'SQL'}
                hint={validationResults.summary?.rule || 'Current rule'}
              />
            </div>

            <div className="subtle-card">
              <p className="text-sm font-semibold text-white">Persisted Result</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                The backend stores the aggregate outcome and returns a preview of
                violating rows for count-based violation checks.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {[
                  ['Status', validationResults.summary?.status || 'Unknown'],
                  [
                    'Observed Value',
                    validationResults.summary?.resultRows ??
                      validationResults.summary?.failedRows ??
                      0,
                  ],
                  ['Executed At', validationResults.summary?.executionTime || 'Pending'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
                    <p className="mt-2 text-sm font-semibold text-white">{value}</p>
                  </div>
                ))}
              </div>
            </div>

            <ResultTable
              rows={validationResults.resultRows || validationResults.failedRows || []}
              title="Violating Rows Preview"
              description="Preview rows returned from the same WHERE condition used by the violation count."
              emptyTitle="No violating rows returned"
              emptyMessage="Either the rule passed or this SQL shape does not support row preview."
              pageSize={10}
            />
          </div>
        ) : (
          <div className="empty-state mt-6">
            <p className="text-lg font-semibold text-white">
              Results will appear here
            </p>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
              Connect the database, enter a rule, and run it to see the aggregate result.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
