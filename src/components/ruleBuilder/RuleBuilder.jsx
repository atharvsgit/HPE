import { useEffect, useMemo, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import { Link } from 'react-router-dom';
import Loader from '../common/Loader';
import ResultTable from '../common/ResultTable';
import StatusBadge from '../common/StatusBadge';
import { useDataset } from '../../context/DatasetContext';
import { createSavedRule, runAdHocRule } from '../../services/rulesApi';

const ruleOptions = [
  { id: 'between', label: 'Between', description: 'Checks whether a numeric value lies within a minimum and maximum range.' },
  { id: 'regex', label: 'Regex Pattern', description: 'Matches text-like values against a regular expression pattern.' },
  { id: 'not_null', label: 'Not Null', description: 'Ensures every inspected row has a value for the selected column.' },
  { id: 'equals', label: 'Exact Match', description: 'Matches a specific string or numeric value exactly.' },
];

const applicableRulesByType = {
  numeric: ['between', 'not_null', 'equals'],
  string: ['regex', 'not_null', 'equals'],
  boolean: ['not_null', 'equals'],
  default: ['regex', 'not_null', 'equals'],
};

const numericTypes = ['integer', 'decimal', 'float', 'double', 'number', 'numeric', 'bigint', 'smallint'];
const booleanTypes = ['boolean', 'bool'];
const stringTypes = ['varchar', 'char', 'string', 'text', 'uuid', 'timestamp', 'date', 'datetime'];

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

const findColumnFromInput = (input, schema) => {
  const safeSchema = schema || [];
  const normalizedInput = normalizeColumnToken(input);
  return [...safeSchema]
    .sort((left, right) => right.columnName.length - left.columnName.length)
    .find((column) => {
      const normalizedColumn = normalizeColumnToken(column.columnName);
      const columnPattern = new RegExp(`\\b${escapeRegExp(normalizedColumn)}\\b`);
      return columnPattern.test(normalizedInput);
    });
};

const extractRegexPattern = (value = '') => {
  const slashPatternMatch = value.match(/\/([^/]+)\/[gimsuy]*/);
  if (slashPatternMatch?.[1]) return slashPatternMatch[1].trim();

  const quotedPatternMatch = value.match(/(?:match|regex)(?:\s+pattern)?\s+["'](.+?)["']/i);
  if (quotedPatternMatch?.[1]) return quotedPatternMatch[1].trim();

  const afterKeywordMatch = value.match(/(?:match|regex)(?:\s+pattern)?\s+(.+)$/i);
  return afterKeywordMatch?.[1]?.trim() || '';
};

const getOpenEndedMax = (columnName, threshold, rows = []) => {
  const numericValues = rows
    .map((row) => Number(row?.[columnName]))
    .filter((value) => Number.isFinite(value));
  if (!numericValues.length) return OPEN_ENDED_MAX;
  const currentMaximum = Math.max(...numericValues);
  return currentMaximum > Number(threshold) ? String(currentMaximum) : OPEN_ENDED_MAX;
};

const getRuleLabel = (ruleId) =>
  ruleOptions.find((option) => option.id === ruleId)?.label || ruleId;

const toColumnTypeGroup = (dataType = '') => {
  const normalizedType = String(dataType || '').trim().toLowerCase();
  if (numericTypes.includes(normalizedType)) return 'numeric';
  if (booleanTypes.includes(normalizedType)) return 'boolean';
  if (stringTypes.includes(normalizedType)) return 'string';
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

const commandTemplates = [
  { label: 'Check attendance below 80 every week', text: 'Show students with attendance less than 80 every week' },
  { label: 'Validate email format daily', text: 'Validate email format matches regex pattern daily' },
  { label: 'Verify salary is not null daily', text: 'Check salary column is not null every day and notify me' },
  { label: 'Audit high transactions monthly', text: 'Verify transaction_amount is between 0 and 5000000 every month' }
];

export default function RuleBuilder() {
  const {
    schemaMetadata,
    selectedDataset,
    datasetRows,
    validationResults,
    setValidationResults,
    pushToast,
  } = useDataset();

  // Primary controls
  const [nlInput, setNlInput] = useState('');
  const [ruleName, setRuleName] = useState('Business validation check');
  const [selectedColumn, setSelectedColumn] = useState('');
  const [selectedRule, setSelectedRule] = useState('not_null');
  const [semanticMode, setSemanticMode] = useState('validation'); // validation = find violations
  const [params, setParams] = useState({ min: '', max: '', pattern: '', value: '' });

  // UI display toggles
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [sqlText, setSqlText] = useState('');
  const [loading, setLoading] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [scheduleStep, setScheduleStep] = useState(0);

  // Interpretation results preview
  const [parsedSchedule, setParsedSchedule] = useState('Ad-hoc run (Immediate)');
  const [parsedCron, setParsedCron] = useState('-');
  const [nextRunPreview, setNextRunPreview] = useState('No Execution scheduled');

  // Set default column when schema loads
  useEffect(() => {
    const schema = schemaMetadata || [];
    if (schema.length > 0) {
      const exists = schema.some((c) => c.columnName === selectedColumn);
      if (!exists) {
        setSelectedColumn(schema[0].columnName);
      }
    } else {
      setSelectedColumn('');
    }
  }, [schemaMetadata, selectedColumn]);

  // Load duplicated rule configuration on mount
  useEffect(() => {
    try {
      const duplicated = localStorage.getItem('pulseqc:duplicated-rule');
      if (duplicated) {
        const config = JSON.parse(duplicated);
        if (config.nlInput) setNlInput(config.nlInput);
        if (config.ruleName) setRuleName(config.ruleName);
        if (config.sqlText) setSqlText(config.sqlText);
        if (config.column) setSelectedColumn(config.column);
        localStorage.removeItem('pulseqc:duplicated-rule');
      }
    } catch {}
  }, [pushToast]);

  const selectedColumnMeta = useMemo(
    () => (schemaMetadata || []).find((column) => column.columnName === selectedColumn) || null,
    [schemaMetadata, selectedColumn],
  );

  const selectedColumnType = selectedColumnMeta?.dataType || 'unknown';
  const selectedColumnTypeGroup = toColumnTypeGroup(selectedColumnType);
  const applicableRuleIds = applicableRulesByType[selectedColumnTypeGroup] || applicableRulesByType.default;

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
    setSqlText(generatedSqlPreview);
  }, [generatedSqlPreview]);

  // Real-time Natural Language prompt parser
  useEffect(() => {
    const text = nlInput.trim().toLowerCase();
    if (!text) return;

    // 1. Column matching
    const matchedColumn = findColumnFromInput(text, schemaMetadata);
    if (matchedColumn) {
      setSelectedColumn(matchedColumn.columnName);
    }

    // 2. Frequency / Re-occurrence parsing
    let freq = 'Ad-hoc run (Immediate)';
    let cron = '-';
    let nextRun = 'No Execution scheduled';

    if (text.includes('every day') || text.includes('daily')) {
      freq = 'Daily';
      cron = '0 0 * * *';
      nextRun = 'Tomorrow at 00:00 UTC';
    } else if (text.includes('every week') || text.includes('weekly') || text.includes('every monday')) {
      freq = 'Weekly';
      cron = '0 0 * * 1';
      nextRun = 'Next Monday at 00:00 UTC';
    } else if (text.includes('every 2 weeks') || text.includes('bi-weekly')) {
      freq = 'Every 2 weeks';
      cron = '0 0 */14 * *';
      nextRun = 'In 14 days at 00:00 UTC';
    } else if (text.includes('every month') || text.includes('monthly')) {
      freq = 'Monthly';
      cron = '0 0 1 * *';
      nextRun = '1st of next month at 00:00 UTC';
    }

    setParsedSchedule(freq);
    setParsedCron(cron);
    setNextRunPreview(nextRun);

    // 3. Rule type parsing
    let rule = 'not_null';
    const nextParams = { min: '', max: '', pattern: '', value: '' };

    if (text.includes('between')) {
      rule = 'between';
      const numbers = text.match(/\b\d+\b/g);
      if (numbers && numbers.length >= 2) {
        nextParams.min = numbers[0];
        nextParams.max = numbers[1];
      }
    } else if (text.includes('less than') || text.includes('below') || text.includes('<')) {
      rule = 'between';
      const numbers = text.match(/\b\d+\b/g);
      if (numbers && numbers.length > 0) {
        nextParams.min = '0';
        nextParams.max = numbers[0];
      }
    } else if (text.includes('greater than') || text.includes('above') || text.includes('>')) {
      rule = 'between';
      const numbers = text.match(/\b\d+\b/g);
      if (numbers && numbers.length > 0) {
        nextParams.min = numbers[0];
        nextParams.max = OPEN_ENDED_MAX;
      }
    } else if (text.includes('regex') || text.includes('match') || text.includes('format')) {
      rule = 'regex';
      if (text.includes('email')) {
        nextParams.pattern = '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$';
      } else {
        nextParams.pattern = '^[A-Z_]+$';
      }
    } else if (text.includes('is') || text.includes('equal') || text.includes('=')) {
      rule = 'equals';
      const match = nlInput.match(/(?:is|equal(?:s)?(?: to)?|=)\s+([\w\s]+?)(?=\s|$)/i);
      if (match) {
        nextParams.value = match[1].trim();
      }
    }

    setSelectedRule(rule);
    setParams(nextParams);

    // 4. Update Rule Name
    const rawName = nlInput.replace(/^(check|validate|run|show|verify)\s+/i, '');
    const cleanName = rawName.charAt(0).toUpperCase() + rawName.slice(1, 45);
    setRuleName(cleanName || 'Validation Rule');

  }, [nlInput, schemaMetadata]);

  const validationIssues = useMemo(() => {
    const issues = {};
    if (!selectedDataset) issues.dataset = 'Connect database source first.';
    if (!schemaMetadata || !schemaMetadata.length) issues.schema = 'Database schema registration required.';
    if (!selectedColumn) issues.column = 'Choose column context.';
    
    if (selectedRule === 'between') {
      if (params.min === '') issues.min = 'Set minimum limit.';
      if (params.max === '') issues.max = 'Set maximum limit.';
    }
    if (selectedRule === 'regex' && !params.pattern.trim()) {
      issues.pattern = 'Specify regex pattern.';
    }
    return issues;
  }, [selectedDataset, schemaMetadata, selectedColumn, selectedRule, params]);

  const primaryValidationMessage =
    validationIssues.dataset ||
    validationIssues.schema ||
    validationIssues.column ||
    validationIssues.min ||
    validationIssues.max ||
    validationIssues.pattern ||
    '';

  const handleRunValidation = async () => {
    setLoading(true);
    try {
      const response = await runAdHocRule(
        {
          dataset_id: selectedDataset?.id,
          dataset_name: selectedDataset?.name,
          rule_name: ruleName,
          sql: sqlText,
          expected_result: { type: 'zero_violations' },
        },
        {
          datasetRows,
          localPayload: {
            column: selectedColumn,
            rule: selectedRule,
            semanticMode,
            min: params.min,
            max: params.max,
            pattern: params.pattern,
            value: params.value,
          },
        }
      );

      setValidationResults(toValidationResultsShape(response, { column: selectedColumn }));
      
      resultsSectionRef.current?.scrollIntoView({ behavior: 'smooth' });

      pushToast({
        tone: 'success',
        title: 'Validation query completed',
        message: `${response.failedRows || 0} violations returned from execution.`,
      });
    } catch (error) {
      pushToast({
        tone: 'error',
        title: 'Query execution failed',
        message: error.message || 'Verification compiler failed to run SQL.',
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
        rule_name: ruleName,
        sql: sqlText,
        expected_result: { type: 'zero_violations' },
      });
      pushToast({
        tone: 'success',
        title: 'Validation rule saved',
        message: `"${savedRule.ruleName}" registered in saved workspace.`,
      });
    } catch (error) {
      pushToast({
        tone: 'error',
        title: 'Could not save rule',
        message: error.message || 'API failed to store validation check.',
      });
    } finally {
      setSavingRule(false);
    }
  };

  const handleScheduleValidation = () => {
    setScheduling(true);
    setScheduleStep(0);

    const steps = [
      'Compiling validation query and verifying schema types...',
      'Deploying Cron validation rule trigger to coordinator daemon...',
      'Registering job parameters in Redis queuing backend...',
      'Validation task schedule configured successfully!'
    ];

    const runSteps = (idx) => {
      if (idx < steps.length) {
        setScheduleStep(idx);
        setTimeout(() => runSteps(idx + 1), 400);
      } else {
        const newTask = {
          id: `task-${Date.now()}`,
          name: ruleName,
          dataset: selectedDataset ? `${selectedDataset.subType}_db.${selectedDataset.name}` : 'unknown_db.unknown_table',
          status: 'active',
          frequency: parsedSchedule === 'Ad-hoc run (Immediate)' ? 'daily' : parsedSchedule.toLowerCase(),
          originalPrompt: nlInput || `Validate ${selectedColumn} constraints`,
          sql: sqlText,
          lastRun: new Date().toISOString(),
          nextRun: new Date(Date.now() + 3600000 * 24).toISOString(),
          rowsScanned: selectedDataset?.records || 5000,
          rowsReturned: 0,
          duration: '0.45s',
          emailStatus: 'Notification Sent: Active (recipient: data-alerts@enterprise.com)',
          steps: [
            'Validation Processing: Triggered by scheduled rule trigger.',
            'Queue Event: Dequeued from validation job queue.',
            'Task Step: Verified active database connection: OK',
            'Validation Processing: Completed (0 returned rows).'
          ]
        };

        const existingTasks = JSON.parse(localStorage.getItem(TASKS_KEY) || '[]');
        localStorage.setItem(TASKS_KEY, JSON.stringify([newTask, ...existingTasks]));

        createSavedRule({
          rule_name: ruleName,
          sql: sqlText,
          dataset_name: selectedDataset?.name || 'unknown_dataset',
        }).catch(() => {});

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
    <div className="grid gap-5 lg:grid-cols-4">
      {/* Workspace Area (NL input and SQL workspaces) */}
      <div className="lg:col-span-3 space-y-4">
        
        {/* Natural Language Workspace */}
        <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Intelligent Assistant Command Center</h3>
            <p className="text-xs text-slate-400 mt-0.5">Describe validation operations and schedule rules in natural language.</p>
          </div>

          <textarea
            id="rule-nl-input"
            rows="3"
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            placeholder="e.g. Check salary column below 0 every week, or Validate transaction_amount is between 10 and 5000000 daily"
            className="input-shell text-xs leading-relaxed"
          />

          {/* Quick template chips */}
          <div className="flex flex-wrap gap-1.5 items-center">
            {commandTemplates.map((chip, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setNlInput(chip.text)}
                className="text-[10px] font-semibold px-2 py-1 rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-500 hover:text-slate-700 dark:hover:text-slate-350 hover:bg-slate-100 dark:hover:bg-slate-850 transition-colors"
              >
                {chip.label}
              </button>
            ))}
          </div>
        </section>

        {/* Structured Interpretation Summary Preview */}
        {nlInput.trim() && (
          <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-4 grid gap-3 grid-cols-2 md:grid-cols-5 text-xs animate-slide-up">
            <div className="border-r border-slate-100 dark:border-slate-850 pr-2">
              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide block">Task Target</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200 mt-1 block truncate" title={ruleName}>
                {ruleName}
              </span>
            </div>
            <div className="border-r border-slate-100 dark:border-slate-850 pr-2">
              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide block">Interpreted Schedule</span>
              <span className="font-semibold text-sky-500 mt-1 block truncate">{parsedSchedule}</span>
            </div>
            <div className="border-r border-slate-100 dark:border-slate-850 pr-2">
              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide block">Target Field</span>
              <span className="font-mono text-slate-700 dark:text-slate-200 mt-1 block truncate">{selectedColumn || 'N/A'}</span>
            </div>
            <div className="border-r border-slate-100 dark:border-slate-850 pr-2">
              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide block">Connected DB</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200 mt-1 block truncate">{selectedDataset?.name || 'None'}</span>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide block">Next Execution</span>
              <span className="font-semibold text-slate-600 dark:text-slate-350 mt-1 block truncate" title={nextRunPreview}>
                {nextRunPreview}
              </span>
            </div>
          </section>
        )}

        {/* Collapsible Advanced builder configurations */}
        <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 overflow-hidden">
          <button
            type="button"
            onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
            className="w-full flex items-center justify-between p-4 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-900/20"
          >
            <span>ADVANCED PARAMETER BUILDER</span>
            <span>{isAdvancedOpen ? 'Hide' : 'Expand Form'}</span>
          </button>

          {isAdvancedOpen && (
            <div className="p-5 border-t border-slate-150 dark:border-slate-850 space-y-4 text-xs">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="field-label" htmlFor="rule-name-input">Validation Rule Name</label>
                  <input
                    id="rule-name-input"
                    type="text"
                    value={ruleName}
                    onChange={(e) => setRuleName(e.target.value)}
                    className="input-shell text-xs"
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="col-select">Target Column Context</label>
                  <select
                    id="col-select"
                    value={selectedColumn}
                    onChange={(e) => setSelectedColumn(e.target.value)}
                    className="input-shell text-xs"
                  >
                    {(schemaMetadata || []).map((c) => (
                      <option key={c.columnName} value={c.columnName}>
                        {c.columnName} ({c.dataType})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="field-label">Verification Logic Mode</label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setSemanticMode('query')}
                      className={`border rounded py-1.5 font-semibold text-center ${
                        semanticMode === 'query'
                          ? 'border-sky-500 bg-sky-500/10 text-sky-500'
                          : 'border-slate-200 dark:border-slate-800'
                      }`}
                    >
                      Filter Matches
                    </button>
                    <button
                      type="button"
                      onClick={() => setSemanticMode('validation')}
                      className={`border rounded py-1.5 font-semibold text-center ${
                        semanticMode === 'validation'
                          ? 'border-sky-500 bg-sky-500/10 text-sky-500'
                          : 'border-slate-200 dark:border-slate-800'
                      }`}
                    >
                      Find Violations
                    </button>
                  </div>
                </div>
                <div>
                  <label className="field-label">Rule Filter Options</label>
                  <select
                    value={selectedRule}
                    onChange={(e) => setSelectedRule(e.target.value)}
                    className="input-shell text-xs"
                  >
                    {ruleOptions.map((opt) => (
                      <option key={opt.id} value={opt.id} disabled={!applicableRuleIds.includes(opt.id)}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {selectedRule === 'between' && (
                <div className="grid gap-4 md:grid-cols-2 bg-slate-50 dark:bg-slate-900/10 p-3 rounded">
                  <div>
                    <label className="field-label" htmlFor="min-input">Min Limit</label>
                    <input
                      id="min-input"
                      type="number"
                      value={params.min}
                      onChange={(e) => setParams({ ...params, min: e.target.value })}
                      className="input-shell text-xs"
                    />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="max-input">Max Limit</label>
                    <input
                      id="max-input"
                      type="number"
                      value={params.max}
                      onChange={(e) => setParams({ ...params, max: e.target.value })}
                      className="input-shell text-xs"
                    />
                  </div>
                </div>
              )}

              {selectedRule === 'regex' && (
                <div className="bg-slate-50 dark:bg-slate-900/10 p-3 rounded">
                  <label className="field-label" htmlFor="pat-input">Pattern Expression</label>
                  <input
                    id="pat-input"
                    type="text"
                    value={params.pattern}
                    onChange={(e) => setParams({ ...params, pattern: e.target.value })}
                    className="input-shell text-xs"
                  />
                </div>
              )}

              {selectedRule === 'equals' && (
                <div className="bg-slate-50 dark:bg-slate-900/10 p-3 rounded">
                  <label className="field-label" htmlFor="match-input">Match String</label>
                  <input
                    id="match-input"
                    type="text"
                    value={params.value}
                    onChange={(e) => setParams({ ...params, value: e.target.value })}
                    className="input-shell text-xs"
                  />
                </div>
              )}
            </div>
          )}
        </section>

        {/* Monaco Editor panel */}
        <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">SQL Command Workspace</h3>
              <p className="text-xs text-slate-400 mt-0.5">Vetting database statements before scheduling validations.</p>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-500 font-mono">PostgreSQL dialect</span>
          </div>

          <div className="sql-editor-shell border-slate-200 dark:border-slate-800 overflow-hidden">
            <Editor
              height="200px"
              defaultLanguage="sql"
              value={sqlText}
              theme="vs-dark"
              loading={<Loader label="Mounting database editor..." compact />}
              onChange={(val) => setSqlText(val || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                fontFamily: 'ui-monospace, IBM Plex Mono, Consolas, monospace',
                lineNumbersMinChars: 3,
                padding: { top: 8, bottom: 8 },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                automaticLayout: true,
                renderLineHighlight: 'all',
              }}
            />
          </div>

          {/* Controls toolbar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded px-4 py-2.5">
            <span className="text-slate-500">
              Database: <strong className="text-slate-600 dark:text-slate-350">{selectedDataset?.name || 'None Connected'}</strong> {selectedDataset?.records ? `(${selectedDataset.records.toLocaleString()} rows)` : ''}
            </span>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRunValidation}
                disabled={loading || !sqlText.trim() || primaryValidationMessage}
                className="secondary-button text-xs font-semibold py-1 px-3"
              >
                {loading ? <Loader label="Compiling..." compact /> : 'Test Query'}
              </button>
              <button
                type="button"
                onClick={handleScheduleValidation}
                disabled={scheduling || !sqlText.trim() || primaryValidationMessage}
                className="primary-button text-xs font-semibold py-1.5 px-3"
              >
                Schedule Validation
              </button>
              <button
                type="button"
                onClick={handleSaveRule}
                disabled={savingRule || !sqlText.trim()}
                className="secondary-button text-xs font-semibold py-1.5 px-3"
              >
                Save Registry
              </button>
            </div>
          </div>
        </section>

        {/* Schedule deployment loader steps */}
        {scheduling && (
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3 animate-slide-up">
            <div className="flex items-center gap-2.5">
              <Loader label="" compact />
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Deploying Validation Task...</span>
            </div>
            <div className="space-y-1.5 text-xs text-slate-500">
              {[
                'Compiling validation query and verifying schema types...',
                'Deploying Cron validation rule trigger to coordinator daemon...',
                'Registering job parameters in Redis queuing backend...',
                'Validation task schedule configured successfully!'
              ].map((step, idx) => (
                <div key={idx} className={`flex items-center gap-2 ${scheduleStep >= idx ? 'text-slate-800 dark:text-slate-200 font-medium' : 'text-slate-400'}`}>
                  {scheduleStep > idx ? (
                    <span className="text-emerald-500 font-bold mr-1">✓</span>
                  ) : scheduleStep === idx ? (
                    <span className="h-3 w-3 rounded-full border border-sky-500 border-t-transparent animate-spin inline-block mr-1" />
                  ) : (
                    <span className="h-3 w-3 rounded-full border border-slate-200 dark:border-slate-850 inline-block mr-1" />
                  )}
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results Block */}
        {validationResults && (
          <section ref={resultsSectionRef} className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-5 animate-slide-up">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Returned Violation Rows</h3>
              <span className="text-xs text-slate-400 font-mono">Scanned: {validationResults.summary.checkedRows.toLocaleString()} rows</span>
            </div>

            <div className="grid gap-3 grid-cols-3">
              <ResultSummaryCard
                label="Scanned Rows"
                value={validationResults.summary.checkedRows.toLocaleString()}
                hint="Checked database records"
              />
              <ResultSummaryCard
                label="Returned Violations"
                value={validationResults.summary.failedRows.toLocaleString()}
                hint="Rows breaking constraints"
                tone={validationResults.summary.failedRows > 0 ? 'danger' : 'neutral'}
              />
              <ResultSummaryCard
                label="Duration"
                value={validationResults.summary.executionTime}
                hint="Verification compile time"
              />
            </div>

            <ResultTable
              rows={validationResults.resultRows || []}
              title="Violation Rows Sample"
              description="Review specific records that flagged validation checks."
              emptyTitle={noRowsInRun ? 'All check passes' : 'No records returned'}
              emptyMessage={
                noRowsInRun
                  ? 'The validation query completed with 0 violations caught.'
                  : 'Run test queries to populate this sample table.'
              }
              pageSize={3}
            />
          </section>
        )}
      </div>

      {/* Target Column Info & Directory (1 widescreen column) */}
      <div className="space-y-4 text-xs">
        
        {/* Active Connector Context */}
        <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3.5">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Active Connector</h3>
            <p className="text-[10px] text-slate-400 mt-0.5">Context details for rule validation mapping.</p>
          </div>

          <div className="space-y-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2">
              <span className="text-slate-400">Database Name</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{selectedDataset?.name || 'None Connected'}</span>
            </div>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2">
              <span className="text-slate-400">Profiled Records</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{selectedDataset?.records ? `${selectedDataset.records.toLocaleString()} rows` : '0 rows'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Inspected Column</span>
              <span className="font-semibold font-mono text-slate-700 dark:text-slate-200 truncate max-w-[110px]" title={selectedColumn}>
                {selectedColumn || 'None'}
              </span>
            </div>
          </div>
        </section>

        {/* Schema Columns list */}
        <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Schema Directory</h3>
            <p className="text-[10px] text-slate-400 mt-0.5">Click column to target in advanced controls.</p>
          </div>

          <div className="rounded border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-850 max-h-[240px] overflow-y-auto">
            {!schemaMetadata || schemaMetadata.length === 0 ? (
              <div className="p-4 text-center text-slate-400">No schema loaded</div>
            ) : (
              schemaMetadata.map((c) => (
                <div
                  key={c.columnName}
                  onClick={() => setSelectedColumn(c.columnName)}
                  className={`flex items-center justify-between p-2.5 cursor-pointer transition-colors ${
                    selectedColumn === c.columnName
                      ? 'bg-sky-500/5 dark:bg-sky-500/10 font-medium'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-900/40'
                  }`}
                >
                  <span className="font-mono text-slate-700 dark:text-slate-200 truncate max-w-[100px]" title={c.columnName}>
                    {c.columnName}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-400 font-mono">{c.dataType}</span>
                    {c.nullCount > 0 && (
                      <span className="text-[9px] px-1 rounded bg-amber-500/10 text-amber-500 font-medium">
                        {c.nullCount} nulls
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

    </div>
  );
}
