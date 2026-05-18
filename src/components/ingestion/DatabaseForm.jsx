export default function DatabaseForm({ value, onChange, disabled }) {
  const updateField = (field, nextValue) => {
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="field-label">Database Type</p>
        <div className="inline-flex rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-sm font-semibold text-cyan-100">
          PostgreSQL
        </div>
      </div>

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
            placeholder="localhost"
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
            placeholder="dq_test"
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
            placeholder="dq_app"
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
            placeholder="Enter database password"
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
            placeholder="business_data.employees"
            className="input-shell"
          />
        </div>
      </div>
    </div>
  );
}
