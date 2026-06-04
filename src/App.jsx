import { useEffect, useMemo, useState } from 'react';
import {
  approvePlan,
  createDatabase,
  deleteDatabase,
  deleteJob,
  getAppSettings,
  getDashboardSummary,
  getDatabaseSchema,
  listAlerts,
  listDatabases,
  listJobs,
  listNotifications,
  pauseJob,
  planCommand,
  resumeJob,
  runJob,
  testDatabase,
  updateAISettings,
  updateNotificationSettings,
  updateJob,
} from './services/productApi';

const tabs = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    description: 'Live jobs, failures, and delivery health.',
  },
  {
    id: 'databases',
    label: 'Databases',
    description: 'Connect and inspect real data targets.',
  },
  {
    id: 'command',
    label: 'AI Command',
    description: 'Create validation jobs from plain English.',
  },
  {
    id: 'jobs',
    label: 'Jobs',
    description: 'Run, pause, edit, and delete checks.',
  },
  {
    id: 'alerts',
    label: 'Alerts',
    description: 'Failure history and notification delivery.',
  },
  {
    id: 'settings',
    label: 'Settings',
    description: 'Theme and integration status.',
  },
];

const defaultDbForm = {
  name: 'Docker Demo Postgres',
  db_type: 'postgresql',
  host: 'postgres',
  port: 5432,
  database: 'dq_test',
  username: 'dq_executor',
  password: 'dq_executor_password',
};

const exampleCommands = [
  'Every day check that salary should not be negative in employees and alert on Slack',
  'Check salary less than 10000 in employees every 5 minutes and alert on Slack',
  'Check department is not null in employees every day',
];

const schedulePresetOptions = [
  { label: 'Custom text', value: '__custom' },
  { label: 'Manual only', value: '' },
  { label: 'Every minute', value: 'every minute' },
  { label: 'Every 5 minutes', value: 'every 5 minutes' },
  { label: 'Every 15 minutes', value: 'every 15 minutes' },
  { label: 'Hourly', value: 'every hour' },
  { label: 'Daily at 9:00 AM', value: 'every day at 9:00 am' },
  { label: 'Daily at 10:30 AM', value: 'every day at 10:30 am' },
  { label: 'Weekly', value: 'weekly' },
  { label: 'Monthly', value: 'monthly' },
];

