import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

export default function DriftChart({ drift }) {
  const data = {
    labels: drift.labels,
    datasets: [
      {
        label: 'Reference',
        data: drift.reference,
        borderColor: 'rgba(148, 163, 184, 0.95)',
        backgroundColor: 'rgba(148, 163, 184, 0.18)',
        tension: 0.35,
        pointRadius: 3,
      },
      {
        label: 'Current',
        data: drift.current,
        borderColor: 'rgba(56, 189, 248, 0.95)',
        backgroundColor: 'rgba(56, 189, 248, 0.2)',
        tension: 0.35,
        pointRadius: 4,
        fill: false,
      },
    ],
  };

  const options = {
    maintainAspectRatio: false,
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
    scales: {
      x: {
        ticks: {
          color: '#94a3b8',
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.08)',
        },
      },
      y: {
        ticks: {
          color: '#94a3b8',
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.08)',
        },
      },
    },
  };

  return (
    <div>
      <p className="section-kicker">Drift Monitoring</p>
      <h3 className="mt-3 text-2xl font-semibold text-white">
        Reference vs current baseline
      </h3>
      <p className="mt-2 text-sm text-slate-400">
        Column-by-column completeness against the connected dataset baseline.
      </p>

      <div className="chart-canvas-shell">
        <div className="h-[260px] sm:h-[290px] lg:h-[300px]">
          <Line data={data} options={options} />
        </div>
      </div>
    </div>
  );
}
