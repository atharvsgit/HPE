const databaseTypes = [
  { id: 'parquet', label: 'Parquet' },
  { id: 'postgresql', label: 'PostgreSQL' },
  { id: 'mysql', label: 'MySQL' },
  { id: 'mongodb', label: 'MongoDB' },
];

export default function DatabaseForm({ value, onChange, disabled }) {
  const updateField = (field, nextValue) => {
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="field-label">Database Type</p>
        <div className="grid gap-3 sm:grid-cols-4">
          {databaseTypes.map((databaseType) => {
            const isActive = value.subType === databaseType.id;

            return (
              <button
                key={databaseType.id}
                type="button"
                onClick={() => updateField('subType', databaseType.id)}
                disabled={disabled}
                className={`pill-button ${
                  isActive ? 'pill-button-active' : ''
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                {databaseType.label}
              </button>
            );
          })}
        </div>
      </div>

      {value.subType === 'mongodb' ? (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="subtle-card md:col-span-2">
            <label className="field-label" htmlFor="db-uri">
              MongoDB URI
            </label>
            <input
              id="db-uri"
              type="text"
              value={value.uri}
              onChange={(event) => updateField('uri', event.target.value)}
              disabled={disabled}
              placeholder="mongodb+srv://username:password@cluster.mongodb.net"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="mongo-database">
              Database
            </label>
            <input
              id="mongo-database"
              type="text"
              value={value.database}
              onChange={(event) => updateField('database', event.target.value)}
              disabled={disabled}
              placeholder="analytics"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="mongo-collection">
              Collection
            </label>
            <input
              id="mongo-collection"
              type="text"
              value={value.collection}
              onChange={(event) => updateField('collection', event.target.value)}
              disabled={disabled}
              placeholder="orders"
              className="input-shell"
            />
          </div>
        </div>
      ) : value.subType === 'parquet' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="subtle-card">
            <label className="field-label">Dataset File</label>
            <label className="dropzone-shell">
              <input
                type="file"
                accept=".parquet"
                onChange={(e) => updateField('file', e.target.files?.[0] || null)}
                disabled={disabled}
                className="hidden"
              />
              <span className="dropzone-badge">Upload File</span>
              <span className="mt-4 text-base font-semibold text-white">
                {value.file ? value.file.name : 'Drop or browse for a .parquet file'}
              </span>
              <span className="mt-2 text-sm leading-6 text-slate-400">
                Accepts Parquet files. Uploads are submitted as multipart FormData.
              </span>
            </label>
          </div>
          <div className="subtle-card">
            <div className="mt-2 rounded-2xl border border-white/10 bg-white/[0.03] p-4 shadow-inner shadow-black/10">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">File Readiness</p>
              <p className="mt-2 text-sm font-semibold text-white">
                {value.file ? 'Ready for upload' : 'Awaiting file selection'}
              </p>
              <p className="mt-2 text-sm text-slate-400">Selected format: PARQUET</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <div className="subtle-card">
            <label className="field-label" htmlFor="db-host">
              Host
            </label>
            <input
              id="db-host"
              type="text"
              value={value.host}
              onChange={(event) => updateField('host', event.target.value)}
              disabled={disabled}
              placeholder="warehouse.company.internal"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="db-port">
              Port
            </label>
            <input
              id="db-port"
              type="text"
              value={value.port}
              onChange={(event) => updateField('port', event.target.value)}
              disabled={disabled}
              placeholder="5432"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="db-name">
              Database
            </label>
            <input
              id="db-name"
              type="text"
              value={value.database}
              onChange={(event) => updateField('database', event.target.value)}
              disabled={disabled}
              placeholder="analytics"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="db-user">
              Username
            </label>
            <input
              id="db-user"
              type="text"
              value={value.username}
              onChange={(event) => updateField('username', event.target.value)}
              disabled={disabled}
              placeholder="quality_admin"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="db-password">
              Password
            </label>
            <input
              id="db-password"
              type="password"
              value={value.password}
              onChange={(event) => updateField('password', event.target.value)}
              disabled={disabled}
              placeholder="Enter secure credential"
              className="input-shell"
            />
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="db-table">
              Table
            </label>
            <input
              id="db-table"
              type="text"
              value={value.table}
              onChange={(event) => updateField('table', event.target.value)}
              disabled={disabled}
              placeholder="orders_snapshot"
              className="input-shell"
            />
          </div>
        </div>
      )}
    </div>
  );
}