const notificationChannelOptions = [
  { label: 'Slack', value: 'slack' },
  { label: 'Email', value: 'email' },
];

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('hpe-theme') || 'light');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('hpe-theme', theme);
  }, [theme]);

  return [theme, setTheme];
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [theme, setTheme] = useTheme();
  const [databases, setDatabases] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [summary, setSummary] = useState(null);
  const [appSettings, setAppSettings] = useState(null);
  const [schema, setSchema] = useState(null);
  const [plan, setPlan] = useState(null);
  const [command, setCommand] = useState(exampleCommands[0]);
  const [selectedDatabaseId, setSelectedDatabaseId] = useState('');
  const [dbForm, setDbForm] = useState(defaultDbForm);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const selectedDatabase = useMemo(
    () => databases.find((database) => String(database.id) === String(selectedDatabaseId)) || databases[0],
    [databases, selectedDatabaseId],
  );

  const activeLabel = tabs.find((tab) => tab.id === activeTab)?.label || 'Dashboard';
  const activeJobs = jobs.filter((job) => job.is_enabled).length;
  const sentCount = summary?.notification_counts?.sent ?? notifications.filter((row) => row.status === 'sent').length;
  const failedCount = summary?.notification_counts?.failed ?? notifications.filter((row) => row.status === 'failed').length;

  const refresh = async () => {
    const [nextDatabases, nextJobs, nextAlerts, nextNotifications, nextSummary, nextSettings] = await Promise.all([
      listDatabases().catch(() => []),
      listJobs().catch(() => []),
      listAlerts().catch(() => []),
      listNotifications().catch(() => []),
      getDashboardSummary().catch(() => null),
      getAppSettings().catch(() => null),
    ]);
    setDatabases(nextDatabases);
    setJobs(nextJobs);
    setAlerts(nextAlerts);
    setNotifications(nextNotifications);
    setSummary(nextSummary);
    setAppSettings(nextSettings);
    setLastRefresh(new Date());
    setSelectedDatabaseId((current) => current || (nextDatabases[0] ? String(nextDatabases[0].id) : ''));
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const showToast = (tone, title, message) => {
    setToast({ tone, title, message });
  };

  const runAction = async (message, action, after = refresh) => {
    setBusy(true);
    setError('');
    setStatus('');
    try {
      const result = await action();
      setStatus(message);
      showToast('success', 'Done', message);
      await after?.(result);
      return result;
    } catch (actionError) {
      const actionMessage = actionError?.response?.data?.detail || actionError.message || 'Action failed.';
      setError(actionMessage);
      showToast('error', 'Action failed', actionMessage);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const addDatabase = () =>
    runAction('Database saved. Test the connection or inspect its schema next.', () => createDatabase(dbForm));

  const inspectSchema = (id) =>
    runAction('Schema loaded.', () => getDatabaseSchema(id), (result) => {
      setSchema(result);
    });

  const generatePlan = () =>
    runAction('Plan generated. Review before approving.', () =>
      planCommand({
        prompt: command,
        database_id: selectedDatabase ? Number(selectedDatabase.id) : null,
      }), (result) => {
      setPlan(result);
    });

  const savePlan = () =>
    runAction('Validation job saved. Scheduler will pick it up within one minute.', () => approvePlan(plan), async () => {
      setPlan(null);
      setActiveTab('jobs');
      await refresh();
    });

  const startVoice = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError('Voice input is not supported in this browser. Type the command instead.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      setCommand(event.results[0][0].transcript);
    };
    recognition.onerror = () => setError('Voice capture failed. Type the command instead.');
    recognition.start();
  };

  const currentView = {
    dashboard: (
      <Dashboard
        summary={summary}
        databases={databases}
        jobs={jobs}
        alerts={alerts}
        notifications={notifications}
        onTab={setActiveTab}
      />
    ),
    databases: (
      <Databases
        databases={databases}
        form={dbForm}
        setForm={setDbForm}
        schema={schema}
        busy={busy}
        onAdd={addDatabase}
        onTest={(id) => runAction('Connection test complete.', () => testDatabase(id))}
        onSchema={inspectSchema}
        onDelete={(id) => runAction('Database removed.', () => deleteDatabase(id), async () => {
          setSchema(null);
          await refresh();
        })}
      />
    ),
    command: (
      <AICommand
        command={command}
        setCommand={setCommand}
        databases={databases}
        selectedDatabaseId={selectedDatabaseId}
        setSelectedDatabaseId={setSelectedDatabaseId}
        plan={plan}
        busy={busy}
        onPlan={generatePlan}
        onApprove={savePlan}
        onVoice={startVoice}
      />
    ),
    jobs: (
      <Jobs
        jobs={jobs}
        busy={busy}
        onRun={(id) => runAction('Job executed.', () => runJob(id))}
        onPause={(id) => runAction('Job paused.', () => pauseJob(id))}
        onResume={(id) => runAction('Job resumed.', () => resumeJob(id))}
        onDelete={(id) => runAction('Job deleted.', () => deleteJob(id))}
        onUpdate={(id, payload) => runAction('Job updated.', () => updateJob(id, payload))}
      />
    ),
    alerts: <Alerts alerts={alerts} notifications={notifications} />,
    settings: (
      <Settings
        theme={theme}
        setTheme={setTheme}
        databases={databases}
        sentCount={sentCount}
        failedCount={failedCount}
        appSettings={appSettings}
        busy={busy}
        onSaveAI={(payload) => runAction('AI provider settings saved.', () => updateAISettings(payload), async (result) => {
          setAppSettings(result);
          await refresh();
        })}
        onSaveNotifications={(payload) => runAction('Notification settings saved.', () => updateNotificationSettings(payload), async (result) => {
          setAppSettings(result);
          await refresh();
        })}
      />
    ),
  }[activeTab];

  return (
    <div className="enterprise-shell">
      <aside className={`enterprise-sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">DQ</div>
          <div>
            <p className="section-kicker">HPE Data Quality</p>
            <h1>Intelligence Workspace</h1>
          </div>
        </div>

        <nav className="enterprise-nav" aria-label="Primary navigation">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`nav-card ${activeTab === tab.id ? 'nav-card-active' : ''}`}
              onClick={() => {
                setActiveTab(tab.id);
                setSidebarOpen(false);
              }}
            >
              <span>{tab.label}</span>
              <small>{tab.description}</small>
            </button>
          ))}
        </nav>

        <div className="sidebar-status">
          <span className="status-dot status-dot-good" />
          <div>
            <strong>{databases.length ? 'Backend connected' : 'Waiting for data'}</strong>
            <span>{activeJobs} active jobs</span>
          </div>
        </div>
      </aside>

      <main className="enterprise-main">
        <header className="enterprise-topbar">
          <div className="topbar-title">
            <button className="icon-button mobile-only" type="button" onClick={() => setSidebarOpen((value) => !value)} aria-label="Toggle navigation">
              <MenuIcon />
            </button>
            <div>
              <p className="section-kicker">Live Control Plane</p>
              <h2>{activeLabel}</h2>
            </div>
          </div>

          <div className="topbar-actions">
            <StatusChip label={`${databases.length} databases`} tone={databases.length ? 'good' : 'neutral'} />
            <StatusChip label={`${activeJobs} active jobs`} tone={activeJobs ? 'info' : 'neutral'} />
            <StatusChip label={`${failedCount} failed deliveries`} tone={failedCount ? 'bad' : 'neutral'} />
            <ThemeSwitch theme={theme} setTheme={setTheme} />
            <button className="secondary-button" type="button" onClick={refresh} disabled={busy}>
              Refresh
            </button>
          </div>
        </header>

        <div className="workspace-meta">
          <span>Updated {lastRefresh ? formatDate(lastRefresh) : 'not yet'}</span>
          <span>Real backend data only</span>
          <span>Scheduler refreshes jobs every 60 seconds</span>
        </div>

        {error && <div className="inline-banner inline-banner-error">{error}</div>}
        {status && <div className="inline-banner inline-banner-success">{status}</div>}

        {currentView}
      </main>
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

function Dashboard({ summary, databases, jobs, alerts, notifications, onTab }) {
  const recentJobs = jobs.slice(0, 5);
  const recentAlerts = alerts.slice(0, 5);
  const latestResults = summary?.latest_results || [];
  const deliveryFailures = notifications.filter((row) => row.status === 'failed').slice(0, 4);

  return (
    <div className="workspace-grid">
      <section className="hero-card span-all">
        <div>
          <p className="section-kicker">AI orchestration</p>
          <h3>Ask once. Validate continuously.</h3>
          <p>
            Create data quality jobs from natural language, run them through the orchestrator,
            and route failures to Slack or email with a real execution trail.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary-button" type="button" onClick={() => onTab('command')}>
            Create AI Job
          </button>
          <button className="secondary-button" type="button" onClick={() => onTab('databases')}>
            Manage Databases
          </button>
        </div>
      </section>

      <MetricGrid
        items={[
          { label: 'Databases', value: summary?.database_count ?? databases.length, hint: 'connected targets', tone: 'info' },
          { label: 'Active Jobs', value: summary?.active_job_count ?? jobs.filter((job) => job.is_enabled).length, hint: 'scheduled checks', tone: 'good' },
          { label: 'Failures Today', value: summary?.failure_count_today ?? recentAlerts.length, hint: 'rule failures', tone: 'bad' },
          { label: 'Notifications', value: Object.values(summary?.notification_counts || {}).reduce((a, b) => a + b, notifications.length), hint: 'delivery attempts', tone: 'neutral' },
        ]}
      />

      <section className="panel-card span-8">
        <PanelHeader title="Orchestrator Jobs" action="Open Jobs" onClick={() => onTab('jobs')} />
        <div className="stack-list">
          {recentJobs.map((job) => (
            <JobSummaryRow key={job.id} job={job} />
          ))}
          {!recentJobs.length && <EmptyState title="No jobs yet" message="Create one from AI Command." />}
        </div>
      </section>

      <section className="panel-card span-4">
        <PanelHeader title="Connected Databases" action="Open" onClick={() => onTab('databases')} />
        <div className="stack-list compact-stack">
          {databases.slice(0, 5).map((database) => (
            <CompactRow
              key={database.id}
              title={database.name}
              meta={`${database.username}@${database.host}`}
              status={database.status}
              tone={database.status === 'connected' ? 'good' : database.status === 'failed' ? 'bad' : 'neutral'}
            />
          ))}
          {!databases.length && <EmptyState title="No databases" message="Add a Postgres connection to begin." compact />}
        </div>
      </section>

      <section className="panel-card span-6">
        <PanelHeader title="Latest Results" />
        <div className="stack-list">
          {latestResults.slice(0, 5).map((result) => (
            <CompactRow
              key={result.result_id}
              title={result.rule_name}
              meta={`${result.observed_value ?? 'no value'} observed at ${formatDate(result.executed_at)}`}
              status={result.status}
              tone={result.status === 'PASS' ? 'good' : result.status === 'FAIL' ? 'bad' : 'neutral'}
            />
          ))}
          {!latestResults.length && <EmptyState title="No runs" message="Run a saved job to populate results." compact />}
        </div>
      </section>

      <section className="panel-card span-6">
        <PanelHeader title="Delivery Health" action="Open Alerts" onClick={() => onTab('alerts')} />
        <div className="stack-list">
          {deliveryFailures.map((notification) => (
            <CompactRow
              key={notification.id}
              title={`${notification.channel} delivery failed`}
              meta={notification.error_message || formatDate(notification.sent_at)}
              status="failed"
              tone="bad"
            />
          ))}
          {!deliveryFailures.length && <EmptyState title="No failed deliveries" message="Slack and email logs will appear here." compact />}
        </div>
      </section>
    </div>
  );
}

function Databases({ databases, form, setForm, schema, busy, onAdd, onTest, onSchema, onDelete }) {
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="workspace-grid">
      <section className="panel-card span-all">
        <PanelHeader title="Add PostgreSQL Database" subtitle="Connections are stored in metadata Postgres and used by the orchestrator." />
        <div className="form-grid">
          <Field label="Friendly name">
            <input value={form.name} onChange={(event) => update('name', event.target.value)} />
          </Field>
          <Field label="Host">
            <input value={form.host} onChange={(event) => update('host', event.target.value)} />
          </Field>
          <Field label="Port">
            <input type="number" value={form.port} onChange={(event) => update('port', Number(event.target.value))} />
          </Field>
          <Field label="Database">
            <input value={form.database} onChange={(event) => update('database', event.target.value)} />
          </Field>
          <Field label="Username">
            <input value={form.username} onChange={(event) => update('username', event.target.value)} />
          </Field>
          <Field label="Password">
            <input type="password" value={form.password} onChange={(event) => update('password', event.target.value)} />
          </Field>
        </div>
        <div className="button-row form-actions">
          <button disabled={busy} className="primary-button" type="button" onClick={onAdd}>
            Save Database
          </button>
        </div>
      </section>

      <section className="panel-card span-all">
        <PanelHeader title="Connected Databases" subtitle="Test the connection or inspect schema before creating AI jobs." />
        <div className="database-grid">
          {databases.map((database) => (
            <article className="database-card" key={database.id}>
              <div className="card-title-row">
                <div>
                  <h3>{database.name}</h3>
                  <p>{database.username}@{database.host}:{database.port}/{database.database}</p>
                </div>
                <StatusChip label={database.status} tone={database.status === 'connected' ? 'good' : database.status === 'failed' ? 'bad' : 'neutral'} />
              </div>
              <div className="button-row">
                <button className="secondary-button" onClick={() => onTest(database.id)} type="button" disabled={busy}>Test</button>
                <button className="secondary-button" onClick={() => onSchema(database.id)} type="button" disabled={busy}>Schema</button>
                <button className="danger-button" onClick={() => onDelete(database.id)} type="button" disabled={busy}>Delete</button>
              </div>
            </article>
          ))}
          {!databases.length && <EmptyState title="No databases saved" message="Add Docker Demo Postgres or another Postgres target." />}
        </div>
      </section>

      {schema && (
        <section className="panel-card span-all">
          <PanelHeader title="Schema Browser" subtitle={`${schema.tables.length} tables visible to this connection.`} />
          <div className="schema-browser">
            {schema.tables.map((table) => (
              <article key={table.qualified_name} className="schema-card">
                <div className="card-title-row">
                  <div>
                    <h3>{table.qualified_name}</h3>
                    <p>{table.columns.length} columns</p>
                  </div>
                </div>
                <div className="chip-row">
                  {table.columns.slice(0, 10).map((column) => (
                    <span className="chip" key={column.name}>{column.name} <small>{column.data_type}</small></span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function AICommand({ command, setCommand, databases, selectedDatabaseId, setSelectedDatabaseId, plan, busy, onPlan, onApprove, onVoice }) {
  const [previewTimezone, setPreviewTimezone] = useState('Asia/Kolkata');
  const previewTimezones = plan?.schedule_preview?.timezones || [];
  const selectedTimezonePreview =
    previewTimezones.find((item) => item.timezone === previewTimezone) ||
    previewTimezones[0] ||
    null;

  useEffect(() => {
    if (plan?.schedule_preview?.scheduler_timezone) {
      setPreviewTimezone(plan.schedule_preview.scheduler_timezone);
    }
  }, [plan?.generation_id, plan?.schedule_preview?.scheduler_timezone]);

  return (
    <div className="workspace-grid">
      <section className="panel-card span-7">
        <PanelHeader title="Natural Language Job Builder" subtitle="The configured AI provider plans jobs; an internal fallback keeps demos offline-safe." />
        <div className="form-grid single">
          <Field label="Target database">
            <select value={selectedDatabaseId} onChange={(event) => setSelectedDatabaseId(event.target.value)}>
              {databases.map((database) => (
                <option key={database.id} value={database.id}>{database.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Command">
            <textarea
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              rows={8}
              placeholder="Example: every day check salary is not negative in employees and alert on Slack"
            />
          </Field>
        </div>
        <div className="button-row form-actions">
          <button className="primary-button" type="button" disabled={busy || !command.trim()} onClick={onPlan}>
            Generate Plan
          </button>
          <button className="secondary-button" type="button" onClick={onVoice}>
            Voice Input
          </button>
        </div>
      </section>

      <section className="panel-card span-5">
        <PanelHeader title="Command Examples" />
        <div className="example-stack">
          {exampleCommands.map((example) => (
            <button key={example} type="button" onClick={() => setCommand(example)}>
              {example}
            </button>
          ))}
        </div>
      </section>

      {plan && (
        <section className="panel-card span-all">
          <PanelHeader title="Review Generated Job" subtitle="The backend validates SQL safety and dry-runs before returning this plan." />
          <div className="review-grid">
            <InfoCard label="Database" value={plan.database_name} />
            <InfoCard label="Table" value={plan.table_name} />
            <InfoCard label="Schedule" value={plan.schedule_text || 'Manual'} />
            {plan.schedule_cron && <InfoCard label="Cron" value={plan.schedule_cron} />}
            {plan.schedule_preview?.scheduler_timezone && (
              <InfoCard label="Scheduler TZ" value={plan.schedule_preview.scheduler_timezone} />
            )}
            <InfoCard label="Severity" value={plan.severity} />
            <InfoCard label="Planner" value={`${plan.source} (${plan.confidence} confidence)`} />
            <InfoCard label="Dry Run" value={formatDryRun(plan.dry_run)} />
          </div>
          {plan.schedule_preview?.timezones?.length ? (
            <>
              <div className="review-toolbar">
                <Field label="Preview timezone">
                  <select value={previewTimezone} onChange={(event) => setPreviewTimezone(event.target.value)}>
                    {previewTimezones.map((item) => (
                      <option key={item.timezone} value={item.timezone}>
                        {item.label} ({item.timezone})
                      </option>
                    ))}
                  </select>
                </Field>
                <InfoCard
                  label={`Selected next run ${selectedTimezonePreview?.label || ''}`}
                  value={selectedTimezonePreview?.display || 'No scheduled run'}
                />
              </div>
              <div className="review-grid">
                {plan.schedule_preview.timezones.map((item) => (
                  <InfoCard key={item.timezone} label={`Next run ${item.label}`} value={item.display} />
                ))}
              </div>
            </>
          ) : null}
          <pre className="sql-box">{plan.sql}</pre>
          <p className="muted-copy">{plan.explanation}</p>
          <div className="button-row">
            <button className="primary-button" type="button" disabled={busy} onClick={onApprove}>
              Approve And Schedule
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function Jobs({ jobs, busy, onRun, onPause, onResume, onDelete, onUpdate }) {
  const [drafts, setDrafts] = useState({});
  const updateDraft = (id, key, value) => setDrafts((current) => ({ ...current, [id]: { ...current[id], [key]: value } }));

  const saveJob = (job) => {
    const draft = drafts[job.id] || {};
    onUpdate(job.id, {
      schedule_text: draft.schedule_text ?? job.schedule_text ?? '',
      severity: draft.severity ?? job.severity,
      notification_channels: draft.notification_channels ?? job.notification_channels ?? ['slack'],
      is_enabled: job.is_enabled,
    });
  };

  return (
    <section className="panel-card span-all">
      <PanelHeader title="Orchestrator Jobs" subtitle="These are real saved rules loaded from the backend registry." />
      <div className="job-list compact-jobs">
        {jobs.map((job) => {
          const draft = drafts[job.id] || {};
          const scheduleText = draft.schedule_text ?? job.schedule_text ?? '';
          const channels = draft.notification_channels ?? job.notification_channels ?? ['slack'];
          return (
            <article className="job-card" key={job.id}>
              <div className="card-title-row">
                <div>
                  <h3>{job.rule_name}</h3>
                  <p>{job.database_name || 'Default database'} / {job.table_name || 'table detected from SQL'}</p>
                </div>
                <div className="status-cluster">
                  <StatusChip label={job.is_enabled ? 'active' : 'paused'} tone={job.is_enabled ? 'good' : 'neutral'} />
                  <StatusChip
                    label={job.last_status || job.scheduler_status}
                    tone={job.last_status === 'PASS' ? 'good' : job.last_status === 'FAIL' || job.last_status === 'ERROR' ? 'bad' : 'info'}
                  />
                </div>
              </div>

              <div className="job-detail-grid">
                <InfoCard label="Schedule" value={job.schedule_text || job.schedule_cron || 'Manual'} />
                <InfoCard label="Severity" value={job.severity} />
                <InfoCard label="Last observed" value={job.last_observed_value ?? 'None'} />
                <InfoCard label="Last run" value={formatDate(job.last_run_at)} />
              </div>

              <pre className="sql-box compact">{job.sql}</pre>

              <div className="job-editor-grid">
                <Field label="Schedule preset">
                  <select
                    value={schedulePresetValue(scheduleText)}
                    onChange={(event) => {
                      if (event.target.value !== '__custom') {
                        updateDraft(job.id, 'schedule_text', event.target.value);
                      }
                    }}
                  >
                    {schedulePresetOptions.map((option) => (
                      <option key={option.value || 'manual'} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Schedule text">
                  <input
                    value={scheduleText}
                    onChange={(event) => updateDraft(job.id, 'schedule_text', event.target.value)}
                    placeholder="manual, every 5 minutes, every day at 10:30 am"
                  />
                </Field>
                <Field label="Severity">
                  <select value={draft.severity ?? job.severity} onChange={(event) => updateDraft(job.id, 'severity', event.target.value)}>
                    {['critical', 'high', 'medium', 'low'].map((severity) => <option key={severity}>{severity}</option>)}
                  </select>
                </Field>
                <div className="field">
                  <span>Notifications</span>
                  <div className="checkbox-row">
                    {notificationChannelOptions.map((channel) => (
                      <label className="mini-check" key={channel.value}>
                        <input
                          type="checkbox"
                          checked={channels.includes(channel.value)}
                          onChange={() => updateDraft(job.id, 'notification_channels', toggleChannel(channels, channel.value))}
                        />
                        <span>{channel.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              <div className="button-row job-actions">
                <button disabled={busy} className="secondary-button" onClick={() => onRun(job.id)} type="button">Run Now</button>
                <button disabled={busy} className="secondary-button" onClick={() => job.is_enabled ? onPause(job.id) : onResume(job.id)} type="button">
                  {job.is_enabled ? 'Pause' : 'Resume'}
                </button>
                <button disabled={busy} className="secondary-button" onClick={() => saveJob(job)} type="button">Save Changes</button>
                <button disabled={busy} className="danger-button" onClick={() => onDelete(job.id)} type="button">Delete</button>
              </div>
            </article>
          );
        })}
        {!jobs.length && <EmptyState title="No orchestrator jobs" message="Generate and approve a plan from AI Command." />}
      </div>
    </section>
  );
}

function Alerts({ alerts, notifications }) {
  return (
    <div className="workspace-grid">
      <section className="panel-card span-7">
        <PanelHeader title="Failure Alerts" subtitle="Violation batches and event records created by failing rules." />
        <div className="stack-list">
          {alerts.slice(0, 30).map((alert) => (
            <CompactRow
              key={alert.id}
              title={alert.rule_name || `Rule ${alert.rule_id}`}
              meta={`${alert.violation_count || 0} violations at ${formatDate(alert.created_at || alert.first_seen)}`}
              status={alert.status || alert.severity}
              tone={alert.status === 'dispatched' ? 'good' : 'bad'}
            />
          ))}
          {!alerts.length && <EmptyState title="No alerts" message="Failures appear here after rule execution." />}
        </div>
      </section>

      <section className="panel-card span-5 delivery-panel">
        <PanelHeader title="Notification Delivery" subtitle="Slack and email send results recorded by the backend." />
        <div className="stack-list delivery-log">
          {notifications.slice(0, 30).map((notification) => (
            <CompactRow
              key={notification.id}
              title={`${titleCase(notification.channel)} delivery`}
              meta={notification.error_message || formatDate(notification.sent_at)}
              status={notification.status}
              tone={notification.status === 'sent' ? 'good' : notification.status === 'failed' ? 'bad' : 'neutral'}
            />
          ))}
          {!notifications.length && <EmptyState title="No delivery logs" message="Slack and email delivery attempts will appear here." />}
        </div>
      </section>
    </div>
  );
}

function Settings({ theme, setTheme, databases, sentCount, failedCount, appSettings, busy, onSaveAI, onSaveNotifications }) {
  const ai = appSettings?.ai;
  const notifications = appSettings?.notifications;
  const [aiForm, setAiForm] = useState({
    provider: 'gemini',
    model: 'gemini-2.5-flash',
    api_key: '',
  });
  const [notificationForm, setNotificationForm] = useState({
    admin_email: '',
    notification_email_from: '',
    smtp_server: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    smtp_use_tls: true,
    slack_webhook_url: '',
  });

  useEffect(() => {
    if (!ai) return;
    setAiForm((current) => ({
      ...current,
      provider: ai.provider || 'gemini',
      model: ai.model || 'gemini-2.5-flash',
      api_key: '',
    }));
  }, [ai]);

  useEffect(() => {
    if (!notifications) return;
    setNotificationForm((current) => ({
      ...current,
      admin_email: notifications.admin_email || '',
      notification_email_from: notifications.notification_email_from || '',
      smtp_server: notifications.smtp_server || '',
      smtp_port: notifications.smtp_port || 587,
      smtp_username: notifications.smtp_username || '',
      smtp_password: '',
      smtp_use_tls: notifications.smtp_use_tls ?? true,
      slack_webhook_url: '',
    }));
  }, [notifications]);

  const providerOptions = ai?.providers || [
    { id: 'gemini', label: 'Gemini', default_model: 'gemini-2.5-flash' },
    { id: 'openai', label: 'OpenAI', default_model: 'gpt-4o-mini' },
    { id: 'anthropic', label: 'Claude / Anthropic', default_model: 'claude-3-5-haiku-latest' },
    { id: 'openrouter', label: 'OpenRouter', default_model: 'openai/gpt-4o-mini' },
    { id: 'groq', label: 'Groq', default_model: 'llama3-8b-8192' },
  ];

  const setAI = (key, value) => {
    setAiForm((current) => {
      if (key !== 'provider') return { ...current, [key]: value };
      const option = providerOptions.find((item) => item.id === value);
      return {
        ...current,
        provider: value,
        model: option?.default_model || current.model,
      };
    });
  };

  const setNotification = (key, value) => {
    setNotificationForm((current) => ({ ...current, [key]: value }));
  };

  const saveAI = () => {
    onSaveAI({
      provider: aiForm.provider,
      model: aiForm.model,
      api_key: aiForm.api_key.trim() || undefined,
    });
  };

  const saveNotifications = () => {
    onSaveNotifications({
      ...notificationForm,
      smtp_password: notificationForm.smtp_password.trim() || undefined,
      slack_webhook_url: notificationForm.slack_webhook_url.trim() || undefined,
    });
  };

  return (
    <div className="workspace-grid">
      <section className="panel-card span-all">
        <PanelHeader title="AI Provider" subtitle="Choose the model used by AI Command. Secrets are saved in backend settings and never displayed again." />
        <div className="settings-form-grid">
          <Field label="Provider">
            <select value={aiForm.provider} onChange={(event) => setAI('provider', event.target.value)}>
              {providerOptions.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Model">
            <input value={aiForm.model} onChange={(event) => setAI('model', event.target.value)} placeholder="gemini-2.5-flash" />
          </Field>
          <Field label="API key">
            <input
              type="password"
              value={aiForm.api_key}
              onChange={(event) => setAI('api_key', event.target.value)}
              placeholder={ai?.has_api_key ? `Saved (${ai.masked_api_key})` : 'Paste provider API key'}
            />
          </Field>
          <div className="settings-status-card">
            <span>Current status</span>
            <strong>{ai?.has_api_key ? `${titleCase(ai.provider)} key saved` : 'No AI key saved'}</strong>
            <small>Fallback planner stays internal if the provider is unavailable.</small>
          </div>
        </div>
        <div className="button-row form-actions">
          <button className="primary-button" type="button" disabled={busy} onClick={saveAI}>
            Save AI Settings
          </button>
        </div>
      </section>

      <section className="panel-card span-all">
        <PanelHeader title="Notifications" subtitle="Control where rule failures are sent. Leave secret fields blank to keep the saved value." />
        <div className="settings-form-grid">
          <Field label="Alert recipient email">
            <input value={notificationForm.admin_email} onChange={(event) => setNotification('admin_email', event.target.value)} placeholder="you@example.com" />
          </Field>
          <Field label="Email from">
            <input value={notificationForm.notification_email_from} onChange={(event) => setNotification('notification_email_from', event.target.value)} placeholder="alerts@example.com" />
          </Field>
          <Field label="SMTP server">
            <input value={notificationForm.smtp_server} onChange={(event) => setNotification('smtp_server', event.target.value)} placeholder="smtp.gmail.com" />
          </Field>
          <Field label="SMTP port">
            <input type="number" value={notificationForm.smtp_port} onChange={(event) => setNotification('smtp_port', Number(event.target.value))} />
          </Field>
          <Field label="SMTP username">
            <input value={notificationForm.smtp_username} onChange={(event) => setNotification('smtp_username', event.target.value)} placeholder="mailbox@example.com" />
          </Field>
          <Field label="SMTP password / app password">
            <input
              type="password"
              value={notificationForm.smtp_password}
              onChange={(event) => setNotification('smtp_password', event.target.value)}
              placeholder={notifications?.has_smtp_password ? `Saved (${notifications.masked_smtp_password})` : 'Paste app password'}
            />
          </Field>
          <Field label="Slack webhook">
            <input
              type="password"
              value={notificationForm.slack_webhook_url}
              onChange={(event) => setNotification('slack_webhook_url', event.target.value)}
              placeholder={notifications?.slack_configured ? `Saved (${notifications.masked_slack_webhook})` : 'Paste Slack webhook'}
            />
          </Field>
          <label className="toggle-field">
            <input
              type="checkbox"
              checked={notificationForm.smtp_use_tls}
              onChange={(event) => setNotification('smtp_use_tls', event.target.checked)}
            />
            <span>Use TLS for SMTP</span>
          </label>
        </div>
        <div className="settings-health-row">
          <StatusChip label={`${sentCount} sent`} tone="good" />
          <StatusChip label={`${failedCount} failed`} tone={failedCount ? 'bad' : 'neutral'} />
          <StatusChip label={notifications?.slack_configured ? 'Slack configured' : 'Slack not configured'} tone={notifications?.slack_configured ? 'good' : 'neutral'} />
          <StatusChip label={notifications?.has_smtp_password ? 'SMTP password saved' : 'SMTP password missing'} tone={notifications?.has_smtp_password ? 'good' : 'neutral'} />
        </div>
        <div className="button-row">
          <button className="primary-button" type="button" disabled={busy} onClick={saveNotifications}>
            Save Notification Settings
          </button>
        </div>
      </section>

      <section className="panel-card span-all">
        <PanelHeader title="Theme" subtitle="Default stays light; dark and system modes are available for demo preference." />
        <div className="theme-grid">
          {['light', 'dark', 'system'].map((mode) => (
            <button
              key={mode}
              className={`theme-card ${theme === mode ? 'theme-card-active' : ''}`}
              type="button"
              onClick={() => setTheme(mode)}
            >
              <span>{titleCase(mode)}</span>
              <small>{mode === 'system' ? 'Follow OS preference' : `${titleCase(mode)} interface`}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel-card span-all">
        <PanelHeader title="Runtime Snapshot" subtitle="Read-only health summary from the current workspace." />
        <div className="settings-grid">
          <InfoCard label="Database targets" value={`${databases.length} saved`} />
          <InfoCard label="Theme" value={theme} />
          <InfoCard label="AI provider" value={ai ? titleCase(ai.provider) : 'Loading'} />
          <InfoCard label="Email recipient" value={notifications?.admin_email || 'Not set'} />
        </div>
      </section>
    </div>
  );
}

function MetricGrid({ items }) {
  return (
    <div className="metric-grid span-all">
      {items.map((item) => (
        <article className={`metric-card metric-${item.tone}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <p>{item.hint}</p>
        </article>
      ))}
    </div>
  );
}

