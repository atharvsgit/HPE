const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const INTEGER_PATTERN = /^-?\d+$/;
const DECIMAL_PATTERN = /^-?\d+(\.\d+)?$/;
const BOOLEAN_PATTERN = /^(true|false|yes|no)$/i;

const isEmptyValue = (value) =>
  value === undefined || value === null || String(value).trim() === '';

const toLabel = (value, index) => {
  const cleaned = String(value || '')
    .trim()
    .replace(/\s+/g, '_');

  return cleaned || `column_${index + 1}`;
};

const parseCsvText = (text) => {
  const rows = [];
  let currentCell = '';
  let currentRow = [];
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const nextCharacter = text[index + 1];

    if (character === '"') {
      if (inQuotes && nextCharacter === '"') {
        currentCell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }

      continue;
    }

    if (character === ',' && !inQuotes) {
      currentRow.push(currentCell);
      currentCell = '';
      continue;
    }

    if (character === '\n' && !inQuotes) {
      currentRow.push(currentCell);
      rows.push(currentRow);
      currentCell = '';
      currentRow = [];
      continue;
    }

    if (character !== '\r') {
      currentCell += character;
    }
  }

  if (currentCell.length || currentRow.length) {
    currentRow.push(currentCell);
    rows.push(currentRow);
  }

  return rows.filter((row) => row.some((cell) => String(cell || '').trim() !== ''));
};

const inferDataType = (values) => {
  const nonEmptyValues = values.filter((value) => !isEmptyValue(value)).slice(0, 50);

  if (!nonEmptyValues.length) {
    return 'varchar';
  }

  if (nonEmptyValues.every((value) => UUID_PATTERN.test(String(value).trim()))) {
    return 'uuid';
  }

  if (nonEmptyValues.every((value) => INTEGER_PATTERN.test(String(value).trim()))) {
    return 'integer';
  }

  if (nonEmptyValues.every((value) => DECIMAL_PATTERN.test(String(value).trim()))) {
    return 'decimal';
  }

  if (nonEmptyValues.every((value) => BOOLEAN_PATTERN.test(String(value).trim()))) {
    return 'boolean';
  }

  if (
    nonEmptyValues.every((value) => {
      const timestamp = Date.parse(String(value).trim());
      return Number.isFinite(timestamp);
    })
  ) {
    return 'timestamp';
  }

  return 'varchar';
};

const getDatasetColumns = (rows = []) =>
  Array.from(
    new Set(
      rows.flatMap((row) => Object.keys(row || {})).filter((key) => key !== '__rowId'),
    ),
  );

const normalizeRowsToColumns = (rows = [], columns = []) =>
  rows.map((row) =>
    columns.reduce(
      (accumulator, column) => ({
        ...accumulator,
        [column]: row?.[column] ?? '',
      }),
      {},
    ),
  );

const withRowIds = (rows = []) =>
  rows.map((row, rowIndex) => ({
    ...row,
    __rowId: `ROW-${String(rowIndex + 1).padStart(4, '0')}`,
  }));

export function buildSchemaFromRows(rows = []) {
  const columns = getDatasetColumns(rows);

  return columns.map((columnName) => {
    const values = rows.map((row) => row?.[columnName]);

    return {
      columnName,
      dataType: inferDataType(values),
      nullCount: values.filter((value) => isEmptyValue(value)).length,
    };
  });
}

