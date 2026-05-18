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

const loadMockState = (key) => {
  try {
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
};

const saveMockState = (key, data) => {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {}
};

let mockSavedRules = loadMockState('mockSavedRules');
let mockRuleResults = loadMockState('mockRuleResults');

const getRowsFromResponse = (response = {}) => {
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
  datasetName: rule.dataset_name ?? rule.datasetName ?? rule.dataset ?? 'Enterprise dataset',
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
      'Enterprise dataset',
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

const simulateLocalExecution = (payload, datasetRows, localPayload) => {
  const rule = localPayload.rule || 'custom_sql';
  const column = localPayload.column;
  let resultRows = [];

  if (datasetRows && datasetRows.length > 0 && column) {
    resultRows = datasetRows.filter(row => {
      const val = row[column];
      let isMatch = false;

      if (rule === 'not_null') {
        isMatch = val !== null && val !== undefined && String(val).trim() !== '';
      } else if (rule === 'equals') {
        isMatch = String(val).trim() === String(localPayload.value || '').trim();
      } else if (rule === 'regex') {
        if (!val) {
          isMatch = false;
        } else {
          try {
            isMatch = new RegExp(localPayload.pattern).test(String(val));
          } catch {
            isMatch = false;
          }
        }
      } else if (rule === 'between') {
        const num = Number(val);
        if (!isNaN(num)) {
          isMatch = num >= Number(localPayload.min) && num <= Number(localPayload.max);
        }
      } else {
        isMatch = true;
      }

      return localPayload.semanticMode === 'query' ? isMatch : !isMatch;
    });
  }

  const resultCount = resultRows.length;
  const checkedRows = datasetRows ? datasetRows.length : 0;

  return {
    id: `sim-${Date.now()}`,
    ruleId: localPayload.rule_id || null,
    ruleName: localPayload.rule_name || payload.rule_name || payload.ruleName || 'Simulated Rule',
    datasetId: localPayload.dataset_id || payload.dataset_id,
    datasetName: localPayload.dataset_name || payload.dataset_name || 'Local Dataset',
    sql: localPayload.sql || payload.sql || '-- simulated execution',
    status: 'completed',
    executionTime: new Date().toISOString(),
    duration: Math.max(0.1, (checkedRows * 0.0005)).toFixed(2) + 's',
    checkedRows,
    passedRows: localPayload.semanticMode === 'query' ? resultCount : checkedRows - resultCount,
    failedRows: localPayload.semanticMode === 'query' ? checkedRows - resultCount : resultCount,
    resultRows: resultCount,
    rows: resultRows.slice(0, 100),
    expectedResult: { type: 'zero_violations' },
    source: 'local_simulation'
  };
};

export async function runAdHocRule(payload, { datasetRows = [], localPayload = {} } = {}) {
  const requestPayload = {
    rule_name: payload.rule_name || payload.ruleName || 'Ad hoc business rule',
    sql: payload.sql,
    expected_result: payload.expected_result || { type: 'zero_violations' },
  };

  try {
    const { data } = await api.post('/rules/run', requestPayload);

    return normalizeRuleResult(data, {
      ruleName: requestPayload.rule_name,
      datasetId: payload.dataset_id,
      datasetName: payload.dataset_name,
      sql: requestPayload.sql,
      expectedResult: requestPayload.expected_result,
    });
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      const result = simulateLocalExecution(payload, datasetRows, localPayload);
      mockRuleResults.push(result);
      saveMockState('mockRuleResults', mockRuleResults);
      return result;
    }
    throw error;
  }
}

export async function createSavedRule(payload) {
  const requestPayload = {
    rule_name: payload.rule_name || payload.ruleName,
    sql: payload.sql,
    expected_result: payload.expected_result || { type: 'zero_violations' },
    schedule_cron: payload.schedule_cron ?? payload.scheduleCron ?? null,
    is_enabled: payload.is_enabled ?? payload.isEnabled ?? true,
  };

  try {
    const { data } = await api.post('/rules', requestPayload);
    return normalizeRule(data);
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      const newRule = {
        id: `mock-${Date.now()}`,
        ruleName: requestPayload.rule_name,
        sql: requestPayload.sql,
        expectedResult: requestPayload.expected_result,
        status: 'active',
        createdAt: new Date().toISOString()
      };
      mockSavedRules.push(newRule);
      saveMockState('mockSavedRules', mockSavedRules);
      return newRule;
    }
    throw error;
  }
}

export async function getSavedRules() {
  try {
    const { data } = await api.get('/rules');
    const rules = Array.isArray(data) ? data : data?.rules || [];
    return rules.map(normalizeRule);
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      return [...mockSavedRules];
    }
    throw error;
  }
}

export async function getRuleResults(ruleId) {
  if (!ruleId) {
    return [];
  }

  try {
    if (ruleId === 'all') {
      await api.get('/rules').catch(err => {
        if (err.code === 'ERR_NETWORK') throw err;
      });
      const rules = await getSavedRules();
      const allResults = await Promise.all(
        rules.map(rule => api.get(`/rules/${rule.id}/results`).catch(() => ({ data: [] })))
      );
      const flattened = allResults.flatMap((res, index) => {
        const data = Array.isArray(res.data) ? res.data : res.data?.results || [];
        return data.map((result) => normalizeRuleResult(result, { ruleId: rules[index].id }));
      });
      return flattened.sort((a, b) => new Date(b.executionTime).getTime() - new Date(a.executionTime).getTime());
    }

    const { data } = await api.get(`/rules/${ruleId}/results`);
    const results = Array.isArray(data) ? data : data?.results || [];
    return results.map((result) => normalizeRuleResult(result, { ruleId }));
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      if (ruleId === 'all') {
        return [...mockRuleResults].sort((a, b) => new Date(b.executionTime).getTime() - new Date(a.executionTime).getTime());
      }
      return mockRuleResults.filter(r => String(r.ruleId) === String(ruleId)).sort((a, b) => new Date(b.executionTime).getTime() - new Date(a.executionTime).getTime());
    }
    throw error;
  }
}

export async function runSavedRule(ruleId, fallbackRule = {}) {
  try {
    const { data } = await api.post(`/rules/${ruleId}/run`);
    return normalizeRuleResult(data, {
      ruleId,
      ruleName: fallbackRule.ruleName,
      datasetName: fallbackRule.datasetName,
      sql: fallbackRule.sql,
    });
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      return {
        id: `sim-${Date.now()}`,
        ruleId,
        ruleName: fallbackRule.ruleName || 'Simulated Rule',
        datasetName: fallbackRule.datasetName || 'Local Dataset',
        sql: fallbackRule.sql || '-- simulated execution',
        status: 'completed',
        executionTime: new Date().toISOString(),
        duration: '0.10s',
        checkedRows: 1,
        passedRows: 0,
        failedRows: 1,
        resultRows: 1,
        rows: [{ info: 'Backend required to execute pure SQL', query: fallbackRule.sql || 'N/A' }],
        expectedResult: { type: 'zero_violations' },
        source: 'local_simulation'
      };
      mockRuleResults.push(result);
      saveMockState('mockRuleResults', mockRuleResults);
      return result;
    }
    throw error;
  }
}

export async function getSchedulerRules() {
  try {
    const { data } = await api.get('/scheduler/rules');
    return Array.isArray(data) ? data : data?.rules || [];
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      return [];
    }
    throw error;
  }
}