function PanelHeader({ title, subtitle, action, onClick }) {
  return (
    <div className="panel-header">
      <div>
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action && <button className="link-button" type="button" onClick={onClick}>{action}</button>}
    </div>
  );
}

function JobSummaryRow({ job }) {
  return (
    <div className="list-row">
      <div>
        <strong>{job.rule_name}</strong>
        <span>{job.database_name || 'Default database'} / {job.table_name || 'table detected from SQL'}</span>
      </div>
      <div className="row-meta">
        <StatusChip label={job.last_status || job.scheduler_status} tone={job.last_status === 'FAIL' || job.last_status === 'ERROR' ? 'bad' : job.last_status === 'PASS' ? 'good' : 'info'} />
        <small>{job.schedule_text || job.schedule_cron || 'manual'}</small>
      </div>
    </div>
  );
}

function CompactRow({ title, meta, status, tone = 'neutral' }) {
  return (
    <div className="list-row">
      <div>
        <strong>{title}</strong>
        <span>{meta}</span>
      </div>
      <StatusChip label={status || 'unknown'} tone={tone} />
    </div>
  );
}

function InfoCard({ label, value }) {
  return (
    <div className="info-card">
      <span>{label}</span>
      <strong>{value ?? 'None'}</strong>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function StatusChip({ label, tone = 'neutral' }) {
  return <span className={`status-chip status-${tone}`}>{label}</span>;
}

function EmptyState({ title, message, compact = false }) {
  return (
    <div className={`empty-state ${compact ? 'empty-state-compact' : ''}`}>
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

function Toast({ toast, onClose }) {
  return (
    <div className={`toast toast-${toast.tone}`}>
      <div>
        <strong>{toast.title}</strong>
        <span>{toast.message}</span>
      </div>
      <button type="button" onClick={onClose} aria-label="Dismiss notification">x</button>
    </div>
  );
}

function ThemeSwitch({ theme, setTheme }) {
  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span className="theme-toggle-icon">{theme === 'dark' ? <SunIcon /> : <MoonIcon />}</span>
      <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
    </button>
  );
}

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4a8.5 8.5 0 1 0 11.5 11.5Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6" />
    </svg>
  );
}

function schedulePresetValue(value) {
  const normalized = String(value ?? '').trim().toLowerCase();
  const matchedPreset = schedulePresetOptions.find((option) => option.value === normalized);
  return matchedPreset ? matchedPreset.value : '__custom';
}

function toggleChannel(channels, channel) {
  const currentChannels = Array.isArray(channels) ? channels : [];
  if (currentChannels.includes(channel)) {
    const remaining = currentChannels.filter((item) => item !== channel);
    return remaining.length ? remaining : [channel];
  }
  return [...currentChannels, channel];
}

function formatDryRun(dryRun) {
  if (!dryRun?.row) return 'No dry run row';
  return Object.entries(dryRun.row)
    .map(([key, value]) => `${key}: ${value}`)
    .join(', ');
}

function formatDate(value) {
  if (!value) return 'not run yet';
  return new Date(value).toLocaleString();
}

function titleCase(value) {
  if (!value) return 'Unknown';
  return String(value).charAt(0).toUpperCase() + String(value).slice(1);
}
