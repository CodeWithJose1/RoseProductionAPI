import { useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { useToast } from '../context/ToastContext.jsx';
import { useApi } from '../hooks/useApi.js';
import { PageHeader, RowActions } from './Common.jsx';
import { DataTable } from './DataTable.jsx';
import { ConfirmDialog } from './Modal.jsx';
import { ResourceFormModal } from './ResourceFormModal.jsx';
import { ErrorState, LoadingState } from './States.jsx';

/**
 * Complete list/create/edit/delete screen for one REST resource.
 */
export function CrudPage({
  api, title, singular, description, icon, columns, searchText, params,
  emptyForm, toForm, toPayload, validate, renderFields, describe, filters,
  beforeTable, onChanged, extraActions, formSize, initialSort, formDescription,
  refreshToken = 0, filtersActive = false,
}) {
  const toast = useToast();
  const { data, loading, error, reload } = useApi(
    () => api.list(params),
    [JSON.stringify(params || {}), refreshToken],
  );
  const [editing, setEditing] = useState(null); // { mode, row }
  const [deleting, setDeleting] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const deleteInFlight = useRef(false);

  const refresh = async () => {
    await reload();
    onChanged?.();
  };

  const submit = async (values) => {
    const body = toPayload(values);
    if (editing.mode === 'create') {
      await api.create(body);
      toast.success(`${singular} created successfully`);
    } else {
      await api.update(editing.row[api.idKey], body);
      toast.success(`${singular} updated successfully`);
    }
    setEditing(null);
    await refresh();
  };

  const confirmDelete = async () => {
    if (deleteInFlight.current) return; // ignore a second click while deleting
    deleteInFlight.current = true;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.remove(deleting[api.idKey]);
      toast.success(`${singular} deleted successfully`);
      setDeleting(null);
      await refresh();
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      deleteInFlight.current = false;
      setDeleteBusy(false);
    }
  };

  const rows = data || [];

  return (
    <section className="page">
      <PageHeader
        title={title}
        description={description}
        icon={icon}
        actions={(
          <>
            {extraActions}
            <button type="button" className="btn btn-primary" onClick={() => setEditing({ mode: 'create', row: null })}>
              <Plus size={16} aria-hidden="true" /> New {singular.toLowerCase()}
            </button>
          </>
        )}
      />
      {beforeTable}
      {filters}
      {loading && !data ? (
        <LoadingState />
      ) : error && !data ? (
        <ErrorState error={error} onRetry={reload} />
      ) : (
        <DataTable
          label={title.toLowerCase()}
          columns={columns}
          rows={rows}
          rowKey={(row) => row[api.idKey]}
          searchText={searchText}
          initialSort={initialSort}
          emptyTitle={filtersActive ? 'No matching records' : `No ${title.toLowerCase()} yet`}
          emptyMessage={filtersActive
            ? 'No records match the selected filters. Change or clear the filters.'
            : `Use “New ${singular.toLowerCase()}” to add the first record.`}
          actions={(row) => (
            <RowActions
              label={describe(row)}
              onEdit={() => setEditing({ mode: 'edit', row })}
              onDelete={() => { setDeleteError(null); setDeleting(row); }}
            />
          )}
        />
      )}

      <ResourceFormModal
        open={Boolean(editing)}
        size={formSize}
        title={editing?.mode === 'edit' ? `Edit ${singular.toLowerCase()}` : `New ${singular.toLowerCase()}`}
        description={formDescription}
        initialValues={editing?.mode === 'edit' ? toForm(editing.row) : emptyForm}
        validate={validate
          ? (values) => validate(values, { rows, editing: editing?.mode === 'edit' ? editing.row : null })
          : undefined}
        onSubmit={submit}
        onClose={() => setEditing(null)}
        renderFields={renderFields}
        submitLabel={editing?.mode === 'edit' ? 'Save changes' : `Create ${singular.toLowerCase()}`}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title={`Delete ${singular.toLowerCase()}?`}
        message={deleting ? `“${describe(deleting)}” will be permanently deleted from the database.` : ''}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
        busy={deleteBusy}
        error={deleteError}
      />
    </section>
  );
}
