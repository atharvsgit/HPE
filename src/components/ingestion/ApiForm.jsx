export default function ApiForm({ value, onChange, disabled }) {
  const updateField = (field, nextValue) => {
    onChange({ ...value, [field]: nextValue });
  };

  const updateHeader = (index, field, nextValue) => {
    const nextHeaders = value.headers.map((header, currentIndex) =>
      currentIndex === index ? { ...header, [field]: nextValue } : header,
    );

    onChange({ ...value, headers: nextHeaders });
  };

  const addHeader = () => {
    onChange({
      ...value,
      headers: [...value.headers, { key: '', value: '' }],
    });
  };

  const removeHeader = (index) => {
    onChange({
      ...value,
      headers: value.headers.filter((_, currentIndex) => currentIndex !== index),
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="subtle-card">
          <label className="field-label" htmlFor="api-url">
            API URL
          </label>
          <input
            id="api-url"
            type="url"
            value={value.url}
            onChange={(event) => updateField('url', event.target.value)}
            disabled={disabled}
            placeholder="https://api.company.com/v1/orders"
            className="input-shell"
          />
        </div>

        <div className="subtle-card">
          <label className="field-label" htmlFor="api-method">
            Method
          </label>
          <select
            id="api-method"
            value={value.method}
            onChange={(event) => updateField('method', event.target.value)}
            disabled={disabled}
            className="input-shell min-w-[160px]"
          >
            {['GET', 'POST', 'PUT', 'PATCH'].map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="subtle-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="field-label mb-0">Headers</p>
            <p className="mt-2 text-sm text-slate-400">
              Capture outbound request headers as key-value pairs.
            </p>
          </div>
          <button
            type="button"
            onClick={addHeader}
            disabled={disabled}
            className="pill-button w-full sm:w-auto"
          >
            Add Header
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {value.headers.map((header, index) => (
            <div
              key={`${index}-${header.key}`}
              className="grid gap-3 sm:grid-cols-[0.8fr_1fr_auto]"
            >
              <input
                type="text"
                value={header.key}
                onChange={(event) =>
                  updateHeader(index, 'key', event.target.value)
                }
                disabled={disabled}
                placeholder="Authorization"
                className="input-shell"
              />
              <input
                type="text"
                value={header.value}
                onChange={(event) =>
                  updateHeader(index, 'value', event.target.value)
                }
                disabled={disabled}
                placeholder="Bearer token"
                className="input-shell"
              />
              <button
                type="button"
                onClick={() => removeHeader(index)}
                disabled={disabled || value.headers.length === 1}
                className="secondary-button danger-button w-full px-4 py-3 sm:w-auto"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
