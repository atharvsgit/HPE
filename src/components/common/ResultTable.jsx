import { useMemo, useState } from 'react';

const DEFAULT_PAGE_SIZE = 10;
const HIDDEN_KEYS = new Set(['severity', '__rowId']);

const formatHeader = (key = '') =>
  String(key)
    .replace(/^rowId$/i, 'row_id')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatCellValue = (value) => {
  if (value === null || value === undefined || value === '') {
    return 'null';
  }

  if (typeof value === 'object') {
    return JSON.stringify(value);
  }

  return String(value);
};

const getRowKeys = (rows = []) => {
  const keys = [];
  const seenKeys = new Set();

  rows.forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (!HIDDEN_KEYS.has(key) && !seenKeys.has(key)) {
        seenKeys.add(key);
        keys.push(key);
      }
    });
  });

  return keys;
};

export default function ResultTable({
  rows = [],
  title = 'Returned Rows',
  description = 'Search and inspect the rows returned by the rule.',
  emptyTitle = 'No rows returned',
  emptyMessage = 'This rule ran successfully, but the result set is empty.',
  pageSize = DEFAULT_PAGE_SIZE,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const normalizedRows = useMemo(
    () =>
      rows.map((row) =>
        row && typeof row === 'object' && !Array.isArray(row)
          ? row
          : { value: row },
      ),
    [rows],
  );

  const columns = useMemo(() => getRowKeys(normalizedRows), [normalizedRows]);
  const filteredRows = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    if (!normalizedSearch) {
      return normalizedRows;
    }

    return normalizedRows.filter((row) =>
      Object.entries(row || {})
        .filter(([key]) => !HIDDEN_KEYS.has(key))
        .some(([, value]) =>
          formatCellValue(value).toLowerCase().includes(normalizedSearch),
        ),
    );
  }, [normalizedRows, searchTerm]);

  const totalPages = Math.max(Math.ceil(filteredRows.length / pageSize), 1);
  const safePage = Math.min(page, totalPages);
  const visibleRows = useMemo(
    () =>
      filteredRows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [filteredRows, pageSize, safePage],
  );

  const handleSearch = (event) => {
    setSearchTerm(event.target.value);
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="section-kicker">{title}</p>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            {description}
          </p>
        </div>
        <input
          type="text"
          value={searchTerm}
          onChange={handleSearch}
          placeholder="Search returned rows"
          className="input-shell lg:max-w-sm"
        />
      </div>

      {!normalizedRows.length ? (
        <div className="empty-state min-h-[220px]">
          <p className="text-lg font-semibold text-white">{emptyTitle}</p>
          <p className="mt-3 max-w-lg text-sm leading-6 text-slate-400">
            {emptyMessage}
          </p>
        </div>
      ) : (
        <>
          <div className="table-shell">
            <div className="table-scroll max-h-[560px]">
              <table className="data-table">
                <thead className="data-table-head">
                  <tr>
                    {columns.map((column) => (
                      <th key={column} className="data-table-header-cell">
                        {formatHeader(column)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {visibleRows.map((row, rowIndex) => (
                    <tr
                      key={row.id || row.rowId || `${safePage}-${rowIndex}`}
                      className="data-table-row"
                    >
                      {columns.map((column) => (
                        <td key={column} className="data-table-cell">
                          {formatCellValue(row?.[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex flex-col gap-3 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Showing {visibleRows.length} of {filteredRows.length} returned rows
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((currentPage) => Math.max(currentPage - 1, 1))}
                disabled={safePage === 1}
                className="secondary-button px-4 py-2 disabled:opacity-50"
              >
                Previous
              </button>
              <span className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-2 text-slate-200">
                {safePage} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() =>
                  setPage((currentPage) => Math.min(currentPage + 1, totalPages))
                }
                disabled={safePage === totalPages}
                className="secondary-button px-4 py-2 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
