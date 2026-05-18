const sourceOptions = [
  {
    id: 'database',
    label: 'Database Source',
    description: 'PostgreSQL, MySQL, or MongoDB',
  },
  {
    id: 'api',
    label: 'API Source',
    description: 'REST endpoint contract',
  },
  {
    id: 'cloud',
    label: 'Cloud Warehouse',
    description: 'Snowflake or BigQuery',
  },
];

export default function SourceSelector({ sourceType, onChange, disabled }) {
  return (
    <div>
      <p className="field-label">Source Type</p>
      <div className="grid gap-3 md:grid-cols-3">
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
