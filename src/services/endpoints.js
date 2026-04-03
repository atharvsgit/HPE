import api from './api';
import { profileFileLocally, runLocalValidation } from './localDataset';

const wait = (duration = 650) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, duration);
  });

const DEFAULT_SCHEMA = [
  { columnName: 'order_id', dataType: 'uuid', nullCount: 0 },
  { columnName: 'customer_id', dataType: 'varchar', nullCount: 14 },
  { columnName: 'country', dataType: 'varchar', nullCount: 2 },
  { columnName: 'order_amount', dataType: 'decimal', nullCount: 6 },
  { columnName: 'order_status', dataType: 'varchar', nullCount: 0 },
  { columnName: 'order_date', dataType: 'timestamp', nullCount: 0 },
];

const shouldFallbackToMock = (error) =>
  !error?.response || [404, 500, 502, 503, 504].includes(error.status);

const buildDatasetResponse = ({
  sourceType = 'file',
  subType = 'csv',
  name = 'orders_snapshot.csv',
}) => ({
  dataset: {
    id: `${sourceType}-${subType}-${Date.now()}`,
    name,
    sourceType,
    subType,
    records: 12800,
    owner: 'Data Platform',
    lastRefreshed: '2026-04-03T10:45:00Z',
  },
  schema: DEFAULT_SCHEMA,
});

const buildValidationMock = (payload) => {
  const column = payload.column || 'order_amount';
  const rule = payload.rule || 'not_null';
  const failureMessages = {
    between: 'Value fell outside the expected business range.',
    regex: 'Value failed the configured pattern match.',
    not_null: 'Value must be present for downstream reporting.',
  };

  const sampleValue =
    rule === 'between' ? '14250.99' : rule === 'regex' ? 'PENDING-01' : 'null';

  const failedRows = [
    {
      rowId: 'ROW-0189',
      column,
      value: sampleValue,
      message: failureMessages[rule],
      severity: 'high',
    },
    {
      rowId: 'ROW-0417',
      column,
      value: rule === 'regex' ? 'pending' : sampleValue,
      message: failureMessages[rule],
      severity: 'medium',
    },
    {
      rowId: 'ROW-0831',
      column,
      value: rule === 'not_null' ? 'null' : sampleValue,
      message: failureMessages[rule],
      severity: 'high',
    },
    {
      rowId: 'ROW-1204',
      column,
      value: rule === 'between' ? '0.38' : sampleValue,
      message: failureMessages[rule],
      severity: 'critical',
    },
  ];

  return {
    summary: {
      column,
      rule,
      checkedRows: 12800,
      passedRows: 12481,
      failedRows: failedRows.length,
      executionTime: '1.8s',
    },
    failedRows,
  };
};

const buildHeadersObject = (headers = []) =>
  headers.reduce((accumulator, entry) => {
    if (entry?.key && entry?.value) {
      accumulator[entry.key] = entry.value;
    }

    return accumulator;
  }, {});

export async function uploadDataset(formData) {
  try {
    const { data } = await api.post('/upload-dataset', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    return data;
  } catch (error) {
    if (!shouldFallbackToMock(error)) {
      throw error;
    }

    await wait();

    const file = formData.get('file');
    const subType = formData.get('sub_type') || 'csv';
    const localProfile = await profileFileLocally(file, subType);

    if (localProfile) {
      return localProfile;
    }

    return buildDatasetResponse({
      sourceType: 'file',
      subType,
      name: file?.name || 'orders_snapshot.csv',
    });
  }
}

export async function connectDatabase(payload) {
  try {
    const { data } = await api.post('/connect-database', payload);
    return data;
  } catch (error) {
    if (!shouldFallbackToMock(error)) {
      throw error;
    }

    await wait();

    let sourceName = `${payload.sub_type} connection`;

    if (payload.source_type === 'database') {
      sourceName =
        payload.sub_type === 'mongodb'
          ? `${payload.config.collection || 'collection'}`
          : `${payload.config.table || 'table'} snapshot`;
    }

    if (payload.source_type === 'api') {
      sourceName = payload.config.url || 'REST endpoint';
    }

    if (payload.source_type === 'cloud') {
      sourceName =
        payload.sub_type === 'bigquery'
          ? `${payload.config.dataset || 'dataset'}.${payload.config.table || 'table'}`
          : `${payload.config.database || 'warehouse'} stream`;
    }

    return buildDatasetResponse({
      sourceType: payload.source_type,
      subType: payload.sub_type,
      name: sourceName,
    });
  }
}

export async function runValidation(payload, datasetRows = []) {
  try {
    const { data } = await api.post('/run-validation', payload);
    return data;
  } catch (error) {
    if (!shouldFallbackToMock(error)) {
      throw error;
    }

    await wait();

    const localResult = runLocalValidation(payload, datasetRows);
    return localResult || buildValidationMock(payload);
  }
}

export async function getReport(datasetId) {
  if (!datasetId) {
    return null;
  }

  try {
    const { data } = await api.get('/report', {
      params: datasetId ? { dataset_id: datasetId } : {},
    });
    return data;
  } catch (error) {
    if (!shouldFallbackToMock(error)) {
      throw error;
    }

    return null;
  }
}

export async function getQualityScore(datasetId) {
  if (!datasetId) {
    return null;
  }

  try {
    const { data } = await api.get('/quality-score', {
      params: datasetId ? { dataset_id: datasetId } : {},
    });
    return data;
  } catch (error) {
    if (!shouldFallbackToMock(error)) {
      throw error;
    }

    return null;
  }
}

export { buildHeadersObject };
