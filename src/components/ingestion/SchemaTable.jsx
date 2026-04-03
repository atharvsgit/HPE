export default function SchemaTable({ schema }) {
  if (!schema?.length) {
    return (
      <div className="empty-state min-h-[320px]">
        <p className="text-lg font-semibold text-white">No schema available</p>
        <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
          Connect a source to inspect column names, data types, and null
          distribution before authoring rules.
        </p>
      </div>
    );
  }

  return (
    <div className="table-shell">
      <div className="table-scroll max-h-[420px]">
        <table className="data-table">
          <thead className="data-table-head">
            <tr>
              <th className="data-table-header-cell">Column Name</th>
              <th className="data-table-header-cell">Data Type</th>
              <th className="data-table-header-cell">Null Count</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {schema.map((column) => (
              <tr key={column.columnName} className="data-table-row">
                <td className="data-table-cell font-semibold text-white">
                  {column.columnName}
                </td>
                <td className="data-table-cell">{column.dataType}</td>
                <td className="data-table-cell">
                  <span
                    className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
                      column.nullCount
                        ? 'border border-amber-400/25 bg-amber-400/10 text-amber-200'
                        : 'border border-emerald-400/25 bg-emerald-400/10 text-emerald-200'
                    }`}
                  >
                    {column.nullCount}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
