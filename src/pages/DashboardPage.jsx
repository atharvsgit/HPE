import { useEffect, useState, useMemo } from 'react';
import Loader from '../components/common/Loader';
import StatusBadge from '../components/common/StatusBadge';
import { useDataset } from '../context/DatasetContext';

const TASKS_KEY = 'pulseqc:scheduled-tasks';
const FEED_KEY = 'pulseqc:orchestrator-feed';
const CONNECTIONS_KEY = 'pulseqc:db-connections';

const defaultTasks = [
  {
    id: 'task-1',
    name: 'Daily Customers Email Validation',
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
    emailStatus: 'Notification Sent: Active (recipient: data-ops@enterprise.com)',
    steps: [
      'Validation Processing: Triggered by scheduled rule trigger.',
      'Queue Event: Dequeued from validation job queue.',
      'Task Step: Established connection with mysql_crm... OK',
      'Task Step: Running business rule verification query... OK',
      'Validation Processing: Checking validation conditions... OK',
      'Validation Processing: Completed (0 returned rows).',
      'Notification Sent: Bypassed (0 failures).'
    ]
  },
  {
    id: 'task-2',
    name: 'Weekly Financial Transaction Validation',
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
    emailStatus: 'Notification Sent: Active (recipient: security-auditors@enterprise.com)',
    steps: [
      'Validation Processing: Triggered by scheduled rule trigger.',
      'Queue Event: Dequeued from validation job queue.',
      'Task Step: Established connection with pg_production... OK',
      'Task Step: Running business rule verification query... OK',
      'Validation Processing: Checking validation conditions... Failed (42 returned rows).',
      'Validation Processing: Completed (42 anomalies caught).',
      'Notification Sent: Sent report digest to security-auditors@enterprise.com'
    ]
  },
  {
    id: 'task-3',
    name: 'Bi-Weekly Student Attendance Validation',
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
    emailStatus: 'Notification Sent: Inactive (paused)',
    steps: [
      'Validation Processing: Validation schedule paused by administrator.'
    ]
  }
];

const initialTimelineEvents = [
  { time: new Date(Date.now() - 60000 * 5).toLocaleTimeString(), text: 'Queue Event: Job broker connected (ONLINE)' },
  { time: new Date(Date.now() - 60000 * 4).toLocaleTimeString(), text: 'Worker Processing: Worker Node registered' },
  { time: new Date(Date.now() - 60000 * 3).toLocaleTimeString(), text: 'Execution Event: Financial Transaction validation completed. 42 violations flagged.' },
  { time: new Date(Date.now() - 60000 * 2).toLocaleTimeString(), text: 'Notification Sent: Validation digest sent to security-auditors@enterprise.com' },
  { time: new Date(Date.now() - 60000 * 1).toLocaleTimeString(), text: 'Validation Processing: Chrono-trigger tick checked.' },
];

