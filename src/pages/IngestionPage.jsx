import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import ConfirmationModal from '../components/common/ConfirmationModal';
import Loader from '../components/common/Loader';
import StatusBadge from '../components/common/StatusBadge';
import DatabaseForm from '../components/ingestion/DatabaseForm';
import SchemaTable from '../components/ingestion/SchemaTable';
import { useDataset } from '../context/DatasetContext';
import { connectDatabase } from '../services/endpoints';

const initialDatabaseState = {
  subType: 'postgresql',
  host: 'postgres',
  port: '5432',
  database: 'dq_test',
  username: 'dq_app',
  password: 'dq_app_password',
  table: 'business_data.employees',
};

const isBlank = (value) => String(value ?? '').trim() === '';

export default function IngestionPage() {
  const navigate = useNavigate();
  const {
    replaceDataset,
    resetDataset,
    selectedDataset,
    schemaMetadata,
    validationResults,
    pushToast,
  } = useDataset();

  const [databaseState, setDatabaseState] = useState(initialDatabaseState);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [confirmationState, setConfirmationState] = useState({ type: null });

  const hasConnection = Boolean(selectedDataset);
  const currentRowCount = selectedDataset?.records || 0;
  const currentColumnCount = schemaMetadata.length || 0;
  const connectionStatus = validationResults
    ? { label: 'Rule Completed', tone: 'success' }
    : selectedDataset
      ? { label: 'Database Connected', tone: 'success' }
      : { label: 'No Database', tone: 'pending' };

  const buildConnectionPayload = () => ({
    source_type: 'database',
    sub_type: 'postgresql',
    config: {
      host: databaseState.host,
      port: databaseState.port,
      database: databaseState.database,
      username: databaseState.username,
      password: databaseState.password,
      table: databaseState.table,
    },
  });

  const validateConnectionInputs = () => {
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
      return 'Complete host, port, database, username, password, and table before connecting.';
    }

    return '';
  };

  const closeConfirmation = () => {
    setConfirmationState({ type: null });
  };

  const executeSubmit = async (mode = 'connect') => {
    setSubmitError('');
    setSubmitting(true);

    try {
      const validationMessage = validateConnectionInputs();

      if (validationMessage) {
        throw new Error(validationMessage);
      }

      const response = await connectDatabase(buildConnectionPayload());

      replaceDataset(response);
      pushToast({
        tone: 'success',
        title: mode === 'replace' ? 'Database connection replaced' : 'Database connected',
        message:
          response.message ||
          `${response.dataset?.name || databaseState.table} is ready for rule validation.`,
      });

      navigate('/rules');
    } catch (error) {
      setSubmitError(
        error.message ||
          'The database could not be connected. Check the required inputs and try again.',
      );
      pushToast({
        tone: 'error',
        title: 'Connection failed',
        message:
          error.message ||
          'The database could not be connected. Check the payload and try again.',
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
        title: 'Incomplete database configuration',
        message: validationMessage,
      });
      return;
    }

    if (hasConnection) {
      setConfirmationState({
        type: 'replace',
        title: 'Replace database connection',
        message: 'A database is already connected. Replace it with this connection?',
        confirmLabel: 'Replace Connection',
        tone: 'primary',
      });
      return;
    }

    await executeSubmit('connect');
  };

  const handleResetRequest = () => {
    setConfirmationState({
      type: 'reset',
      title: 'Reset database connection',
      message: 'Reset the active database context and rule result view?',
      confirmLabel: 'Reset Connection',
      tone: 'danger',
    });
  };

  const handleConfirmAction = async () => {
    if (confirmationState.type === 'reset') {
      resetDataset();
      setSubmitError('');
      closeConfirmation();

      pushToast({
        tone: 'success',
        title: 'Database context reset',
        message: 'The active database, schema metadata, and current rule result view were cleared.',
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
              <p className="section-kicker">Database Connection</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">
                Connect the company database used for rule validation
              </h3>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                The frontend is scoped to database-backed quality rules. The
                company data is treated as trusted, so this screen only captures
                the database connection and target table context.
              </p>
            </div>

            <div className="subtle-card w-full max-w-sm">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Active Database
              </p>
              <div className="mt-3">
                <StatusBadge tone={connectionStatus.tone}>
                  {connectionStatus.label}
                </StatusBadge>
              </div>
              <p className="mt-2 text-lg font-semibold text-white">
                {selectedDataset?.name || databaseState.table || 'Not connected'}
              </p>
              <p className="mt-2 text-sm text-slate-400">
                PostgreSQL database connection for saved and ad hoc SQL rules.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-5 sm:space-y-6">
            <DatabaseForm
              value={databaseState}
              onChange={setDatabaseState}
              disabled={submitting}
            />

            <div className="inline-banner inline-banner-info">
              For the local Docker setup, keep these defaults and click Connect
              Database: host postgres, database dq_test, table
              business_data.employees.
            </div>

            <div className="flex flex-col gap-4 border-t border-white/10 pt-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={submitting}
                  className="primary-button w-full sm:w-auto"
                  title="Connect this database and continue to the rule builder."
                >
                  {submitting ? (
                    <Loader label="Connecting database" compact />
                  ) : hasConnection ? (
                    'Replace Database'
                  ) : (
                    'Connect Database'
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => navigate('/rules')}
                  disabled={!selectedDataset}
                  className="secondary-button w-full sm:w-auto"
                  title={
                    selectedDataset
                      ? 'Open the rule builder for the active database.'
                      : 'Connect a database to start validation.'
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
                <p className="section-kicker">Current Database</p>
                <div className="mt-3">
                  <StatusBadge tone={connectionStatus.tone}>
                    {connectionStatus.label}
                  </StatusBadge>
                </div>
                <h3 className="mt-3 text-2xl font-semibold text-white">
                  {selectedDataset?.name || 'No database connected'}
                </h3>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
                  {selectedDataset
                    ? 'Run SQL-based data quality rules against the active database table.'
                    : 'Connect the company database to unlock rule authoring, execution history, and scheduler visibility.'}
                </p>
              </div>

              {selectedDataset && (
                <button
                  type="button"
                  onClick={handleResetRequest}
                  className="secondary-button danger-button"
                >
                  Reset Connection
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
                  Row count reported by the database connection response.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Columns
                </p>
                <p className="mt-2 text-2xl font-bold text-white">{currentColumnCount}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Column metadata available to the rule builder.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Validation Mode
                </p>
                <p className="mt-2 text-lg font-semibold text-white">
                  SQL aggregate rules
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Rules execute through the backend daemon and persist aggregate outcomes.
                </p>
              </div>
            </div>
          </div>

          <div className="glass-panel animate-slide-up p-4 sm:p-6">
            <p className="section-kicker">Database Schema</p>
            <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h3 className="text-2xl font-semibold text-white">
                  Columns available for rule authoring
                </h3>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
                  The rule builder uses this metadata to help compose SQL aggregate checks.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.05] px-4 py-3 text-left lg:text-right">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  Active Table
                </p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {selectedDataset?.name || databaseState.table || 'Awaiting connection'}
                </p>
              </div>
            </div>

            <div className="mt-6">
              <SchemaTable schema={schemaMetadata} />
            </div>
          </div>

          <div className="glass-panel p-4 sm:p-6">
            <p className="section-kicker">Workflow</p>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">1. Connect</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Register the company database and target table context.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">2. Validate</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Run ad hoc or saved SQL aggregate rules through the backend daemon.
                </p>
              </div>
              <div className="subtle-card">
                <p className="text-sm font-semibold text-white">3. Review</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Inspect saved rules, scheduler status, and persisted execution results.
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
