import { useEffect, useMemo, useState } from 'react';
import ConfirmationModal from '../components/common/ConfirmationModal';
import StatusBadge from '../components/common/StatusBadge';
import { Link, useNavigate } from 'react-router-dom';
import Loader from '../components/common/Loader';
import ApiForm from '../components/ingestion/ApiForm';
import CloudForm from '../components/ingestion/CloudForm';
import DatabaseForm from '../components/ingestion/DatabaseForm';
import FileUpload from '../components/ingestion/FileUpload';
import SchemaTable from '../components/ingestion/SchemaTable';
import SourceSelector from '../components/ingestion/SourceSelector';
import { useDataset } from '../context/DatasetContext';
import {
  buildHeadersObject,
  connectDatabase,
  uploadDataset,
} from '../services/endpoints';

const initialDatabaseState = {
  subType: 'postgresql',
  host: '',
  port: '5432',
  database: '',
  username: '',
  password: '',
  table: '',
  uri: '',
  collection: '',
};

const initialApiState = {
  url: '',
  method: 'GET',
  headers: [{ key: '', value: '' }],
};

const initialCloudState = {
  subType: 'snowflake',
  account: '',
  warehouse: '',
  database: '',
  schema: '',
  username: '',
  password: '',
  project: '',
  dataset: '',
  table: '',
  credentials: '{\n  "type": "service_account"\n}',
};

const sourceDescriptions = {
  file: 'Upload CSV or Parquet files with schema introspection and profiling.',
  database:
    'Connect operational and analytical stores such as PostgreSQL, MySQL, and MongoDB.',
  api: 'Register a REST endpoint with method and headers for direct ingestion.',
  cloud:
    'Attach enterprise warehouses like Snowflake and BigQuery for governed observability.',
};

const isBlank = (value) => String(value ?? '').trim() === '';