export default function DashboardPage() {
  const { pushToast } = useDataset();
  const [tasks, setTasks] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [connections, setConnections] = useState([]);
  const [expandedTaskId, setExpandedTaskId] = useState(null);
  const [detailTab, setDetailTab] = useState('summary'); // 'summary' | 'sql' | 'logs'
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editFreqValue, setEditFreqValue] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedTasks = localStorage.getItem(TASKS_KEY);
    const storedTimeline = localStorage.getItem(FEED_KEY);
    const storedConnections = localStorage.getItem(CONNECTIONS_KEY);

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

    if (storedConnections) {
      setConnections(JSON.parse(storedConnections));
    } else {
      setConnections([
        { name: 'pg_production', type: 'postgresql', status: 'connected', isActive: true },
        { name: 'mysql_crm', type: 'mysql', status: 'connected', isActive: false },
        { name: 'mongo_logs', type: 'mongodb', status: 'connected', isActive: false },
      ]);
    }

    setLoading(false);
  }, []);

  // Simulating active validation operation logs
  useEffect(() => {
    if (loading) return;

    const phrases = [
      'Validation Processing: Scheduler cron validation checks completed.',
      'Worker Processing: Active container nodes validated (HEALTHY).',
      'Queue Event: Redis scheduler queue size: 0 pending.',
      'Task Step: Established handshake with pg_production database: OK.',
      'Background Task: Dispatched execution telemetry digest logs.',
      'Execution Event: Rules compilation completed successfully in 0.12s.',
    ];

    const interval = setInterval(() => {
      const newEvent = {
        time: new Date().toLocaleTimeString(),
        text: phrases[Math.floor(Math.random() * phrases.length)],
      };
      setTimeline((prev) => {
        const next = [newEvent, ...prev.slice(0, 14)];
        localStorage.setItem(FEED_KEY, JSON.stringify(next));
        return next;
      });
    }, 12000);

    return () => clearInterval(interval);
  }, [loading]);

  const saveTasks = (updatedTasks) => {
    setTasks(updatedTasks);
    localStorage.setItem(TASKS_KEY, JSON.stringify(updatedTasks));
  };

  const handleToggleStatus = (id, e) => {
    e.stopPropagation();
    const updated = tasks.map((task) => {
      if (task.id === id) {
        const nextStatus = task.status === 'active' ? 'paused' : 'active';
        return {
          ...task,
          status: nextStatus,
          nextRun: nextStatus === 'active' ? new Date(Date.now() + 3600000 * 12).toISOString() : null,
          emailStatus: nextStatus === 'active' ? 'Notification Sent: Active' : 'Notification Sent: Inactive (paused)',
          steps: nextStatus === 'active'
            ? [
                'Validation Processing: Validation trigger activated by user.',
                'Queue Event: Cron schedule enqueued into active_jobs.'
              ]
            : ['Validation Processing: Schedule paused by administrator.']
        };
      }
      return task;
    });
    saveTasks(updated);
    pushToast({
      tone: 'success',
      title: 'Validation Schedule Updated',
      message: 'The validation workflow trigger state has been updated.'
    });
  };

  const handleRerunTask = (id, e) => {
    e.stopPropagation();
    const updated = tasks.map((task) => {
      if (task.id === id) {
        return {
          ...task,
          lastRun: new Date().toISOString(),
          rowsScanned: task.rowsScanned + Math.floor(Math.random() * 50),
          rowsReturned: Math.floor(Math.random() * 5) === 0 ? Math.floor(Math.random() * 6) : 0,
        };
      }
      return task;
    });
    saveTasks(updated);

    const targetTask = tasks.find(t => t.id === id);
    const logEvent = {
      time: new Date().toLocaleTimeString(),
      text: `Execution Event: Ad-hoc validation check triggered for "${targetTask.name}" completed.`
    };
    setTimeline(prev => [logEvent, ...prev]);

    pushToast({
      tone: 'success',
      title: 'Validation Run Executed',
      message: `The ad-hoc validation check was executed successfully.`
    });
  };

  const handleDeleteTask = (id, e) => {
    e.stopPropagation();
    const updated = tasks.filter((t) => t.id !== id);
    saveTasks(updated);
    if (expandedTaskId === id) setExpandedTaskId(null);
    pushToast({
      tone: 'success',
      title: 'Validation Schedule Removed',
      message: 'The selected scheduled validation rule has been deleted.'
    });
  };

  const handleStartEdit = (task, e) => {
    e.stopPropagation();
    setEditingTaskId(task.id);
    setEditFreqValue(task.frequency);
  };

  const handleSaveEdit = (id, e) => {
    e.stopPropagation();
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
      title: 'Validation Schedule Changed',
      message: `Validation frequency updated to: ${editFreqValue}`
    });
  };

  const formatDateTime = (value) => {
    if (!value) return 'N/A';
    return new Intl.DateTimeFormat('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  };

  // Connected database summaries with active schedule statistics
  const dbSummaries = useMemo(() => {
    return connections.map((conn) => {
      const activeCount = tasks.filter((t) => t.dataset.startsWith(conn.name) && t.status === 'active').length;
      return { ...conn, activeCount };
    });
  }, [connections, tasks]);

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <p className="section-kicker">Platform Console</p>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white mt-1">Live Validation Dashboard</h2>
          <p className="text-xs text-slate-500 mt-1">
            Observe running validation tasks, connection contexts, and schedule operations.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader label="Loading operational feed..." />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          
          {/* Main task list (Widescreen 3-columns) */}
          <div className="lg:col-span-3 space-y-4">
            
            {/* Active scheduled validations section */}
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Scheduled Validation Tasks</h3>
                <span className="text-xs text-slate-400 font-semibold">{tasks.length} rules active</span>
              </div>

              {tasks.length === 0 ? (
                <div className="empty-state py-8">
                  <p className="text-slate-900 dark:text-white font-medium">Currently no scheduled validations running</p>
                  <p className="text-slate-500 text-xs mt-1">
                    Describe a business rule in the Rule Workspace and define a schedule trigger to begin.
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-850">
                  {tasks.map((task) => {
                    const isExpanded = expandedTaskId === task.id;
                    const isEditing = editingTaskId === task.id;

                    return (
                      <div key={task.id} className="py-3.5 first:pt-0 last:pb-0 space-y-3.5">
                        
                        {/* Summary inline row */}
                        <div
                          onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}
                          className="flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`h-2.5 w-2.5 rounded-full ${task.status === 'active' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                              <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">{task.name}</h4>
                            </div>
                            <p className="text-xs text-slate-500 italic mt-1.5 truncate">
                              "{task.originalPrompt}"
                            </p>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[11px] text-slate-400">
                              <span>
                                <strong className="text-slate-400 dark:text-slate-600">Database:</strong> {task.dataset}
                              </span>
                              <span>•</span>
                              <span>
                                <strong className="text-slate-400 dark:text-slate-600">Frequency:</strong> {task.frequency}
                              </span>
                              <span>•</span>
                              <span>
                                <strong className="text-slate-400 dark:text-slate-600">Rows Scanned:</strong> {task.rowsScanned.toLocaleString()}
                              </span>
                              <span>•</span>
                              <span className={task.rowsReturned > 0 ? 'text-rose-500 font-semibold' : ''}>
                                <strong className="text-slate-400 dark:text-slate-600">Violations:</strong> {task.rowsReturned}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center justify-between md:justify-end gap-5 text-xs" onClick={(e) => e.stopPropagation()}>
                            <div className="text-right hidden sm:block">
                              <span className="text-[10px] text-slate-400 uppercase tracking-wide block">Next execution</span>
                              <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 block">
                                {task.status === 'active' ? formatDateTime(task.nextRun) : 'Paused'}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <button
                                onClick={(e) => handleRerunTask(task.id, e)}
                                className="rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-1 font-semibold text-slate-700 dark:text-slate-300 transition-colors"
                              >
                                Run
                              </button>
                              <button
                                onClick={(e) => handleToggleStatus(task.id, e)}
                                className={`rounded px-2.5 py-1 font-semibold transition-colors ${
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

                        {/* Collapsible drawer with Progressive Tabs disclosure */}
                        {isExpanded && (
                          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/20 p-4 space-y-4">
                            
                            {/* Drawer Tabs */}
                            <div className="flex items-center gap-1.5 border-b border-slate-200 dark:border-slate-800 pb-2">
                              {[
                                ['summary', 'Execution Details'],
                                ['sql', 'SQL Preview'],
                                ['logs', 'Validation Operations Logs']
                              ].map(([tabId, label]) => (
                                <button
                                  key={tabId}
                                  onClick={() => setDetailTab(tabId)}
                                  className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${
                                    detailTab === tabId
                                      ? 'bg-slate-200 dark:bg-slate-800 text-slate-900 dark:text-white'
                                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
                                  }`}
                                >
                                  {label}
                                </button>
                              ))}
                            </div>

                            {/* Tab 1: Summary */}
                            {detailTab === 'summary' && (
                              <div className="grid gap-4 md:grid-cols-2 text-xs">
                                <div className="space-y-2">
                                  <div>
                                    <span className="text-[10px] uppercase font-semibold text-slate-400 block">Active Database Connector</span>
                                    <span className="text-slate-700 dark:text-slate-200 block mt-0.5">{task.dataset}</span>
                                  </div>
                                  <div>
                                    <span className="text-[10px] uppercase font-semibold text-slate-400 block">Natural Language Prompt</span>
                                    <p className="text-slate-700 dark:text-slate-300 block mt-0.5 italic">"{task.originalPrompt}"</p>
                                  </div>
                                </div>
                                <div className="space-y-2">
                                  <div className="flex justify-between items-center">
                                    <div>
                                      <span className="text-[10px] uppercase font-semibold text-slate-400 block">Execution duration</span>
                                      <span className="text-slate-700 dark:text-slate-200 block font-mono mt-0.5">{task.duration}</span>
                                    </div>
                                    <div>
                                      <span className="text-[10px] uppercase font-semibold text-slate-400 block">System Alerts Status</span>
                                      <span className="text-slate-700 dark:text-slate-200 block mt-0.5">{task.emailStatus}</span>
                                    </div>
                                  </div>
                                  <div>
                                    <span className="text-[10px] uppercase font-semibold text-slate-400 block">Last Run Triggered</span>
                                    <span className="text-slate-700 dark:text-slate-200 block mt-0.5">{formatDateTime(task.lastRun)}</span>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Tab 2: SQL Code block preview */}
                            {detailTab === 'sql' && (
                              <div>
                                <span className="text-[10px] uppercase font-semibold text-slate-400 block">Validation SQL</span>
                                <pre className="mt-1 bg-slate-950 p-3 rounded border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto leading-relaxed">
                                  {task.sql}
                                </pre>
                              </div>
                            )}

                            {/* Tab 3: Detailed execution timeline logs */}
                            {detailTab === 'logs' && (
                              <div className="space-y-3">
                                <span className="text-[10px] uppercase font-semibold text-slate-400 block">Step-by-step Operational logs</span>
                                <div className="rounded border border-slate-200 dark:border-slate-800 bg-slate-950 p-3.5 space-y-1.5 font-mono text-xs text-slate-300">
                                  {task.steps.map((step, idx) => (
                                    <div key={idx} className="flex gap-2">
                                      <span className="text-slate-500 select-none">[{idx + 1}]</span>
                                      <span>{step}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Action block bar inside progressive panel */}
                            <div className="flex items-center justify-between border-t border-slate-200 dark:border-slate-800/80 pt-3.5 mt-2">
                              <div className="flex items-center gap-3">
                                {isEditing ? (
                                  <div className="flex items-center gap-2">
                                    <input
                                      type="text"
                                      value={editFreqValue}
                                      onChange={(e) => setEditFreqValue(e.target.value)}
                                      placeholder="Frequency interval"
                                      className="input-shell py-0.5 px-2 text-xs w-40"
                                      title="Interval input"
                                    />
                                    <button
                                      onClick={(e) => handleSaveEdit(task.id, e)}
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
                                    onClick={(e) => handleStartEdit(task, e)}
                                    className="text-xs font-semibold text-sky-500 hover:text-sky-400 flex items-center gap-1"
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                                    </svg>
                                    Edit Schedule
                                  </button>
                                )}
                              </div>

                              <button
                                onClick={(e) => handleDeleteTask(task.id, e)}
                                className="text-xs font-semibold text-rose-500 hover:text-rose-450 flex items-center gap-1"
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

            {/* Live operational log feeds timeline */}
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Live Orchestration Timeline</h3>
                <p className="text-xs text-slate-400 mt-0.5">Real-time validation operations and active log traces.</p>
              </div>

              <div className="rounded border border-slate-200 dark:border-slate-800 bg-slate-950 p-4 font-mono text-xs h-[160px] overflow-y-auto space-y-2 leading-relaxed">
                {timeline.map((event, idx) => (
                  <div key={idx} className="flex gap-3">
                    <span className="text-slate-500 select-none">[{event.time}]</span>
                    <span className={event.text.includes('Failed') || event.text.includes('violations') ? 'text-rose-400 font-medium' : event.text.includes('completed') ? 'text-emerald-400' : 'text-slate-300'}>
                      {event.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Connected databases status widget on the right (1-column) */}
          <div className="space-y-4 text-xs">
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Active Databases</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">Connections status and active schedules count.</p>
              </div>

              <div className="space-y-3">
                {dbSummaries.map((db) => (
                  <div key={db.name} className="flex items-center justify-between border-b border-slate-100 dark:border-slate-850 pb-2.5 last:border-0 last:pb-0">
                    <div>
                      <span className="font-semibold text-slate-700 dark:text-slate-200 block truncate max-w-[120px]">{db.name}</span>
                      <span className="text-[10px] text-slate-400 block uppercase font-medium mt-0.5">{db.type}</span>
                    </div>
                    <div className="text-right">
                      <span className="font-semibold text-slate-700 dark:text-slate-200 block">{db.activeCount} rules</span>
                      <span className={`inline-flex items-center gap-1 mt-0.5 text-[10px] font-semibold ${db.status === 'connected' ? 'text-emerald-500' : 'text-slate-400'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${db.status === 'connected' ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        {db.status === 'connected' ? 'Online' : 'Offline'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-3">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Computational Nodes</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">Queue processor clusters health status.</p>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-850 pb-1.5">
                  <span className="text-slate-400">Worker Status</span>
                  <span className="font-semibold text-emerald-500">2 Active Nodes</span>
                </div>
                <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-850 pb-1.5">
                  <span className="text-slate-400">Redis Broker</span>
                  <span className="font-semibold text-emerald-500 font-mono">OK</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Queue Loads</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-200">Idle (0 jobs)</span>
                </div>
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
