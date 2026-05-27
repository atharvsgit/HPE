import { useEffect, useState, useMemo } from 'react';
import Loader from '../components/common/Loader';
import StatusBadge from '../components/common/StatusBadge';
import { useDataset } from '../context/DatasetContext';

const TASKS_KEY = 'pulseqc:scheduled-tasks';
const FEED_KEY = 'pulseqc:orchestrator-feed';

const defaultTasks = [
  {
    id: 'task-1',
    name: 'Daily Customer Email Validation',
    dataset: 'mysql_crm.customers',
    status: 'active',
    frequency: 'daily',
    originalPrompt: 'Check that email is not null and matches regex standard every day',
    sql: 'SELECT * FROM "customers" WHERE "email" IS NULL OR "email" !~ \'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$\';',
    lastRun: new Date(Date.now() - 3600000 * 4).toISOString(), // 4 hrs ago
    nextRun: new Date(Date.now() + 3600000 * 20).toISOString(), // in 20 hrs
    rowsScanned: 15420,
    rowsReturned: 0,
    duration: '0.85s',
    emailStatus: 'Alerts active (recipient: data-ops@enterprise.com)',
    steps: [
      'Triggered by cron scheduler',
      'Dequeued from Redis queue: active_jobs',
      'Established database connection... OK',
      'Running SQL verification query... OK',
      'Checking zero violation conditions... OK',
      'Validation completed: 0 failed rows detected',
      'Notification dispatch: Not required (0 failures)'
    ]
  },
  {
    id: 'task-2',
    name: 'Weekly Financial Transaction Auditor',
    dataset: 'pg_production.transactions',
    status: 'active',
    frequency: 'weekly',
    originalPrompt: 'Validate that transaction_amount is between 0 and 5000000 every week',
    sql: 'SELECT * FROM "transactions" WHERE "transaction_amount" < 0 OR "transaction_amount" > 5000000;',
    lastRun: new Date(Date.now() - 3600000 * 24 * 3).toISOString(), // 3 days ago
    nextRun: new Date(Date.now() + 3600000 * 24 * 4).toISOString(), // in 4 days
    rowsScanned: 843210,
    rowsReturned: 42,
    duration: '3.12s',
    emailStatus: 'Alerts active (recipient: security-auditors@enterprise.com)',
    steps: [
      'Triggered by cron scheduler',
      'Dequeued from Redis queue: active_jobs',
      'Established database connection... OK',
      'Running SQL verification query... OK',
      'Checking zero violation conditions... Failed (42 rows returned)',
      'Validation completed: 42 anomalies detected',
      'Notification dispatch: Dispatched email alert to security-auditors@enterprise.com'
    ]
  },
  {
    id: 'task-3',
    name: 'Bi-Weekly Student Attendance Quality Check',
    dataset: 'mongo_logs.attendance_records',
    status: 'paused',
    frequency: 'every 2 weeks',
    originalPrompt: 'Check student attendance below 70 every 2 weeks',
    sql: 'SELECT * FROM "attendance_records" WHERE "attendance" < 70;',
    lastRun: new Date(Date.now() - 3600000 * 24 * 12).toISOString(), // 12 days ago
    nextRun: null,
    rowsScanned: 4500,
    rowsReturned: 18,
    duration: '0.45s',
    emailStatus: 'Alerts disabled (paused)',
    steps: [
      'Scheduler paused by administrator'
    ]
  }
];

const initialTimelineEvents = [
  { time: new Date(Date.now() - 60000 * 5).toLocaleTimeString(), text: 'Redis job queue connection: ONLINE' },
  { time: new Date(Date.now() - 60000 * 4).toLocaleTimeString(), text: 'Worker Node #1 registered: ID node-f8a9' },
  { time: new Date(Date.now() - 60000 * 3).toLocaleTimeString(), text: 'Weekly Financial Transaction Auditor completed: 42 anomalies flagged' },
  { time: new Date(Date.now() - 60000 * 2).toLocaleTimeString(), text: 'Dispatched alert to security-auditors@enterprise.com' },
  { time: new Date(Date.now() - 60000 * 1).toLocaleTimeString(), text: 'Scheduler task tick: Checking active intervals' },
];

