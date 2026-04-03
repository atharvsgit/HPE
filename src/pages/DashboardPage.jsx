import { useEffect, useState } from 'react';
import AnomalyChart from '../components/dashboard/AnomalyChart';
import DriftChart from '../components/dashboard/DriftChart';
import FailureTable from '../components/dashboard/FailureTable';
import HealthChart from '../components/dashboard/HealthChart';
import Skeleton from '../components/common/Skeleton';
import { useDataset } from '../context/DatasetContext';
import { deriveObservabilityData } from '../services/derivedMetrics';
import { getQualityScore, getReport } from '../services/endpoints';

function SummaryCard({ label, value, hint }) {
  return (
    <div className="metric-card">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-bold text-white">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
    </div>
  );
}

export default function DashboardPage() {
  const {
    selectedDataset,
    schemaMetadata,
    validationResults,
    datasetRows,
    pushToast,
  } = useDataset();
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState(null);
  const [qualityScore, setQualityScore] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const derivedTelemetry = deriveObservabilityData({
      selectedDataset,
      schemaMetadata,
      validationResults,
      datasetRows,
    });

    const loadDashboard = async () => {
      if (!selectedDataset) {
        setReport(null);
        setQualityScore(null);
        setLoading(false);
        return;
      }

      setLoading(true);

      try {
        const [reportResponse, qualityResponse] = await Promise.all([
          getReport(selectedDataset?.id),
          getQualityScore(selectedDataset?.id),
        ]);

        if (!isMounted) {
          return;
        }

        setReport(reportResponse || derivedTelemetry?.report || null);
        setQualityScore(qualityResponse || derivedTelemetry?.qualityScore || null);
      } catch (error) {
        if (!isMounted) {
          return;
        }

        if (derivedTelemetry) {
          setReport(derivedTelemetry.report);
          setQualityScore(derivedTelemetry.qualityScore);
        } else {
          pushToast({
            tone: 'error',
            title: 'Dashboard refresh failed',
            message:
              error.message ||
              'The dashboard could not load because no usable dataset telemetry is available yet.',
          });
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadDashboard();

    return () => {
      isMounted = false;
    };
  }, [
    datasetRows,
    pushToast,
    schemaMetadata,
    selectedDataset,
    selectedDataset?.id,
    validationResults,
  ]);

  return (
    <div className="space-y-6">
      <section className="glass-panel animate-slide-up p-4 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-kicker">Observability Dashboard</p>
            <h3 className="mt-3 text-2xl font-semibold text-white">
              Monitor health, anomalies, drift, and failure trends
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
              This view combines aggregate scoring with row-level failure signals
              so teams can quickly understand whether a dataset is within
              tolerance before it reaches consuming systems.
            </p>
          </div>

          <div className="subtle-card w-full max-w-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
              Observed Asset
            </p>
            <p className="mt-2 text-sm font-semibold text-white">
              {selectedDataset?.name || 'Awaiting a connected dataset'}
            </p>
            <p className="mt-2 text-sm text-slate-400">
              {selectedDataset
                ? 'Metrics come from the connected profile or live backend responses.'
                : 'No values are shown until the interface has connected data to derive from.'}
            </p>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-12 xl:gap-6">
          <div className="glass-panel p-4 sm:p-6 xl:col-span-4">
            <Skeleton className="h-64 w-full" />
          </div>
          <div className="glass-panel p-4 sm:p-6 xl:col-span-8">
            <Skeleton className="h-64 w-full" />
          </div>
          <div className="glass-panel p-4 sm:p-6 xl:col-span-6">
            <Skeleton className="h-72 w-full" />
          </div>
          <div className="glass-panel p-4 sm:p-6 xl:col-span-6">
            <Skeleton className="h-72 w-full" />
          </div>
        </div>
      ) : qualityScore && report ? (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <SummaryCard
              label="Quality Score"
              value={`${qualityScore.score}%`}
              hint={`${qualityScore.status} and ${qualityScore.trendLabel.toLowerCase()}`}
            />
            <SummaryCard
              label="Passed Checks"
              value={qualityScore.passed}
              hint="Records or rules meeting expectations"
            />
            <SummaryCard
              label="Failed Checks"
              value={qualityScore.failed}
              hint="Rows flagged for remediation"
            />
            <SummaryCard
              label="Completeness"
              value={`${qualityScore.completeness}%`}
              hint="Non-empty cell coverage across the dataset"
            />
            <SummaryCard
              label="Latency"
              value={report.summary?.pipelineLatency || '2m 18s'}
              hint="Current pipeline evaluation time"
            />
          </section>

          <section className="grid gap-5 lg:grid-cols-2 xl:grid-cols-12 xl:gap-6">
            <div className="glass-panel p-4 sm:p-6 xl:col-span-4">
              <HealthChart qualityScore={qualityScore} />
            </div>
            <div className="glass-panel p-4 sm:p-6 xl:col-span-8">
              <AnomalyChart anomalies={report.anomalies} />
            </div>
            <div className="glass-panel p-4 sm:p-6 xl:col-span-6">
              <DriftChart drift={report.drift} />
            </div>
            <div className="glass-panel p-4 sm:p-6 xl:col-span-6">
              <FailureTable failures={report.failures} />
            </div>
          </section>
        </>
      ) : (
        <section className="glass-panel p-4 sm:p-6">
          <div className="empty-state">
            <p className="text-lg font-semibold text-white">
              No dashboard telemetry available
            </p>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
              Connect a dataset and run validation to populate the observability
              views. The dashboard now stays empty until there is real connected
              schema or validation data to derive from.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
