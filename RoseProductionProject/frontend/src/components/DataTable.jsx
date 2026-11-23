import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { EmptyState } from './States.jsx';

function compare(a, b) {
  if (a === b) return 0;
  if (a === null || a === undefined || a === '') return 1;
  if (b === null || b === undefined || b === '') return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

/**
 * Searchable, sortable, paginated table.
 * columns: [{ key, header, render?(row), sortValue?(row), align?, sortable? }]
 */
export function DataTable({
  columns, rows, rowKey, searchText, actions, pageSize = 10, label,
  emptyTitle = 'No records found', emptyMessage, toolbar, initialSort,
}) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState(initialSort || null);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle || !searchText) return rows;
    return rows.filter((row) => searchText(row).toLowerCase().includes(needle));
  }, [rows, query, searchText]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const column = columns.find((col) => col.key === sort.key);
    if (!column) return filtered;
    const value = column.sortValue || ((row) => row[column.key]);
    const copy = [...filtered].sort((a, b) => compare(value(a), value(b)));
    return sort.dir === 'desc' ? copy.reverse() : copy;
  }, [filtered, sort, columns]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  useEffect(() => setPage(1), [query]);

  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  const toggleSort = (key) => {
    setSort((current) => {
      if (!current || current.key !== key) return { key, dir: 'asc' };
      if (current.dir === 'asc') return { key, dir: 'desc' };
      return null;
    });
  };

  return (
    <div className="table-card">
      <div className="table-toolbar">
        {searchText && (
          <label className="search-box">
            <Search size={16} aria-hidden="true" />
            <span className="sr-only">Search {label}</span>
            <input
              type="search"
              placeholder={`Search ${label || 'records'}…`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        )}
        <div className="toolbar-extra">{toolbar}</div>
        <span className="muted result-count" aria-live="polite">
          {sorted.length} {sorted.length === 1 ? 'record' : 'records'}
        </span>
      </div>

      {sorted.length === 0 ? (
        <EmptyState
          title={query ? 'No matching records' : emptyTitle}
          message={query ? `Nothing matches "${query}".` : emptyMessage}
        />
      ) : (
        <div className="table-scroll">
          <table className="data-table" aria-label={label}>
            <thead>
              <tr>
                {columns.map((column) => {
                  const sortable = column.sortable !== false;
                  const active = sort?.key === column.key;
                  const Icon = !active ? ArrowUpDown : sort.dir === 'asc' ? ArrowUp : ArrowDown;
                  return (
                    <th
                      key={column.key}
                      className={column.align === 'right' ? 'align-right' : undefined}
                      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    >
                      {sortable ? (
                        <button type="button" className="sort-button" onClick={() => toggleSort(column.key)}>
                          {column.header}
                          <Icon size={14} aria-hidden="true" className={active ? '' : 'faint'} />
                        </button>
                      ) : column.header}
                    </th>
                  );
                })}
                {actions && <th className="align-right">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={rowKey(row)}>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      data-label={column.header}
                      className={[column.align === 'right' ? 'align-right' : '', column.wrap ? 'wrap' : ''].join(' ').trim() || undefined}
                    >
                      {column.render ? column.render(row) : row[column.key]}
                    </td>
                  ))}
                  {actions && <td className="align-right actions-cell" data-label="Actions">{actions(row)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pageCount > 1 && (
        <nav className="pagination" aria-label="Pagination">
          <button type="button" className="btn btn-ghost" onClick={() => setPage((p) => p - 1)} disabled={page === 1}>
            <ChevronLeft size={16} aria-hidden="true" /> Previous
          </button>
          <span>Page {page} of {pageCount}</span>
          <button type="button" className="btn btn-ghost" onClick={() => setPage((p) => p + 1)} disabled={page === pageCount}>
            Next <ChevronRight size={16} aria-hidden="true" />
          </button>
        </nav>
      )}
    </div>
  );
}
