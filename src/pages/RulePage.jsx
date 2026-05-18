import { Link } from 'react-router-dom';
import StatusBadge from '../components/common/StatusBadge';
import RuleBuilder from '../components/ruleBuilder/RuleBuilder';
import { useDataset } from '../context/DatasetContext';

export default function RulePage() {
  const { selectedDataset, schemaMetadata, validationResults } = useDataset();
  const datasetStatus = validationResults
    ? {
        label: 'Rule Completed',
        tone: 'success',
      }
    : selectedDataset
      ? {
          label: 'Database Connected',
          tone: 'success',
        }
      : {
          label: 'No Database',
          tone: 'pending',
        };

  return (
    <div className="space-y-6">
      <section className="glass-panel animate-slide-up p-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-kicker">Rule Builder</p>
            <div className="mt-3">
              <StatusBadge tone={datasetStatus.tone}>
                {datasetStatus.label}
              </StatusBadge>
            </div>
            <h3 className="mt-3 text-2xl font-semibold text-white">
              Enter SQL rules and review aggregate outcomes
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
              Use SQL or the guided builder. Each run checks the active database
              table through the backend daemon and stores the aggregate outcome.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="subtle-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Database
              </p>
              <p className="mt-2 text-sm font-semibold text-white">
                {selectedDataset?.name || 'No database connected'}
              </p>
            </div>
            <div className="subtle-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Columns
              </p>
              <p className="mt-2 text-sm font-semibold text-white">
                {schemaMetadata.length || 0} table fields
              </p>
            </div>
          </div>
        </div>
      </section>

      {schemaMetadata.length ? (
        <RuleBuilder />
      ) : (
        <section className="glass-panel p-6">
          <div className="empty-state">
            <p className="text-lg font-semibold text-white">
              Connect the database to start validation
            </p>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
              Connect the company database first so the rule builder can load
              table columns and run backend SQL aggregate checks.
            </p>
            <Link
              to="/"
              className="primary-button mt-6"
            >
              Go to Database Connection
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
