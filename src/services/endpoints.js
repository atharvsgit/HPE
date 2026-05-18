import api from './api';

const buildHeadersObject = (headers = []) =>
  headers.reduce((accumulator, entry) => {
    if (entry?.key && entry?.value) {
      accumulator[entry.key] = entry.value;
    }

    return accumulator;
  }, {});

const guessDataType = (values) => {
  const nonNull = values.filter(v => v !== null && v !== undefined && String(v).trim() !== '');
  if (nonNull.length === 0) return 'varchar';

  const isNumeric = (v) => /^-?\d+(\.\d+)?$/.test(String(v).trim());
  const isInteger = (v) => /^-?\d+$/.test(String(v).trim());
  const isBoolean = (v) => ['true', 'false', '1', '0', 'yes', 'no'].includes(String(v).trim().toLowerCase());
  const isDate = (v) => !isNaN(Date.parse(String(v).trim()));

  if (nonNull.every(isInteger)) return 'integer';
  if (nonNull.every(isNumeric)) return 'float';
  if (nonNull.every(isBoolean)) return 'boolean';
  if (nonNull.every(isDate)) return 'timestamp';
  return 'varchar';
};

export async function uploadDataset(formData) {
  const file = formData.get('file');

  // Since the backend does not have an upload endpoint, we parse CSV files locally for demos
  if (file && (file.name.endsWith('.csv') || file.name.endsWith('.txt'))) {
    const text = await file.text();
    const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);

    if (lines.length > 0) {
      const headers = lines[0].split(',').map(h => h.trim());
      const rows = lines.slice(1).map((line, i) => {
        const values = line.split(',');
        const row = { __rowId: `row-${i}` };
        headers.forEach((header, index) => {
          row[header] = values[index]?.trim() || '';
        });
        return row;
      });

      return {
        message: 'CSV parsed successfully',
        dataset: {
          id: `csv-${Date.now()}`,
          name: file.name,
          sourceType: 'file',
          records: rows.length,
          lastRefreshed: new Date().toISOString()
        },
        schema: headers.map(h => ({
          columnName: h,
          dataType: guessDataType(rows.map(r => r[h])),
          nullCount: rows.filter(r => r[h] === '').length
        })),
        rows
      };
    }
  }

  // Fallback to API if it's another format or backend upload is supported later
  try {
    const { data } = await api.post('/upload-dataset', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  } catch (error) {
    if (error.code === 'ERR_NETWORK') {
      throw new Error('Network Error: The backend server could not be reached. Ensure it is running on port 8000.');
    }
    throw error;
  }
}

export async function connectDatabase(payload) {
  const { data } = await api.post('/connect-database', payload);
  return data;
}

export async function runValidation(payload, datasetRows = []) {
  const { data } = await api.post('/run-validation', payload);
  return data;
}

export async function getReport(datasetId) {
  if (!datasetId) {
    return null;
  }

  const { data } = await api.get('/report', {
    params: datasetId ? { dataset_id: datasetId } : {},
  });
  return data;
}

export async function getQualityScore(datasetId) {
  if (!datasetId) {
    return null;
  }

  const { data } = await api.get('/quality-score', {
    params: datasetId ? { dataset_id: datasetId } : {},
  });
  return data;
}

export { buildHeadersObject };
