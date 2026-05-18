import api from './api';

const toIsoString = (value) => {
  if (!value) {
    return new Date().toISOString();
  }

  const parsedDate = new Date(value);
  return Number.isNaN(parsedDate.getTime())
    ? new Date().toISOString()
    : parsedDate.toISOString();
};

const getRowsFromResponse = (response = {}) => {
  if (Array.isArray(response.violation_rows)) {
    return response.violation_rows;
  }

  if (Array.isArray(response.violationRows)) {
    return response.violationRows;
  }

  if (Array.isArray(response.failedRows)) {
    return response.failedRows;
  }

  if (Array.isArray(response.failed_rows)) {
    return response.failed_rows;
  }

  if (Array.isArray(response.rows)) {
    return response.rows;
  }

  if (Array.isArray(response.result)) {
    return response.result;
  }

  if (Array.isArray(response.result_rows)) {
    return response.result_rows;
  }

  if (Array.isArray(response.result?.rows)) {
    return response.result.rows;
  }

  if (Array.isArray(response.records)) {
    return response.records;
  }

  if (Array.isArray(response.data)) {
    return response.data;
  }

  return [];
};

const getResultCount = (response = {}, rows = []) =>
  response.result?.violation_count ??
  response.result?.observed_value ??
  response.observed_value ??
  response.result_count ??
  response.resultCount ??
  response.result_rows_count ??
  response.violation_count ??
  response.violationCount ??
  response.summary?.failedRows ??
  response.summary?.failed_rows ??
  response.failed_rows_count ??
  rows.length ??
  0;

const normalizeStatus = (status) => {
  const normalized = String(status || '').toUpperCase();

  if (['PASS', 'FAIL', 'ERROR'].includes(normalized)) {
    return normalized;
  }

  return status || 'completed';
};

export const normalizeRule = (rule = {}) => ({
  id: rule.id ?? rule.rule_id ?? rule.uuid ?? `rule-${Date.now()}`,
  ruleName: rule.rule_name ?? rule.ruleName ?? rule.name ?? 'Untitled rule',
  datasetName: rule.dataset_name ?? rule.datasetName ?? rule.dataset ?? 'Company database',
  sql: rule.sql ?? rule.query ?? '',
  expectedResult: rule.expected_result ?? rule.expectedResult ?? { type: 'zero_violations' },
  createdAt: toIsoString(rule.created_at ?? rule.createdAt),
  status: rule.status ?? 'active',
});

export const normalizeRuleResult = (response = {}, fallback = {}) => {
  const rows = getRowsFromResponse(response);
  const resultCount = Number(getResultCount(response, rows)) || 0;
  const checkedRows =
    response.checked_rows ??
    response.checkedRows ??
    response.summary?.checkedRows ??
    fallback.checkedRows ??
    0;
  const passedRows =
    response.passed_rows ??
    response.passedRows ??
    response.summary?.passedRows ??
    Math.max(Number(checkedRows) - resultCount, 0);

  return {
    id: response.id ?? response.result_id ?? fallback.id ?? `result-${Date.now()}`,
    ruleId: response.rule_id ?? response.ruleId ?? fallback.ruleId ?? null,
    ruleName:
      response.rule_name ??
      response.ruleName ??
      fallback.ruleName ??
      'Ad hoc business rule',
    datasetId: response.dataset_id ?? response.datasetId ?? fallback.datasetId ?? null,
    datasetName:
      response.dataset_name ??
      response.datasetName ??
      fallback.datasetName ??
      'Company database',
    sql: response.sql ?? response.query ?? fallback.sql ?? '',
    status: normalizeStatus(response.status),
    executionTime: toIsoString(
      response.execution_time ??
        response.executed_at ??
        response.created_at ??
        fallback.executionTime,
    ),
    duration:
      response.execution_time_ms !== undefined
        ? `${response.execution_time_ms}ms`
        : response.duration ?? response.summary?.executionTime ?? fallback.duration ?? 'backend recorded',
    checkedRows,
    passedRows,
    failedRows: resultCount,
    resultRows: resultCount,
    rows,
    expectedResult:
      response.expected_result ??
      response.expectedResult ??
      fallback.expectedResult ??
      { type: 'zero_violations' },
    source: response.source ?? fallback.source ?? 'backend',
    error: response.error ?? response.error_message ?? null,
  };
};

export async function runAdHocRule(payload) {
  const requestPayload = {
    rule_name: payload.rule_name || payload.ruleName || 'Ad hoc business rule',
    sql: payload.sql,
    expected_result: payload.expected_result || { type: 'zero_violations' },
  };

  const { data } = await api.post('/rules/run', requestPayload);

  return normalizeRuleResult(data, {
    ruleName: requestPayload.rule_name,
    datasetId: payload.dataset_id,
    datasetName: payload.dataset_name,
    sql: requestPayload.sql,
    expectedResult: requestPayload.expected_result,
  });
}

export async function createSavedRule(payload) {
  const requestPayload = {
    rule_name: payload.rule_name || payload.ruleName,
    sql: payload.sql,
    expected_result: payload.expected_result || { type: 'zero_violations' },
    schedule_cron: payload.schedule_cron ?? payload.scheduleCron ?? null,
    is_enabled: payload.is_enabled ?? payload.isEnabled ?? true,
  };

  const { data } = await api.post('/rules', requestPayload);
  return normalizeRule(data);
}

export async function getSavedRules() {
  const { data } = await api.get('/rules');
  const rules = Array.isArray(data) ? data : data?.rules || [];
  return rules.map(normalizeRule);
}

export async function getRuleResults(ruleId) {
  if (!ruleId) {
    return [];
  }

  if (ruleId === 'all') {
    const { data } = await api.get('/results');
    const results = Array.isArray(data) ? data : data?.results || [];
    return results.map((result) => normalizeRuleResult(result));
  }

  const { data } = await api.get(`/rules/${ruleId}/results`);
  const results = Array.isArray(data) ? data : data?.results || [];
  return results.map((result) => normalizeRuleResult(result, { ruleId }));
}

export async function runSavedRule(ruleId, fallbackRule = {}) {
  const { data } = await api.post(`/rules/${ruleId}/run`);
  return normalizeRuleResult(data, {
    ruleId,
    ruleName: fallbackRule.ruleName,
    datasetName: fallbackRule.datasetName,
    sql: fallbackRule.sql,
  });
}

export async function getSchedulerRules() {
  const { data } = await api.get('/scheduler/rules');
  return Array.isArray(data) ? data : data?.rules || [];
}
