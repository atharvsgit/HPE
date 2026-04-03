import { useDeferredValue, useMemo, useState } from 'react';

const severityClasses = {
  critical: 'border-rose-500/25 bg-rose-500/10 text-rose-100',
  high: 'border-orange-400/25 bg-orange-400/10 text-orange-100',
  medium: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
};

export default function FailureTable({ failures = [] }) {
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const filteredFailures = useMemo(() => {
    const normalizedSearch = deferredSearchTerm.trim().toLowerCase();

    if (!normalizedSearch) {
      return failures;
    }

    return failures.filter((failure) =>
      [failure.rowId, failure.column, failure.message, failure.severity]
        .filter(Boolean)
        .some((field) =>
          String(field).toLowerCase().includes(normalizedSearch),
        ),
    );
  }, [deferredSearchTerm, failures]);

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="section-kicker">Failure Table</p>
          <h3 className="mt-3 text-2xl font-semibold text-white">
            Row-level error inventory
          </h3>
          <p className="mt-2 text-sm text-slate-400">
            Search the latest failures to isolate incidents by row, column, or
            severity.
          </p>
        </div>
        <input
          type="text"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="Search failures"
          className="input-shell w-full sm:max-w-xs"
        />
      </div>

      {filteredFailures.length ? (
        <div className="table-shell mt-6">
          <div className="table-scroll max-h-[300px]">
            <table className="data-table">
              <thead className="data-table-head">
                <tr>
                  <th className="data-table-header-cell">Row ID</th>
                  <th className="data-table-header-cell">Column</th>
                  <th className="data-table-header-cell">Message</th>
                  <th className="data-table-header-cell">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredFailures.map((failure) => (
                  <tr key={failure.rowId} className="data-table-row">
                    <td className="data-table-cell font-semibold text-white">
                      {failure.rowId}
                    </td>
                    <td className="data-table-cell">{failure.column}</td>
                    <td className="data-table-cell">
                      {failure.message}
                    </td>
                    <td className="data-table-cell">
                      <span
                        className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                          severityClasses[failure.severity] || severityClasses.medium
                        }`}
                      >
                        {failure.severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="empty-state mt-6 min-h-[220px]">
          <p className="text-lg font-semibold text-white">No data available</p>
          <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
            Failure rows will appear once the dashboard receives report data or
            when the search term matches an existing incident.
          </p>
        </div>
      )}
    </div>
  );
}
