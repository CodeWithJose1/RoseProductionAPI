import { useState } from 'react';
import { Eye, Map } from 'lucide-react';
import { farmsApi } from '../api/endpoints.js';
import { CrudPage } from '../components/CrudPage.jsx';
import { TextInput } from '../components/FormField.jsx';
import { Modal } from '../components/Modal.jsx';
import { ErrorState, LoadingState } from '../components/States.jsx';
import { useApi } from '../hooks/useApi.js';
import { formatNumber } from '../utils/format.js';
import {
  findClash, normalizeText, rules, runRules, textKey, withDuplicate,
} from '../utils/validation.js';

const schema = {
  name: [rules.required('Farm name'), rules.maxLength('Farm name', 100)],
  location: [rules.required('Location'), rules.maxLength('Location', 150)],
};

// A farm is identified by its name and location; case and spacing ignored.
export function validateFarm(values, { rows, editing } = {}) {
  const sameKey = (name, location) => textKey(name) === textKey(values.name)
    && textKey(location) === textKey(values.location);
  const clash = findClash({
    rows,
    idKey: 'farm_id',
    editing,
    unchanged: editing && sameKey(editing.name, editing.location),
    sameAs: (row) => sameKey(row.name, row.location),
  });
  return withDuplicate(runRules(values, schema), 'name', clash,
    'A farm with this name already exists at this location.');
}

function FarmDetail({ farmId, onClose }) {
  const { data, loading, error, reload } = useApi(() => farmsApi.get(farmId), [farmId]);
  return (
    <Modal open title={data ? data.name : 'Farm details'} onClose={onClose} size="lg">
      {loading && !data && <LoadingState />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <div className="detail">
          <dl className="detail-grid">
            <div><dt>Farm ID</dt><dd>{data.farm_id}</dd></div>
            <div><dt>Location</dt><dd>{data.location}</dd></div>
            <div><dt>Lots</dt><dd>{data.lot_count}</dd></div>
            <div><dt>Total area</dt><dd>{formatNumber(data.total_area)}</dd></div>
          </dl>
          <h3>Associated lots</h3>
          {data.lots.length === 0 ? (
            <p className="muted">This farm has no lots yet.</p>
          ) : (
            <table className="data-table compact">
              <thead><tr><th>ID</th><th>Lot</th><th className="align-right">Area</th></tr></thead>
              <tbody>
                {data.lots.map((lot) => (
                  <tr key={lot.lot_id}>
                    <td>{lot.lot_id}</td><td>{lot.name}</td><td className="align-right">{formatNumber(lot.area)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </Modal>
  );
}

export default function Farms() {
  const [detailId, setDetailId] = useState(null);

  const columns = [
    { key: 'farm_id', header: 'ID', align: 'right' },
    { key: 'name', header: 'Farm' },
    { key: 'location', header: 'Location' },
    { key: 'lot_count', header: 'Lots', align: 'right' },
    {
      key: 'details',
      header: 'Details',
      sortable: false,
      render: (row) => (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDetailId(row.farm_id)}>
          <Eye size={14} aria-hidden="true" /> View lots
        </button>
      ),
    },
  ];

  return (
    <>
      <CrudPage
        api={farmsApi}
        title="Farms"
        singular="Farm"
        icon={Map}
        description="Floricultural farms and their cultivation lots."
        columns={columns}
        searchText={(row) => `${row.name} ${row.location}`}
        emptyForm={{ name: '', location: '' }}
        toForm={(row) => ({ name: row.name, location: row.location })}
        toPayload={(values) => ({ name: normalizeText(values.name), location: normalizeText(values.location) })}
        validate={validateFarm}
        describe={(row) => row.name}
        renderFields={({ values, set, errors }) => (
          <>
            <TextInput label="Farm name" required value={values.name} onChange={(v) => set('name', v)} error={errors.name} maxLength={100} />
            <TextInput label="Location" required value={values.location} onChange={(v) => set('location', v)} error={errors.location} maxLength={150} />
          </>
        )}
      />
      {detailId && <FarmDetail farmId={detailId} onClose={() => setDetailId(null)} />}
    </>
  );
}
