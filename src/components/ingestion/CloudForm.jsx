const cloudTypes = [
  { id: 'snowflake', label: 'Snowflake' },
  { id: 'bigquery', label: 'BigQuery' },
];

export default function CloudForm({ value, onChange, disabled }) {
  const updateField = (field, nextValue) => {
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="field-label">Cloud Connector</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {cloudTypes.map((cloudType) => {
            const isActive = value.subType === cloudType.id;

            return (
              <button
                key={cloudType.id}
                type="button"
                onClick={() => updateField('subType', cloudType.id)}
                disabled={disabled}
                className={`pill-button ${
                  isActive ? 'pill-button-active' : ''
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                {cloudType.label}
              </button>
            );
          })}
        </div>
      </div>

      {value.subType === 'snowflake' ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-account">
              Account
            </label>
            <input
              id="snowflake-account"
              type="text"
              value={value.account}
              onChange={(event) => updateField('account', event.target.value)}
              disabled={disabled}
              placeholder="company-prod"
              className="input-shell"
            />
          </div>
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-warehouse">
              Warehouse
            </label>
            <input
              id="snowflake-warehouse"
              type="text"
              value={value.warehouse}
              onChange={(event) => updateField('warehouse', event.target.value)}
              disabled={disabled}
              placeholder="DQ_WH"
              className="input-shell"
            />
          </div>
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-database">
              Database
            </label>
            <input
              id="snowflake-database"
              type="text"
              value={value.database}
              onChange={(event) => updateField('database', event.target.value)}
              disabled={disabled}
              placeholder="RAW"
              className="input-shell"
            />
          </div>
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-schema">
              Schema
            </label>
            <input
              id="snowflake-schema"
              type="text"
              value={value.schema}
              onChange={(event) => updateField('schema', event.target.value)}
              disabled={disabled}
              placeholder="PUBLIC"
              className="input-shell"
            />
          </div>
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-user">
              Username
            </label>
            <input
              id="snowflake-user"
              type="text"
              value={value.username}
              onChange={(event) => updateField('username', event.target.value)}
              disabled={disabled}
              placeholder="quality_analyst"
              className="input-shell"
            />
          </div>
          <div className="subtle-card">
            <label className="field-label" htmlFor="snowflake-password">
              Password
            </label>
            <input
              id="snowflake-password"
              type="password"
              value={value.password}
              onChange={(event) => updateField('password', event.target.value)}
              disabled={disabled}
              placeholder="Enter secure credential"
              className="input-shell"
            />
          </div>
        </div>
      ) : (
        <div className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="subtle-card">
              <label className="field-label" htmlFor="bigquery-project">
                Project
              </label>
              <input
                id="bigquery-project"
                type="text"
                value={value.project}
                onChange={(event) => updateField('project', event.target.value)}
                disabled={disabled}
                placeholder="acme-quality"
                className="input-shell"
              />
            </div>
            <div className="subtle-card">
              <label className="field-label" htmlFor="bigquery-dataset">
                Dataset
              </label>
              <input
                id="bigquery-dataset"
                type="text"
                value={value.dataset}
                onChange={(event) => updateField('dataset', event.target.value)}
                disabled={disabled}
                placeholder="sales"
                className="input-shell"
              />
            </div>
            <div className="subtle-card">
              <label className="field-label" htmlFor="bigquery-table">
                Table
              </label>
              <input
                id="bigquery-table"
                type="text"
                value={value.table}
                onChange={(event) => updateField('table', event.target.value)}
                disabled={disabled}
                placeholder="daily_orders"
                className="input-shell"
              />
            </div>
          </div>

          <div className="subtle-card">
            <label className="field-label" htmlFor="bigquery-credentials">
              Credentials JSON
            </label>
            <textarea
              id="bigquery-credentials"
              rows="8"
              value={value.credentials}
              onChange={(event) => updateField('credentials', event.target.value)}
              disabled={disabled}
              className="input-shell resize-none"
              placeholder='{"type":"service_account"}'
            />
          </div>
        </div>
      )}
    </div>
  );
}
