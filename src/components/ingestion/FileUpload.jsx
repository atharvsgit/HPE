const acceptedFormats = [
  { value: 'csv', label: 'CSV' },
  { value: 'parquet', label: 'Parquet' },
];

export default function FileUpload({
  value,
  onChange,
  disabled,
  appendToExisting = false,
  onAppendToggle,
  showAppendOption = false,
  canAppend = false,
  currentDatasetName = '',
}) {
  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    const inferredFormat = file?.name?.toLowerCase().endsWith('.parquet')
      ? 'parquet'
      : 'csv';

    onChange({
      ...value,
      file,
      format: file ? inferredFormat : value.format,
    });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
      <div className="subtle-card">
        <label className="field-label">Dataset File</label>
        <label className="dropzone-shell">
          <input
            type="file"
            accept=".csv,.parquet"
            onChange={handleFileChange}
            disabled={disabled}
            className="hidden"
          />
          <span className="dropzone-badge">
            Upload File
          </span>
          <span className="mt-4 text-base font-semibold text-white">
            {value.file ? value.file.name : 'Drop or browse for a dataset'}
          </span>
          <span className="mt-2 text-sm leading-6 text-slate-400">
            Accepts CSV and Parquet files. Uploads are submitted as multipart
            `FormData`.
          </span>
        </label>
      </div>

      <div className="subtle-card">
        <label className="field-label" htmlFor="file-format">
          File Type
        </label>
        <select
          id="file-format"
          value={value.format}
          onChange={(event) =>
            onChange({ ...value, format: event.target.value })
          }
          disabled={disabled}
          className="input-shell"
        >
          {acceptedFormats.map((format) => (
            <option key={format.value} value={format.value}>
              {format.label}
            </option>
          ))}
        </select>

        <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-4 shadow-inner shadow-black/10">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
            File Readiness
          </p>
          <p className="mt-2 text-sm font-semibold text-white">
            {value.file ? 'Ready for upload' : 'Awaiting file selection'}
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Selected format: {value.format.toUpperCase()}
          </p>
        </div>

        {showAppendOption && (
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4 shadow-inner shadow-black/10">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={appendToExisting}
                onChange={(event) => onAppendToggle?.(event.target.checked)}
                disabled={disabled || !canAppend}
                className="mt-1 h-4 w-4 rounded border-white/20 bg-slate-950/80 text-cyan-400 focus:ring-2 focus:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <span>
                <span className="block text-sm font-semibold text-white">
                  Append to existing dataset
                </span>
                <span className="mt-1 block text-sm leading-6 text-slate-400">
                  {canAppend
                    ? `Merge the uploaded rows into ${currentDatasetName || 'the current dataset'} and refresh the schema metadata.`
                    : 'Append is available for row-backed datasets loaded in this session.'}
                </span>
              </span>
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
