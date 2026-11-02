import { useSearchParams } from 'react-router-dom';
import type { FormEvent } from 'react';

export function useListFilters(keys: string[]) {
  const [params, setParams] = useSearchParams();
  const parsed = Number(params.get('offset') || 0);
  const offset = Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
  const limit = [20, 50, 100].includes(Number(params.get('limit')))
    ? Number(params.get('limit'))
    : 20;
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  for (const key of keys) if (params.get(key)) query.set(key, params.get(key)!);
  const update = (changes: Record<string, string>, pageChange = false) => {
    const next = new URLSearchParams(params);
    if (!pageChange) next.delete('offset');
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next);
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = Object.fromEntries(
      new FormData(event.currentTarget),
    ) as Record<string, string>;
    for (const [key, value] of Object.entries(values))
      values[key] = value.trim();
    if (values.country) values.country = values.country.toUpperCase();
    if (values.occurred_from) values.occurred_from += 'T00:00:00Z';
    if (values.occurred_to) values.occurred_to += 'T23:59:59.999999Z';
    update(values);
  };
  return {
    params,
    query: query.toString(),
    offset,
    limit,
    update,
    submit,
    reset: () => setParams({}),
  };
}

export function Pagination({
  total,
  offset,
  limit,
  update,
}: {
  total: number;
  offset: number;
  limit: number;
  update: (changes: Record<string, string>, pageChange?: boolean) => void;
}) {
  return (
    <nav className="pagination" aria-label="Results pages">
      <label>
        Rows per page{' '}
        <select
          value={limit}
          onChange={(event) => update({ limit: event.target.value })}
        >
          {[20, 50, 100].map((size) => (
            <option key={size}>{size}</option>
          ))}
        </select>
      </label>
      <span role="status">
        {total === 0
          ? '0 results'
          : `${Math.min(offset + 1, total)}–${Math.min(offset + limit, total)} of ${total}`}
      </span>
      <button
        disabled={offset === 0}
        onClick={() =>
          update({ offset: String(Math.max(0, offset - limit)) }, true)
        }
      >
        Previous
      </button>
      <button
        disabled={offset + limit >= total}
        onClick={() => update({ offset: String(offset + limit) }, true)}
      >
        Next
      </button>
    </nav>
  );
}
