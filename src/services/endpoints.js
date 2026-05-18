import api from './api';

const buildHeadersObject = (headers = []) =>
  headers.reduce((accumulator, entry) => {
    if (entry?.key && entry?.value) {
      accumulator[entry.key] = entry.value;
    }

    return accumulator;
  }, {});

export async function connectDatabase(payload) {
  const { data } = await api.post('/connect-database', payload);
  return data;
}

export { buildHeadersObject };