export default function DashboardPage() {
  const { pushToast } = useDataset();
  const [tasks, setTasks] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [expandedTaskId, setExpandedTaskId] = useState(null);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editFreqValue, setEditFreqValue] = useState('');
  const [loading, setLoading] = useState(true);

  // Load scheduler state
  useEffect(() => {
    const storedTasks = localStorage.getItem(TASKS_KEY);
    const storedTimeline = localStorage.getItem(FEED_KEY);

    if (storedTasks) {
      setTasks(JSON.parse(storedTasks));
    } else {
      setTasks(defaultTasks);
      localStorage.setItem(TASKS_KEY, JSON.stringify(defaultTasks));
    }

    if (storedTimeline) {
      setTimeline(JSON.parse(storedTimeline));
    } else {
      setTimeline(initialTimelineEvents);
      localStorage.setItem(FEED_KEY, JSON.stringify(initialTimelineEvents));
    }

    setLoading(false);
  }, []);

  // Periodic simulated timeline updates (Real-time orchestration logs)
  useEffect(() => {
    if (loading) return;

    const phrases = [
      'Cron tick: Active database tables verified.',
      'Worker node heartbeats verified: HEALTHY.',
      'Redis queue active_jobs length: 0 pending.',
      'Database connection verified for pg_production: OK.',
      'Logs rotated for scheduler daemon.',
      'Simulated cron run completed in 0.25s.',
    ];

    const interval = setInterval(() => {
      const newEvent = {
        time: new Date().toLocaleTimeString(),
        text: phrases[Math.floor(Math.random() * phrases.length)],
      };
      setTimeline((prev) => {
        const next = [newEvent, ...prev.slice(0, 19)];
        localStorage.setItem(FEED_KEY, JSON.stringify(next));
        return next;
      });
    }, 15000);

    return () => clearInterval(interval);
  }, [loading]);

  const saveTasks = (updatedTasks) => {
    setTasks(updatedTasks);
    localStorage.setItem(TASKS_KEY, JSON.stringify(updatedTasks));
  };

  const handleToggleStatus = (id) => {
    const updated = tasks.map((task) => {
      if (task.id === id) {
        const nextStatus = task.status === 'active' ? 'paused' : 'active';
        return {
          ...task,
          status: nextStatus,
          nextRun: nextStatus === 'active' ? new Date(Date.now() + 3600000 * 12).toISOString() : null,
          emailStatus: nextStatus === 'active' ? 'Alerts active' : 'Alerts disabled (paused)'
        };
      }
      return task;
    });
    saveTasks(updated);
    pushToast({
      tone: 'success',
      title: 'Schedule Status Updated',
      message: 'The validation schedule status has been updated successfully.'
    });
  };

  const handleRerunTask = (id) => {
    const updated = tasks.map((task) => {
      if (task.id === id) {
        return {
          ...task,
          lastRun: new Date().toISOString(),
          rowsScanned: task.rowsScanned + Math.floor(Math.random() * 50),
          rowsReturned: Math.floor(Math.random() * 5) === 0 ? Math.floor(Math.random() * 10) : 0,
        };
      }
      return task;
    });
    saveTasks(updated);

    // Add entry to feed
    const targetTask = tasks.find(t => t.id === id);
    const logEvent = {
      time: new Date().toLocaleTimeString(),
      text: `Ad-hoc execution triggered for "${targetTask.name}"... Completed (0.42s).`
    };
    setTimeline(prev => [logEvent, ...prev]);

    pushToast({
      tone: 'success',
      title: 'Validation Executed',
      message: `The ad-hoc validation task run finished.`
    });
  };

  const handleDeleteTask = (id) => {
    const updated = tasks.filter((t) => t.id !== id);
    saveTasks(updated);
    pushToast({
      tone: 'success',
      title: 'Scheduled Task Deleted',
      message: 'The selected scheduled validation task was removed.'
    });
  };

  const handleStartEdit = (task) => {
    setEditingTaskId(task.id);
    setEditFreqValue(task.frequency);
  };

  const handleSaveEdit = (id) => {
    const updated = tasks.map((task) => {
      if (task.id === id) {
        return { ...task, frequency: editFreqValue };
      }
      return task;
    });
    saveTasks(updated);
    setEditingTaskId(null);
    pushToast({
      tone: 'success',
      title: 'Schedule Updated',
      message: `Task schedule interval was changed to: ${editFreqValue}`
    });
  };

  const formatDateTime = (value) => {
    if (!value) return 'N/A';
    return new Intl.DateTimeFormat('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  };

  const activeSchedules = useMemo(() => tasks.filter(t => t.status === 'active').length, [tasks]);

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Header section */}
      <div>
        <p className="section-kicker">Orchestration & Schedules</p>
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-white mt-1">Scheduled Validations</h2>
        <p className="text-sm text-slate-500 mt-2">
          Monitor recurring validations, active task frequencies, row results, and live pipeline activities.
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader label="Loading scheduled workflows..." />
        </div>
      ) : (
        <>
          {/* Scheduler Metrics Dashboard summary */}
          {tasks.length > 0 && (
            <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 p-4">
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Active schedules</span>
                <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">{activeSchedules} / {tasks.length}</p>
              </div>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 p-4">
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Anomalies caught</span>
                <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">
                  {tasks.reduce((acc, t) => acc + t.rowsReturned, 0)}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 p-4">
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Total Scanned rows</span>
                <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">
                  {new Intl.NumberFormat('en-US', { notation: 'compact' }).format(tasks.reduce((acc, t) => acc + t.rowsScanned, 0))}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 p-4">
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Redis queue status</span>
                <p className="text-2xl font-bold mt-1 text-emerald-500">Idle</p>
              </div>
            </div>
          )}

          {/* Active Tasks Feed */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Validation Scheduler Feed</h3>
              <span className="text-xs text-slate-400">{tasks.length} validation tasks registered</span>
            </div>

            {tasks.length === 0 ? (
              <div className="empty-state">
                <svg className="mx-auto h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-slate-900 dark:text-white font-medium mt-3">No active scheduled validations</p>
                <p className="text-slate-500 text-xs mt-1 max-w-sm mx-auto">
                  Describe a business query in the Rule Workspace and define a schedule (e.g. "every day") to populate this dashboard.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {tasks.map((task) => {
                  const isExpanded = expandedTaskId === task.id;
                  const isEditing = editingTaskId === task.id;

                  return (
                    <div
                      key={task.id}
                      className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900/30 overflow-hidden transition-all duration-200"
                    >
                      {/* Main Collapsible Item row */}
                      <div
                        onClick={() => !isEditing && setExpandedTaskId(isExpanded ? null : task.id)}
                        className={`flex flex-col md:flex-row md:items-center justify-between p-4 cursor-pointer gap-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-900/50 ${
                          isExpanded ? 'border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40' : ''
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3">
                            <span
                              className={`h-2.5 w-2.5 rounded-full ${
                                task.status === 'active'
                                  ? 'bg-emerald-500 animate-pulse'
                                  : 'bg-slate-400'
                              }`}
                            />
                            <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">{task.name}</h4>
                            <span className="text-slate-200 dark:text-slate-800 hidden md:block">|</span>
                            <span className="text-xs text-slate-500 truncate hidden md:block">{task.dataset}</span>
                          </div>
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-500">
                            <span className="flex items-center gap-1">
                              <span className="font-semibold text-slate-400 dark:text-slate-600">Interval:</span>
                              {task.frequency}
                            </span>
                            <span>•</span>
                            <span>
                              <span className="font-semibold text-slate-400 dark:text-slate-600">Scanned:</span> {task.rowsScanned.toLocaleString()}
                            </span>
                            <span>•</span>
                            <span className={task.rowsReturned > 0 ? 'text-rose-500 font-semibold' : ''}>
                              <span className="font-semibold text-slate-400 dark:text-slate-600">Failures:</span> {task.rowsReturned}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-4 text-xs">
                          <div className="text-right">
                            <span className="text-[10px] text-slate-400 block uppercase font-medium">Last Run</span>
                            <span className="text-slate-600 dark:text-slate-300 font-medium mt-0.5 block">{formatDateTime(task.lastRun)}</span>
                          </div>
                          <div className="text-right min-w-[100px]">
                            <span className="text-[10px] text-slate-400 block uppercase font-medium">Next Run</span>
                            <span className="text-slate-600 dark:text-slate-300 font-medium mt-0.5 block">
                              {task.status === 'active' ? formatDateTime(task.nextRun) : 'Paused'}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 max-md:mt-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleRerunTask(task.id)}
                              className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-700 dark:text-slate-300 transition-colors"
                              title="Rerun validation check immediately"
                            >
                              Run
                            </button>
                            <button
                              onClick={() => handleToggleStatus(task.id)}
                              className={`rounded px-2 py-1 font-semibold transition-colors ${
                                task.status === 'active'
                                  ? 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-500'
                                  : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500'
                              }`}
                            >
                              {task.status === 'active' ? 'Pause' : 'Resume'}
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Dropdown details content */}
                      {isExpanded && (
                        <div className="p-5 bg-white dark:bg-slate-900/10 space-y-5 text-sm">
                          <div className="grid gap-6 md:grid-cols-2">
                            {/* Query details */}
                            <div className="space-y-3">
                              <div>
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">Original User Request</span>
                                <p className="text-slate-700 dark:text-slate-300 mt-1 italic">"{task.originalPrompt}"</p>
                              </div>
                              <div>
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">Generated SQL Query</span>
                                <pre className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-600 dark:text-slate-400 overflow-x-auto mt-1 leading-relaxed">
                                  {task.sql}
                                </pre>
                              </div>
                            </div>

                            {/* Status Logs and info */}
                            <div className="space-y-4">
                              <div className="flex justify-between items-center">
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Execution Steps Log</span>
                                <StatusBadge tone={task.status === 'active' ? 'success' : 'pending'}>
                                  {task.status}
                                </StatusBadge>
                              </div>
                              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 p-3.5 space-y-2">
                                {task.steps.map((step, i) => (
                                  <div key={i} className="flex gap-2.5 text-xs text-slate-600 dark:text-slate-400">
                                    <span className="text-slate-300 dark:text-slate-700 select-none">{i + 1}.</span>
                                    <span>{step}</span>
                                  </div>
                                ))}
                              </div>

                              <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
                                <div>
                                  <span className="font-semibold text-slate-400 block">Execution duration</span>
                                  <span className="mt-0.5 block font-mono text-slate-700 dark:text-slate-300">{task.duration}</span>
                                </div>
                                <div>
                                  <span className="font-semibold text-slate-400 block">Email integration</span>
                                  <span className="mt-0.5 block text-slate-700 dark:text-slate-300">{task.emailStatus}</span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Detail Actions block */}
                          <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-800/80 pt-4 mt-2">
                            <div className="flex items-center gap-3">
                              {isEditing ? (
                                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                                  <input
                                    type="text"
                                    value={editFreqValue}
                                    onChange={(e) => setEditFreqValue(e.target.value)}
                                    placeholder="e.g. daily, weekly, every 3 weeks"
                                    className="input-shell py-1 px-3 text-xs w-48"
                                    title="Interval format"
                                  />
                                  <button
                                    onClick={() => handleSaveEdit(task.id)}
                                    className="primary-button text-xs py-1 px-3"
                                  >
                                    Save
                                  </button>
                                  <button
                                    onClick={() => setEditingTaskId(null)}
                                    className="secondary-button text-xs py-1 px-3"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              ) : (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleStartEdit(task);
                                  }}
                                  className="text-xs font-semibold text-sky-500 hover:text-sky-400 flex items-center gap-1"
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                                  </svg>
                                  Edit Schedule Frequency
                                </button>
                              )}
                            </div>

                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteTask(task.id);
                              }}
                              className="text-xs font-semibold text-rose-500 hover:text-rose-400 flex items-center gap-1"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                              Delete Task
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Orchestrator live timeline activities */}
          <div className="grid gap-6 md:grid-cols-3">
            <div className="md:col-span-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Live Orchestration Timeline</h3>
                <p className="text-xs text-slate-400 mt-1">Real-time daemon verification feeds and Redis queue actions.</p>
              </div>

              <div className="rounded-lg bg-slate-950 text-slate-300 dark:text-slate-400 p-4 font-mono text-xs h-[180px] overflow-y-auto space-y-2 leading-relaxed">
                {timeline.map((event, idx) => (
                  <div key={idx} className="flex gap-3">
                    <span className="text-slate-500 select-none">[{event.time}]</span>
                    <span className={event.text.includes('flagged') || event.text.includes('Failed') ? 'text-rose-400 font-medium' : event.text.includes('completed') ? 'text-emerald-400' : 'text-slate-300'}>
                      {event.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 flex flex-col justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Worker Status Panel</h3>
                <p className="text-xs text-slate-400 mt-1">Status of computational worker nodes and job queue.</p>
              </div>

              <div className="mt-4 space-y-3 flex-1 justify-center flex flex-col">
                <div className="flex items-center justify-between text-xs border-b border-slate-100 dark:border-slate-800 pb-2">
                  <span className="text-slate-400">Queue Daemon (Celery/Redis)</span>
                  <span className="font-semibold text-emerald-500">Connected</span>
                </div>
                <div className="flex items-center justify-between text-xs border-b border-slate-100 dark:border-slate-800 pb-2">
                  <span className="text-slate-400">Active Worker Nodes</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">2 Online</span>
                </div>
                <div className="flex items-center justify-between text-xs pb-1">
                  <span className="text-slate-400">SMTP Server (Notification)</span>
                  <span className="font-semibold text-emerald-500">Online</span>
                </div>
              </div>

              <div className="border-t border-slate-100 dark:border-slate-800 pt-3 flex items-center justify-between text-xs text-slate-400">
                <span>CPU Load: 0.12%</span>
                <span>RAM Load: 4.8%</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
