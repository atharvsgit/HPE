const isEmptyValue = (value) =>
  value === null ||
  value === undefined ||
  String(value).trim() === '' ||
  Number.isNaN(value) ||
  value === 'NaN' ||
  value === 'null';

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const getSeverityFromRate = (rate) => {
  if (rate >= 18) {
    return 'critical';
  }

  if (rate >= 8) {
    return 'high';
  }

  return 'medium';
};

const formatDurationFromRows = (rows) =>
  `${Math.max(0.35, rows * 0.0025).toFixed(rows > 2500 ? 1 : 2)}s`;

export function deriveObservabilityData({
  selectedDataset,
  schemaMetadata = [],
  validationResults = null,
  datasetRows = [],
}) {
  if (!selectedDataset) {
    return null;
  }

  const columns =
    schemaMetadata.length > 0
      ? schemaMetadata
      : Object.keys(datasetRows[0] || {})
          .filter((key) => key !== '__rowId')
          .map((columnName) => ({
            columnName,
            dataType: 'varchar',
            nullCount: datasetRows.filter((row) => isEmptyValue(row[columnName])).length,
          }));

  const totalRows =
    datasetRows.length ||
    validationResults?.summary?.checkedRows ||
    selectedDataset.records ||
    0;

  if (!columns.length && !validationResults) {
    return null;
  }

  const totalColumns = Math.max(columns.length, 1);
  const totalCells = totalRows * totalColumns;
  const totalNulls = columns.reduce(
    (sum, column) => sum + (Number(column.nullCount) || 0),
    0,
  );

  const impactedRows = datasetRows.length
    ? datasetRows.filter((row) =>
        columns.some((column) => isEmptyValue(row[column.columnName])),
      ).length
    : Math.min(totalRows || totalNulls, totalNulls);

  const failed =
    validationResults?.summary?.failedRows ??
    impactedRows ??
    0;
  const checkedRows = validationResults?.summary?.checkedRows || totalRows;
  const passed =
    validationResults?.summary?.passedRows ??
    Math.max((checkedRows || totalRows) - failed, 0);

  const completenessRatio = totalCells
    ? clamp(1 - totalNulls / totalCells, 0, 1)
    : checkedRows
      ? clamp(passed / checkedRows, 0, 1)
      : 0;
  const validationRatio = checkedRows
    ? clamp(passed / checkedRows, 0, 1)
    : completenessRatio;

  const score = Math.round(
    clamp(completenessRatio * 0.58 + validationRatio * 0.42, 0, 1) * 100,
  );

  const status =
    score >= 95 ? 'Excellent' : score >= 85 ? 'Stable' : score >= 70 ? 'Watch' : 'At Risk';

  const qualityScore = {
    score,
    passed,
    failed,
    totalChecks: checkedRows || totalRows,
    status,
    trendLabel: validationResults
      ? 'Derived from validation failures'
      : 'Derived from connected profile',
    lastRun: validationResults
      ? new Date().toISOString()
      : selectedDataset.lastRefreshed || new Date().toISOString(),
    completeness: Math.round(completenessRatio * 100),
  };

  const columnRiskPoints = columns.map((column, index) => {
    const nullRate = totalRows
      ? (Number(column.nullCount || 0) / totalRows) * 100
      : Number(column.nullCount || 0);
    const validationPenalty =
      validationResults?.summary?.column === column.columnName && checkedRows
        ? (failed / checkedRows) * 25
        : 0;
    const riskScore = Number((nullRate + validationPenalty).toFixed(2));

    return {
      x: index + 1,
      y: riskScore,
      label: column.columnName,
      nullRate: Number(nullRate.toFixed(2)),
      status: 'normal',
    };
  });

  const averageRisk =
    columnRiskPoints.reduce((sum, point) => sum + point.y, 0) /
      Math.max(columnRiskPoints.length, 1) || 0;
  const variance =
    columnRiskPoints.reduce((sum, point) => sum + (point.y - averageRisk) ** 2, 0) /
      Math.max(columnRiskPoints.length, 1) || 0;
  const riskThreshold = averageRisk + Math.sqrt(variance) * 0.75;

  const anomalies = columnRiskPoints.map((point) => ({
    ...point,
    status:
      point.y > riskThreshold ||
      validationResults?.summary?.column === point.label
        ? 'anomaly'
        : 'normal',
  }));

  const currentCompleteness = columns.map((column) => {
    if (!totalRows) {
      return 100;
    }

    return Number(
      (100 - ((Number(column.nullCount || 0) / totalRows) * 100)).toFixed(2),
    );
  });

  const baselineCompleteness =
    currentCompleteness.reduce((sum, value) => sum + value, 0) /
      Math.max(currentCompleteness.length, 1) || 100;
  const reference = currentCompleteness.map(() =>
    Number(baselineCompleteness.toFixed(2)),
  );
  const maxDrift = currentCompleteness.reduce(
    (largestGap, currentValue) =>
      Math.max(largestGap, Math.abs(currentValue - baselineCompleteness)),
    0,
  );

  const derivedFailures = validationResults?.failedRows?.length
    ? validationResults.failedRows
    : datasetRows.length
      ? datasetRows
          .flatMap((row) =>
            columns
              .filter((column) => isEmptyValue(row[column.columnName]))
              .map((column) => ({
                rowId: row.__rowId,
                column: column.columnName,
                message: `${column.nullCount} missing values detected for ${column.columnName}.`,
                severity: getSeverityFromRate(
                  totalRows ? (column.nullCount / totalRows) * 100 : column.nullCount,
                ),
              })),
          )
          .slice(0, 20)
      : columns
          .filter((column) => Number(column.nullCount) > 0)
          .map((column, index) => ({
            rowId: `COL-${String(index + 1).padStart(3, '0')}`,
            column: column.columnName,
            message: `${column.nullCount} null values were detected during schema profiling.`,
            severity: getSeverityFromRate(
              totalRows ? (column.nullCount / totalRows) * 100 : column.nullCount,
            ),
          }));

  const report = {
    summary: {
      anomalies: anomalies.filter((point) => point.status === 'anomaly').length,
      driftLevel:
        maxDrift >= 12 ? 'High' : maxDrift >= 6 ? 'Moderate' : 'Low',
      latestIncident: derivedFailures[0]?.rowId || 'None',
      pipelineLatency:
        validationResults?.summary?.executionTime || formatDurationFromRows(totalRows),
    },
    anomalies,
    drift: {
      labels: columns.map((column) => column.columnName),
      reference,
      current: currentCompleteness,
    },
    failures: derivedFailures,
  };

  return {
    qualityScore,
    report,
  };
}
