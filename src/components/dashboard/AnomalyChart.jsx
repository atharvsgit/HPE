import {
  Chart as ChartJS,
  Legend,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';
import { Scatter } from 'react-chartjs-2';

ChartJS.register(LinearScale, PointElement, Tooltip, Legend);

export default function AnomalyChart({ anomalies = [] }) {
  const normalPoints = anomalies.filter((point) => point.status === 'normal');
  const anomalyPoints = anomalies.filter((point) => point.status === 'anomaly');

  const data = {
    datasets: [
      {
        label: 'Normal',
        data: normalPoints,
        pointBackgroundColor: 'rgba(56, 189, 248, 0.85)',
        pointBorderColor: 'rgba(125, 211, 252, 1)',
        pointRadius: 5,
      },
      {
        label: 'Anomalies',
        data: anomalyPoints,
        pointBackgroundColor: 'rgba(251, 113, 133, 0.9)',
        pointBorderColor: 'rgba(254, 205, 211, 1)',
        pointRadius: 7,
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
      tooltip: {
        callbacks: {
          label(context) {
            const point = context.raw;
            return `${point.label}: risk ${point.y} | null rate ${point.nullRate}%`;
          },
        },
      },
    },
    scales: {
      x: {
        title: {
          display: true,
          text: 'Column Index',
          color: '#94a3b8',
        },
        ticks: {
          color: '#94a3b8',
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.08)',
        },
      },
      y: {
        title: {
          display: true,
          text: 'Risk Score',
          color: '#94a3b8',
        },
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
      <p className="section-kicker">Anomaly Detection</p>
      <h3 className="mt-3 text-2xl font-semibold text-white">Behavior outliers</h3>
      <p className="mt-2 text-sm text-slate-400">
        Scatter plot of normal observations versus anomalous points in the same
        monitoring window.
      </p>

      <div className="chart-canvas-shell">
        <div className="h-[260px] sm:h-[280px] lg:h-[300px]">
          <Scatter data={data} options={options} />
        </div>
      </div>
    </div>
  );
}
