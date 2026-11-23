import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataTable } from '../components/DataTable.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import { ResourceFormModal } from '../components/ResourceFormModal.jsx';
import { TextInput } from '../components/FormField.jsx';
import { EmptyState, ErrorState, LoadingState } from '../components/States.jsx';
import { ApiError } from '../api/client.js';
import { rules, runRules } from '../utils/validation.js';

const rows = Array.from({ length: 23 }, (_, i) => ({ id: i + 1, name: `Rose ${String(i + 1).padStart(2, '0')}`, qty: (i * 37) % 100 }));
const columns = [
  { key: 'id', header: 'ID' },
  { key: 'name', header: 'Name' },
  { key: 'qty', header: 'Quantity', align: 'right' },
];

describe('DataTable', () => {
  it('renders rows with pagination (10 per page)', async () => {
    const user = userEvent.setup();
    render(<DataTable label="roses" columns={columns} rows={rows} rowKey={(r) => r.id} searchText={(r) => r.name} />);
    expect(screen.getByText('23 records')).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(11); // header + 10
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    expect(screen.getByText('Rose 11')).toBeInTheDocument();
  });

  it('filters with the search box', async () => {
    const user = userEvent.setup();
    render(<DataTable label="roses" columns={columns} rows={rows} rowKey={(r) => r.id} searchText={(r) => r.name} />);
    await user.type(screen.getByPlaceholderText('Search roses…'), 'Rose 07');
    expect(screen.getByText('1 record')).toBeInTheDocument();
    expect(screen.getByText('Rose 07')).toBeInTheDocument();
  });

  it('shows an empty state when the search has no match', async () => {
    const user = userEvent.setup();
    render(<DataTable label="roses" columns={columns} rows={rows} rowKey={(r) => r.id} searchText={(r) => r.name} />);
    await user.type(screen.getByPlaceholderText('Search roses…'), 'tulip');
    expect(screen.getByText('No matching records')).toBeInTheDocument();
  });

  it('sorts ascending then descending when a header is clicked', async () => {
    const user = userEvent.setup();
    render(<DataTable label="roses" columns={columns} rows={rows.slice(0, 5)} rowKey={(r) => r.id} />);
    const header = screen.getByRole('button', { name: /quantity/i });
    await user.click(header);
    let cells = screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[2].textContent);
    expect(cells).toEqual([...cells].sort((a, b) => Number(a) - Number(b)));
    await user.click(header);
    cells = screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[2].textContent);
    expect(cells).toEqual([...cells].sort((a, b) => Number(b) - Number(a)));
  });

  it('renders the configured empty state for no rows', () => {
    render(<DataTable label="roses" columns={columns} rows={[]} rowKey={(r) => r.id} emptyTitle="No roses yet" />);
    expect(screen.getByText('No roses yet')).toBeInTheDocument();
  });
});

describe('state components', () => {
  it('render loading, empty and error states', async () => {
    const retry = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <LoadingState label="Loading farms…" />
        <EmptyState title="Nothing here" />
        <ErrorState error={{ message: 'Database down' }} onRetry={retry} />
      </>,
    );
    expect(screen.getByText('Loading farms…')).toBeInTheDocument();
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    expect(screen.getByText('Database down')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(retry).toHaveBeenCalled();
  });
});

describe('ConfirmDialog', () => {
  it('confirms or cancels', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmDialog open title="Delete farm?" message="Farm X will be deleted" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByRole('dialog', { name: 'Delete farm?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('shows the server error returned by a failed delete', () => {
    render(<ConfirmDialog open message="x" error="Cannot delete this farm: it is still referenced by 3 lot(s)." onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('3 lot(s)');
  });
});

function NameForm({ onSubmit }) {
  return (
    <ResourceFormModal
      open
      title="New variety"
      initialValues={{ name: '', color: '' }}
      validate={(v) => runRules(v, { name: [rules.required('Name')], color: [rules.required('Color')] })}
      onSubmit={onSubmit}
      onClose={() => {}}
      renderFields={({ values, set, errors }) => (
        <>
          <TextInput label="Name" value={values.name} onChange={(x) => set('name', x)} error={errors.name} />
          <TextInput label="Color" value={values.color} onChange={(x) => set('color', x)} error={errors.color} />
        </>
      )}
    />
  );
}

describe('ResourceFormModal', () => {
  it('blocks submit and shows client-side validation errors', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<NameForm onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('Name is required')).toBeInTheDocument();
    expect(screen.getByText('Color is required')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits valid values', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue();
    render(<NameForm onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText('Name'), 'Freedom');
    await user.type(screen.getByLabelText('Color'), 'Red');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSubmit).toHaveBeenCalledWith({ name: 'Freedom', color: 'Red' });
  });

  it('maps API field errors onto the form', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(400, 'Validation failed', { details: { color: 'must be at most 50 characters' } }));
    render(<NameForm onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText('Name'), 'Freedom');
    await user.type(screen.getByLabelText('Color'), 'Red');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Validation failed')).toBeInTheDocument();
    expect(screen.getAllByText('must be at most 50 characters').length).toBeGreaterThan(0);
  });
});
