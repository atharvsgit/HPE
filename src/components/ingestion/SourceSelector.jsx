const sourceOptions = [
  {
    id: 'file',
    label: 'File',
    description: 'CSV or Parquet upload',
  },
  {
    id: 'database',
    label: 'Database',
    description: 'PostgreSQL, MySQL, MongoDB',
  },
  {
    id: 'api',
    label: 'API',
    description: 'REST endpoint ingestion',
  },
  {
    id: 'cloud',
    label: 'Cloud',
    description: 'Snowflake or BigQuery',
  },
];

export default function SourceSelector({ sourceType, onChange, disabled }) {
  return (
    <div>
      <p className="field-label">Source Type</p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {sourceOptions.map((option) => {
          const isActive = sourceType === option.id;

          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onChange(option.id)}
              disabled={disabled}
              className={`selection-card ${
                isActive ? 'selection-card-active' : ''
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              <div className="flex items-center justify-between">
                <span className="text-base font-semibold text-white">
                  {option.label}
                </span>
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    isActive ? 'bg-cyan-300' : 'bg-slate-600'
                  }`}
                />
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-400">{option.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