export async function profileFileLocally(file, subType = 'csv') {
  const format = (subType || '').toLowerCase();

  if (!file) {
    return null;
  }

  if (format !== 'csv' && !file.name.toLowerCase().endsWith('.csv')) {
    return {
      dataset: {
        id: `file-${format}-${Date.now()}`,
        name: file.name,
        sourceType: 'file',
        subType: format,
        records: 0,
        owner: 'Local browser session',
        lastRefreshed: new Date().toISOString(),
      },
      schema: [],
      rows: [],
      profiledLocally: false,
      message:
        'Parquet profiling requires backend support in this frontend-only environment.',
    };
  }

  const text = await file.text();
  const parsedRows = parseCsvText(text);

  if (!parsedRows.length) {
    return {
      dataset: {
        id: `file-csv-${Date.now()}`,
        name: file.name,
        sourceType: 'file',
        subType: 'csv',
        records: 0,
        owner: 'Local browser session',
        lastRefreshed: new Date().toISOString(),
      },
      schema: [],
      rows: [],
      profiledLocally: true,
      message: 'The file was read successfully but no usable rows were detected.',
    };
  }

  const headers = parsedRows[0].map((header, index) => toLabel(header, index));
  const records = parsedRows.slice(1).map((row, rowIndex) =>
    headers.reduce(
      (accumulator, header, columnIndex) => ({
        ...accumulator,
        __rowId: `ROW-${String(rowIndex + 1).padStart(4, '0')}`,
        [header]: row[columnIndex] ?? '',
      }),
      {},
    ),
  );

  const schema = buildSchemaFromRows(records);

  return {
    dataset: {
      id: `file-csv-${Date.now()}`,
      name: file.name,
      sourceType: 'file',
      subType: 'csv',
      records: records.length,
      owner: 'Local browser session',
      lastRefreshed: new Date().toISOString(),
    },
    schema,
    rows: records,
    profiledLocally: true,
    message: `Profiled ${records.length} rows directly in the browser.`,
  };
}

export function appendProfileData({
  currentDataset,
  currentRows = [],
  incomingData,
}) {
  if (!currentDataset || !currentRows.length || !incomingData?.rows?.length) {
    return null;
  }

  const mergedColumns = Array.from(
    new Set([
      ...getDatasetColumns(currentRows),
      ...getDatasetColumns(incomingData.rows),
    ]),
  );
  const normalizedRows = withRowIds([
    ...normalizeRowsToColumns(currentRows, mergedColumns),
    ...normalizeRowsToColumns(incomingData.rows, mergedColumns),
  ]);
  const nextSchema = buildSchemaFromRows(normalizedRows);

  return {
    dataset: {
      ...currentDataset,
      records: normalizedRows.length,
      lastRefreshed: new Date().toISOString(),
    },
    schema: nextSchema,
    rows: normalizedRows,
    profiledLocally: true,
    message: `Appended ${incomingData.rows.length} rows into ${currentDataset.name}.`,
  };
}

const buildFailureMessage = (rule, column, value, payload) => {
  if (rule === 'between') {
    return `${column} value ${value} is outside ${payload.min} to ${payload.max}.`;
  }

  if (rule === 'regex') {
    return `${column} value ${value || '<empty>'} failed pattern ${payload.pattern}.`;
  }

  return `${column} is required but missing for this row.`;
};

const getSeverity = (rule, value) => {
  if (rule === 'not_null') {
    return 'critical';
  }

  if (rule === 'between' && Number(value) === 0) {
    return 'critical';
  }

  return rule === 'regex' ? 'medium' : 'high';
};

export function runLocalValidation(payload, datasetRows = []) {
  if (!datasetRows.length) {
    return null;
  }

  const startedAt = performance.now();
  const failedRows = datasetRows
    .map((row, index) => {
      const value = row[payload.column];
      let failed = false;

      if (payload.rule === 'between') {
        const numericValue = Number(value);
        failed =
          isEmptyValue(value) ||
          Number.isNaN(numericValue) ||
          numericValue < Number(payload.min) ||
          numericValue > Number(payload.max);
      }

      if (payload.rule === 'regex') {
        const pattern = new RegExp(payload.pattern);
        failed = isEmptyValue(value) || !pattern.test(String(value));
      }

      if (payload.rule === 'not_null') {
        failed = isEmptyValue(value);
      }

      if (!failed) {
        return null;
      }

      return {
        rowId: row.__rowId || `ROW-${String(index + 1).padStart(4, '0')}`,
        column: payload.column,
        value: isEmptyValue(value) ? 'null' : String(value),
        message: buildFailureMessage(payload.rule, payload.column, value, payload),
        severity: getSeverity(payload.rule, value),
      };
    })
    .filter(Boolean);

  const checkedRows = datasetRows.length;
  const passedRows = checkedRows - failedRows.length;
  const elapsed = ((performance.now() - startedAt) / 1000).toFixed(2);

  return {
    summary: {
      column: payload.column,
      rule: payload.rule,
      checkedRows,
      passedRows,
      failedRows: failedRows.length,
      executionTime: `${elapsed}s`,
    },
    failedRows,
  };
}

export { isEmptyValue };