export default function IngestionPage() {
  const navigate = useNavigate();
  const {
    appendDataset,
    datasetRows,
    replaceDataset,
    resetDataset,
    selectedDataset,
    schemaMetadata,
    validationResults,
    pushToast,
  } = useDataset();

  const [sourceType, setSourceType] = useState('file');
  const [fileState, setFileState] = useState({ file: null, format: 'csv' });
  const [databaseState, setDatabaseState] = useState(initialDatabaseState);
  const [apiState, setApiState] = useState(initialApiState);
  const [cloudState, setCloudState] = useState(initialCloudState);
  const [appendToExisting, setAppendToExisting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [confirmationState, setConfirmationState] = useState({
    type: null,
  });

  const sourceSummary = useMemo(() => sourceDescriptions[sourceType], [sourceType]);
  const hasExistingDataset = Boolean(selectedDataset);
  const canAppend = sourceType === 'file' && hasExistingDataset && datasetRows.length > 0;
  const currentRowCount = datasetRows.length || selectedDataset?.records || 0;
  const currentColumnCount = schemaMetadata.length || 0;
  const datasetStatus = validationResults
    ? {
        label: 'Validation Completed',
        tone:
          (validationResults.summary?.failedRows ||
            validationResults.failedRows?.length ||
            0) > 0
            ? 'error'
            : 'success',
      }
    : selectedDataset
      ? {
          label: 'Dataset Loaded',
          tone: 'success',
        }
      : {
          label: 'No Dataset',
          tone: 'pending',
        };
  const submitButtonLabel = hasExistingDataset
    ? appendToExisting && canAppend
      ? 'Append Dataset'
      : 'Replace Dataset'
    : 'Connect Dataset';

  useEffect(() => {
    if (!canAppend && appendToExisting) {
      setAppendToExisting(false);
    }
  }, [appendToExisting, canAppend]);

  const buildConnectionPayload = () => {
    if (sourceType === 'database') {
      if (databaseState.subType === 'mongodb') {
        return {
          source_type: 'database',
          sub_type: 'mongodb',
          config: {
            uri: databaseState.uri,
            database: databaseState.database,
            collection: databaseState.collection,
          },
        };
      }

      return {
        source_type: 'database',
        sub_type: databaseState.subType,
        config: {
          host: databaseState.host,
          port: databaseState.port,
          database: databaseState.database,
          username: databaseState.username,
          password: databaseState.password,
          table: databaseState.table,
        },
      };
    }

    if (sourceType === 'api') {
      return {
        source_type: 'api',
        sub_type: 'rest',
        config: {
          url: apiState.url,
          method: apiState.method,
          headers: buildHeadersObject(apiState.headers),
        },
      };
    }

    if (cloudState.subType === 'bigquery') {
      let parsedCredentials = cloudState.credentials;

      if (cloudState.credentials?.trim()) {
        parsedCredentials = JSON.parse(cloudState.credentials);
      }

      return {
        source_type: 'cloud',
        sub_type: 'bigquery',
        config: {
          project: cloudState.project,
          dataset: cloudState.dataset,
          table: cloudState.table,
          credentials: parsedCredentials,
        },
      };
    }

    return {
      source_type: 'cloud',
      sub_type: 'snowflake',
      config: {
        account: cloudState.account,
        warehouse: cloudState.warehouse,
        database: cloudState.database,
        schema: cloudState.schema,
        username: cloudState.username,
        password: cloudState.password,
      },
    };
  };

  const closeConfirmation = () => {
    setConfirmationState({ type: null });
  };

  const validateConnectionInputs = () => {
    if (sourceType === 'file') {
      if (!fileState.file) {
        return 'Select a CSV or Parquet file before submitting.';
      }

      return '';
    }

    if (sourceType === 'database') {
      if (databaseState.subType === 'mongodb') {
        if (isBlank(databaseState.uri)) {
          return 'Enter the MongoDB URI before submitting.';
        }

        if (isBlank(databaseState.database) || isBlank(databaseState.collection)) {
          return 'Enter both the MongoDB database and collection before submitting.';
        }

        return '';
      }

      if (
        [
          databaseState.host,
          databaseState.port,
          databaseState.database,
          databaseState.username,
          databaseState.password,
          databaseState.table,
        ].some(isBlank)
      ) {
        return 'Complete host, port, database, username, password, and table before submitting.';
      }

      return '';
    }

    if (sourceType === 'api') {
      if (isBlank(apiState.url)) {
        return 'Enter the API URL before submitting.';
      }

      return '';
    }

    if (cloudState.subType === 'bigquery') {
      if (
        [cloudState.project, cloudState.dataset, cloudState.table, cloudState.credentials].some(
          isBlank,
        )
      ) {
        return 'Complete project, dataset, table, and credentials JSON before submitting.';
      }

      try {
        JSON.parse(cloudState.credentials);
      } catch {
        return 'Credentials JSON must be valid JSON before submitting.';
      }

      return '';
    }

    if (
      [
        cloudState.account,
        cloudState.warehouse,
        cloudState.database,
        cloudState.schema,
        cloudState.username,
        cloudState.password,
      ].some(isBlank)
    ) {
      return 'Complete account, warehouse, database, schema, username, and password before submitting.';
    }

    return '';
  };

  const executeSubmit = async (mode = 'connect') => {
    setSubmitError('');
    setSubmitting(true);

    try {
      const validationMessage = validateConnectionInputs();

      if (validationMessage) {
        throw new Error(validationMessage);
      }

      let response;

      if (sourceType === 'file') {
        if (!fileState.file) {
          throw new Error('Select a CSV or Parquet file before submitting.');
        }

        const formData = new FormData();
        formData.append('source_type', 'file');
        formData.append('sub_type', fileState.format);
        formData.append('file', fileState.file);

        response = await uploadDataset(formData);
      } else {
        response = await connectDatabase(buildConnectionPayload());
      }

      if (mode === 'append') {
        const appendedData = appendDataset(response);

        if (!appendedData) {
          throw new Error(
            'Append is available only for datasets with row-level data loaded in this session.',
          );
        }

        setAppendToExisting(false);
        pushToast({
          tone: 'success',
          title: 'Dataset appended',
          message:
            appendedData.message ||
            `${response.dataset?.name || 'Dataset'} was appended successfully.`,
        });
      } else {
        replaceDataset(response);
        pushToast({
          tone: 'success',
          title: mode === 'replace' ? 'Dataset replaced' : 'Source connected',
          message:
            response.message ||
            `${response.dataset?.name || 'Dataset'} is ready for validation.`,
        });
      }

      navigate('/rules');
    } catch (error) {
      setSubmitError(
        error.message ||
          'The source could not be connected. Check the required inputs and try again.',
      );
      pushToast({
        tone: 'error',
        title: 'Connection failed',
        message:
          error.message ||
          'The source could not be connected. Check the payload and try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitError('');

    const validationMessage = validateConnectionInputs();

    if (validationMessage) {
      setSubmitError(validationMessage);
      pushToast({
        tone: 'error',
        title: 'Incomplete dataset configuration',
        message: validationMessage,
      });
      return;
    }

    if (hasExistingDataset) {
      if (appendToExisting && canAppend) {
        await executeSubmit('append');
        return;
      }

      setConfirmationState({
        type: 'replace',
        title: 'Dataset already exists',
        message: 'Dataset already exists. What would you like to do?',
        confirmLabel: 'Replace Dataset',
        tone: 'primary',
      });
      return;
    }

    await executeSubmit('connect');
  };

  const handleResetRequest = () => {
    setConfirmationState({
      type: 'reset',
      title: 'Reset current dataset',
      message: 'Are you sure you want to reset the dataset?',
      confirmLabel: 'Reset Dataset',
      tone: 'danger',
    });
  };

  const handleConfirmAction = async () => {
    if (confirmationState.type === 'reset') {
      resetDataset();
      setAppendToExisting(false);
      setSubmitError('');
      closeConfirmation();

      pushToast({
        tone: 'success',
        title: 'Dataset reset successfully',
        message: 'The active dataset, schema, validation results, and derived views were cleared.',
      });
      return;
    }

    if (confirmationState.type === 'replace') {
      closeConfirmation();
      await executeSubmit('replace');
    }
  };

  return (
    <>
      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr] xl:gap-6">
        <section className="glass-panel animate-slide-up p-4 sm:p-6">
          <div className="flex flex-col gap-5 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="section-kicker">Dataset Management</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">
                Register a source and capture its schema metadata
              </h3>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                Select the source type, complete the connector details, and submit
                a structured payload to the backend. Uploads automatically use
                `FormData`; connected schemas are persisted in shared context.
              </p>
            </div>

            <div className="subtle-card w-full max-w-sm">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Active Source
              </p>
              <div className="mt-3">
                <StatusBadge tone={datasetStatus.tone}>
                  {datasetStatus.label}
                </StatusBadge>
              </div>
              <p className="mt-2 text-lg font-semibold text-white capitalize">
                {sourceType}
              </p>
              <p className="mt-2 text-sm text-slate-400">{sourceSummary}</p>
            </div>
          </div>

        <div className="mt-6 space-y-5 sm:space-y-6">
          <SourceSelector
            sourceType={sourceType}
            onChange={setSourceType}
            disabled={submitting}
          />

          {sourceType === 'file' && (
            <FileUpload
              value={fileState}
              onChange={setFileState}
              disabled={submitting}
              appendToExisting={appendToExisting}
              onAppendToggle={setAppendToExisting}
              showAppendOption={hasExistingDataset}
              canAppend={canAppend}
              currentDatasetName={selectedDataset?.name}
            />
          )}

          {sourceType === 'database' && (
            <DatabaseForm
              value={databaseState}
              onChange={setDatabaseState}
              disabled={submitting}
            />
          )}

          {sourceType === 'api' && (
            <ApiForm value={apiState} onChange={setApiState} disabled={submitting} />
          )}

          {sourceType === 'cloud' && (
            <CloudForm
              value={cloudState}
              onChange={setCloudState}
              disabled={submitting}
            />
          )}

          <div className="flex flex-col gap-4 border-t border-white/10 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="primary-button w-full sm:w-auto"
                title="Connect this dataset and continue to the rule builder."
              >
                {submitting ? (
                  <Loader label="Connecting source" compact />
                ) : (
                  submitButtonLabel
                )}
              </button>

              <button
                type="button"
                onClick={() => navigate('/rules')}
                disabled={!selectedDataset}
                className="secondary-button w-full sm:w-auto"
                title={
                  selectedDataset
                    ? 'Open the rule builder for the active dataset.'
                    : 'Upload a dataset to start validation.'
                }
              >
                Open Rule Builder
              </button>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link
                to="/dashboard"
                className="pill-button w-full whitespace-nowrap px-5 py-3 text-sm sm:w-auto"
              >
                View Dashboard
              </Link>
              {selectedDataset && (
                <div className="inline-flex items-center rounded-full border border-emerald-400/25 bg-emerald-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-300">
                  Connected
                </div>
              )}
            </div>
          </div>

          {submitError && (
            <div className="inline-banner inline-banner-error" role="alert">
              {submitError}
            </div>
          )}
        </div>
        </section>

        <section className="space-y-6">
          <div className="glass-panel animate-slide-up p-4 sm:p-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="section-kicker">Current Dataset</p>
                <div className="mt-3">
                  <StatusBadge tone={datasetStatus.tone}>
                    {datasetStatus.label}
                  </StatusBadge>
                </div>
                <h3 className="mt-3 text-2xl font-semibold text-white">
                  {selectedDataset?.name || 'No dataset loaded'}
                </h3>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
                  {selectedDataset
                    ? 'Manage the active dataset lifecycle here. You can reset the current context, replace it with a new source, or append new row-backed file data.'
                    : 'Connect a dataset to populate schema metadata, validation controls, and the observability dashboard.'}
                </p>
              </div>

              {selectedDataset && (
                <button
                  type="button"
                  onClick={handleResetRequest}
                  className="secondary-button danger-button"
                >
                  Reset Dataset
                </button>
              )}
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <div className="subtle-card">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Rows
                </p>
                <p className="mt-2 text-2xl font-bold text-white">{currentRowCount}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Current records available to validation and dashboard views.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Columns
                </p>
                <p className="mt-2 text-2xl font-bold text-white">{currentColumnCount}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Profiled schema fields tracked in global context.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Lifecycle Mode
                </p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {appendToExisting && canAppend
                    ? 'Append on next upload'
                    : hasExistingDataset
                      ? 'Replace on next upload'
                      : 'Fresh connection'}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  {appendToExisting && canAppend
                    ? 'The next file upload will merge rows and recompute the schema.'
                    : 'Uploading or connecting a new dataset will replace the current one after confirmation.'}
                </p>
              </div>
            </div>
          </div>

          <div className="glass-panel animate-slide-up p-4 sm:p-6">
            <p className="section-kicker">Schema Overview</p>
            <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h3 className="text-2xl font-semibold text-white">
                  Profiled columns and null distribution
                </h3>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
                  The backend response is normalized into shared context so rule
                  authoring and observability use the same schema metadata.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.05] px-4 py-3 text-left lg:text-right">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Active Dataset
                </p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {selectedDataset?.name || 'Awaiting connection'}
                </p>
              </div>
            </div>

            <div className="mt-6">
              <SchemaTable schema={schemaMetadata} />
            </div>
          </div>

          <div className="glass-panel p-4 sm:p-6">
            <p className="section-kicker">Workflow Guidance</p>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">1. Connect</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Submit a structured connector payload for files, databases, APIs,
                  or cloud warehouses.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">2. Validate</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Build column-level rules and inspect red-highlighted failed rows.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">3. Observe</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Monitor pass rates, anomalies, drift, and operational failures in
                  a single dashboard.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <ConfirmationModal
        isOpen={Boolean(confirmationState.type)}
        title={confirmationState.title}
        message={confirmationState.message}
        confirmLabel={confirmationState.confirmLabel}
        tone={confirmationState.tone}
        onClose={closeConfirmation}
        onConfirm={handleConfirmAction}
      />
    </>
  );
}
