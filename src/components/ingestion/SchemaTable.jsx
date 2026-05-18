export default function SchemaTable({ schema }) {
  if (!schema?.length) {
    return (
      <div className="empty-state min-h-[320px]">
        <p className="text-lg font-semibold text-white">No schema available</p>
        <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
          Connect the company database to inspect table columns and data types
          before authoring rules.
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
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {schema.map((column) => (
              <tr key={column.columnName} className="data-table-row">
                <td className="data-table-cell font-semibold text-white">
                  {column.columnName}
                </td>
                <td className="data-table-cell">{column.dataType}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
