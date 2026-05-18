import {
  ArcElement,
  Chart as ChartJS,
  Legend,
  Tooltip,
} from 'chart.js';
import { Doughnut } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

export default function HealthChart({ qualityScore }) {
  const data = {
    labels: ['Passed', 'Failed'],
    datasets: [
      {
        data: [qualityScore.passed, qualityScore.failed],
        backgroundColor: ['rgba(52, 211, 153, 0.88)', 'rgba(251, 113, 133, 0.85)'],
        borderWidth: 0,
      },
    ],
  };

  const options = {
    maintainAspectRatio: false,
    cutout: '78%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#cbd5e1',
          usePointStyle: true,
          boxWidth: 10,
        },
      },
    },
  };

  return (
    <div>
      <p className="section-kicker">Passed vs Failed</p>
      <div className="mt-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-2xl font-semibold text-white">Health Score</h3>
          <p className="mt-2 text-sm text-slate-400">
            Current pass/fail distribution with overall quality score.
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-400/25 bg-emerald-400/10 px-4 py-2 text-sm font-semibold text-emerald-200">
          {qualityScore.status}
        </div>
      </div>

      <div className="chart-canvas-shell">
        <div className="relative h-[260px] sm:h-[280px] lg:h-[300px]">
        <Doughnut data={data} options={options} />
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
            Score
          </p>
          <p className="mt-2 text-4xl font-semibold text-white">
            {qualityScore.score}%
          </p>
          <p className="mt-2 text-center text-sm text-emerald-300">
            {qualityScore.trendLabel}
          </p>
          <p className="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">
            Completeness {qualityScore.completeness}%
          </p>
        </div>
        </div>
      </div>
    </div>
  );
}
