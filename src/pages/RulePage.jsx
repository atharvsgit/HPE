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
          label: 'Dataset Loaded',
          tone: 'success',
        }
      : {
          label: 'No Dataset',
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
              Enter rules and get matching rows
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
              Use natural language, SQL, or the schema-aware builder. Each run
              checks the active dataset and returns the rows that match your rule.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="subtle-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Dataset
              </p>
              <p className="mt-2 text-sm font-semibold text-white">
                {selectedDataset?.name || 'No dataset connected'}
              </p>
            </div>
            <div className="subtle-card">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                Columns
              </p>
              <p className="mt-2 text-sm font-semibold text-white">
                {schemaMetadata.length || 0} profiled fields
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
              Connect a dataset to start validation
            </p>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
              Connect a dataset on the dataset workspace first so the rule builder
              can load schema-aware columns, available rule types, and row-level
              validation results.
            </p>
            <Link
              to="/"
              className="primary-button mt-6"
            >
              Go to Dataset Workspace
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
