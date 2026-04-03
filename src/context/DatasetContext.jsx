import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { appendProfileData } from '../services/localDataset';

const DatasetContext = createContext(null);

const STORAGE_KEYS = {
  dataset: 'pulseqc:selected-dataset',
  schema: 'pulseqc:schema-metadata',
};

const readStoredValue = (key, fallbackValue) => {
  if (typeof window === 'undefined') {
    return fallbackValue;
  }

  try {
    const stored = window.localStorage.getItem(key);
    return stored ? JSON.parse(stored) : fallbackValue;
  } catch {
    return fallbackValue;
  }
};

const createToastId = () =>
  `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

export function DatasetProvider({ children }) {
  const [selectedDatasetState, setSelectedDatasetState] = useState(() =>
    readStoredValue(STORAGE_KEYS.dataset, null),
  );
  const [schemaMetadataState, setSchemaMetadataState] = useState(() =>
    readStoredValue(STORAGE_KEYS.schema, []),
  );
  const [datasetRowsState, setDatasetRowsState] = useState([]);
  const [validationResultsState, setValidationResultsState] = useState(null);
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      STORAGE_KEYS.dataset,
      JSON.stringify(selectedDatasetState),
    );
  }, [selectedDatasetState]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      STORAGE_KEYS.schema,
      JSON.stringify(schemaMetadataState),
    );
  }, [schemaMetadataState]);

  const setSelectedDataset = useCallback((dataset) => {
    startTransition(() => {
      setSelectedDatasetState(dataset ?? null);
    });
  }, []);

  const setSchemaMetadata = useCallback((schema) => {
    startTransition(() => {
      setSchemaMetadataState(Array.isArray(schema) ? schema : []);
    });
  }, []);

  const setValidationResults = useCallback((results) => {
    startTransition(() => {
      setValidationResultsState(results ?? null);
    });
  }, []);

  const setDatasetRows = useCallback((rows) => {
    startTransition(() => {
      setDatasetRowsState(Array.isArray(rows) ? rows : []);
    });
  }, []);

  const replaceDataset = useCallback(
    (nextData) => {
      const normalizedData = nextData || {};

      setSelectedDataset(normalizedData.dataset ?? null);
      setSchemaMetadata(normalizedData.schema ?? []);
      setDatasetRows(normalizedData.rows ?? []);
      setValidationResults(null);

      return normalizedData;
    },
    [setDatasetRows, setSchemaMetadata, setSelectedDataset, setValidationResults],
  );

  const appendDataset = useCallback(
    (nextData) => {
      const appendedData = appendProfileData({
        currentDataset: selectedDatasetState,
        currentRows: datasetRowsState,
        incomingData: nextData,
      });

      if (!appendedData) {
        return null;
      }

      replaceDataset(appendedData);
      return appendedData;
    },
    [datasetRowsState, replaceDataset, selectedDatasetState],
  );

  const dismissToast = useCallback((id) => {
    setToasts((currentToasts) =>
      currentToasts.filter((toast) => toast.id !== id),
    );
  }, []);

  const pushToast = useCallback(
    ({ title, message, tone = 'info', duration = 4500 }) => {
      const id = createToastId();

      setToasts((currentToasts) => [
        ...currentToasts,
        { id, title, message, tone },
      ]);

      window.setTimeout(() => {
        dismissToast(id);
      }, duration);
    },
    [dismissToast],
  );

  const resetDataset = useCallback(() => {
    setSelectedDataset(null);
    setSchemaMetadata([]);
    setDatasetRows([]);
    setValidationResults(null);
  }, [
    setDatasetRows,
    setSchemaMetadata,
    setSelectedDataset,
    setValidationResults,
  ]);

  const value = useMemo(
    () => ({
      selectedDataset: selectedDatasetState,
      schemaMetadata: schemaMetadataState,
      datasetRows: datasetRowsState,
      validationResults: validationResultsState,
      toasts,
      appendDataset,
      replaceDataset,
      resetDataset,
      setSelectedDataset,
      setSchemaMetadata,
      setDatasetRows,
      setValidationResults,
      pushToast,
      dismissToast,
    }),
    [
      appendDataset,
      dismissToast,
      datasetRowsState,
      pushToast,
      replaceDataset,
      resetDataset,
      schemaMetadataState,
      selectedDatasetState,
      setDatasetRows,
      setSchemaMetadata,
      setSelectedDataset,
      setValidationResults,
      toasts,
      validationResultsState,
    ],
  );

  return (
    <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
  );
}

export function useDataset() {
  const context = useContext(DatasetContext);

  if (!context) {
    throw new Error('useDataset must be used within a DatasetProvider.');
  }

  return context;
}
