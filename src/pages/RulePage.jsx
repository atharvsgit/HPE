import { useEffect, useState } from 'react';
import StatusBadge from '../components/common/StatusBadge';
import RuleBuilder from '../components/ruleBuilder/RuleBuilder';
import { useDataset } from '../context/DatasetContext';

const CONNECTIONS_KEY = 'pulseqc:db-connections';

// Seed database datasets mapping
const mockDatabaseConfigs = {
  'pg_production': {
    id: 'db-pg-prod',
    name: 'pg_production',
    sourceType: 'database',
    subType: 'postgresql',
    records: 843210,
    schema: [
      { columnName: 'id', dataType: 'integer', nullCount: 0 },
      { columnName: 'transaction_amount', dataType: 'decimal', nullCount: 0 },
      { columnName: 'status', dataType: 'varchar', nullCount: 5 },
      { columnName: 'created_at', dataType: 'timestamp', nullCount: 0 }
    ],
    rows: [
      { id: 1, transaction_amount: 120.50, status: 'completed', created_at: '2026-05-27T10:00:00Z' },
      { id: 2, transaction_amount: 5400.00, status: 'completed', created_at: '2026-05-27T10:05:00Z' },
      { id: 3, transaction_amount: -5.00, status: 'error', created_at: '2026-05-27T10:10:00Z' },
      { id: 4, transaction_amount: 32000.00, status: 'pending', created_at: '2026-05-27T10:15:00Z' }
    ]
  },
  'mysql_crm': {
    id: 'db-mysql-crm',
    name: 'mysql_crm',
    sourceType: 'database',
    subType: 'mysql',
    records: 15420,
    schema: [
      { columnName: 'id', dataType: 'integer', nullCount: 0 },
      { columnName: 'email', dataType: 'varchar', nullCount: 14 },
      { columnName: 'name', dataType: 'varchar', nullCount: 0 },
      { columnName: 'salary', dataType: 'integer', nullCount: 12 }
    ],
    rows: [
      { id: 1, email: 'john.doe@company.com', name: 'John Doe', salary: 85000 },
      { id: 2, email: 'jane.smith@company.com', name: 'Jane Smith', salary: 92000 },
      { id: 3, email: '', name: 'Bob Johnson', salary: 45000 },
      { id: 4, email: 'invalid-email', name: 'Alice Williams', salary: -1000 }
    ]
  },
  'mongo_logs': {
    id: 'db-mongo-logs',
    name: 'mongo_logs',
    sourceType: 'database',
    subType: 'mongodb',
    records: 4500,
    schema: [
      { columnName: '_id', dataType: 'string', nullCount: 0 },
      { columnName: 'attendance', dataType: 'number', nullCount: 0 },
      { columnName: 'marks', dataType: 'number', nullCount: 4 },
      { columnName: 'student_name', dataType: 'string', nullCount: 0 }
    ],
    rows: [
      { _id: '507f191e810c19729de860e1', attendance: 85, marks: 78, student_name: 'David Brown' },
      { _id: '507f191e810c19729de860e2', attendance: 65, marks: 45, student_name: 'Emily Davis' },
      { _id: '507f191e810c19729de860e3', attendance: 92, marks: 95, student_name: 'Michael Miller' }
    ]
  },
  'stripe_billing_api': {
    id: 'db-stripe-api',
    name: 'stripe_billing_api',
    sourceType: 'api',
    subType: 'rest',
    records: 3200,
    schema: [
      { columnName: 'id', dataType: 'string', nullCount: 0 },
      { columnName: 'amount', dataType: 'number', nullCount: 0 },
      { columnName: 'currency', dataType: 'string', nullCount: 0 },
      { columnName: 'customer_email', dataType: 'string', nullCount: 2 }
    ],
    rows: [
      { id: 'ch_1', amount: 2000, currency: 'usd', customer_email: 'finance@billing.com' },
      { id: 'ch_2', amount: 5000, currency: 'eur', customer_email: 'sales@billing.com' }
    ]
  }
};

const initialConnections = [
  { name: 'pg_production', type: 'postgresql', status: 'connected', isActive: true },
  { name: 'mysql_crm', type: 'mysql', status: 'connected', isActive: false },
  { name: 'mongo_logs', type: 'mongodb', status: 'connected', isActive: false },
  { name: 'stripe_billing_api', type: 'api', status: 'disconnected', isActive: false },
];

export default function RulePage() {
  const { selectedDataset, replaceDataset, pushToast } = useDataset();
  const [connections, setConnections] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newConnName, setNewConnName] = useState('');
  const [newConnType, setNewConnType] = useState('postgresql');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(CONNECTIONS_KEY);
    let currentConnections = [];
    if (stored) {
      currentConnections = JSON.parse(stored);
      setConnections(currentConnections);
    } else {
      currentConnections = initialConnections;
      setConnections(initialConnections);
      localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(initialConnections));
    }

    // Set the initial active dataset in context if none is loaded
    const active = currentConnections.find((c) => c.isActive && c.status === 'connected');
    if (active && !selectedDataset) {
      const config = mockDatabaseConfigs[active.name];
      if (config) {
        replaceDataset(config);
      }
    }
  }, [replaceDataset, selectedDataset]);

  const handleSwitchDatabase = (name) => {
    const target = connections.find((c) => c.name === name);
    if (!target || target.status !== 'connected') {
      pushToast({
        tone: 'error',
        title: 'Connection Offline',
        message: `Database "${name}" is disconnected. Reconnect it first.`,
      });
      return;
    }

    const updated = connections.map((c) => ({
      ...c,
      isActive: c.name === name,
    }));
    setConnections(updated);
    localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(updated));

    // Load mock configuration schema into global context
    const config = mockDatabaseConfigs[name];
    if (config) {
      replaceDataset(config);
      pushToast({
        tone: 'success',
        title: 'Active Database Switched',
        message: `Now targeting "${name}" for schema and query rules.`,
      });
    }
  };

  const handleDisconnect = (name, e) => {
    e.stopPropagation();
    const updated = connections.map((c) => {
      if (c.name === name) {
        return { ...c, status: 'disconnected', isActive: false };
      }
      return c;
    });
    setConnections(updated);
    localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(updated));

    if (selectedDataset?.name === name) {
      replaceDataset(null);
    }

    pushToast({
      tone: 'info',
      title: 'Database Disconnected',
      message: `Successfully disconnected "${name}".`,
    });
  };

  const handleConnect = (name, e) => {
    e.stopPropagation();
    const updated = connections.map((c) => {
      if (c.name === name) {
        return { ...c, status: 'connected' };
      }
      return c;
    });
    setConnections(updated);
    localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(updated));

    pushToast({
      tone: 'success',
      title: 'Database Connected',
      message: `Connection re-established with "${name}".`,
    });
  };

  const handleCreateConnection = (e) => {
    e.preventDefault();
    if (!newConnName.trim()) return;

    setSubmitting(true);
    setTimeout(() => {
      const formattedName = newConnName.toLowerCase().replace(/\s+/g, '_');
      const newConn = {
        name: formattedName,
        type: newConnType,
        status: 'connected',
        isActive: false
      };

      // Register mock schema mapping
      mockDatabaseConfigs[formattedName] = {
        id: `db-custom-${Date.now()}`,
        name: formattedName,
        sourceType: 'database',
        subType: newConnType,
        records: 5000,
        schema: [
          { columnName: 'id', dataType: 'integer', nullCount: 0 },
          { columnName: 'value', dataType: 'decimal', nullCount: 2 },
          { columnName: 'created_at', dataType: 'timestamp', nullCount: 0 }
        ],
        rows: [
          { id: 1, value: 10.5, created_at: new Date().toISOString() },
          { id: 2, value: null, created_at: new Date().toISOString() }
        ]
      };

      const updated = [...connections, newConn];
      setConnections(updated);
      localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(updated));
      setNewConnName('');
      setIsModalOpen(false);
      setSubmitting(false);

      pushToast({
        tone: 'success',
        title: 'Connection Created',
        message: `Registered connection for "${formattedName}" successfully.`
      });
    }, 800);
  };

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Page Title */}
      <div>
        <p className="section-kicker">Data Quality Workspace</p>
        <h2 className="text-3xl font-semibold text-slate-900 dark:text-white mt-1">Rule Workspace</h2>
        <p className="text-sm text-slate-500 mt-2">
          Manage database connections, switch contexts, and schedule business rules with our smart natural language interface.
        </p>
      </div>

      {/* Database Connection Hub */}
      <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/30 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-200">Database Connection Hub</h3>
            <p className="text-xs text-slate-400 mt-0.5">Switch active database or disconnect connectors.</p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            className="secondary-button text-xs font-semibold flex items-center gap-1.5 py-1.5 px-3"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Connect Database
          </button>
        </div>

        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {connections.map((c) => (
            <div
              key={c.name}
              onClick={() => handleSwitchDatabase(c.name)}
              className={`rounded-lg border p-4 cursor-pointer text-left transition-all duration-200 flex flex-col justify-between min-h-[110px] ${
                c.isActive
                  ? 'border-sky-500 bg-sky-50/20 dark:bg-sky-500/10'
                  : 'border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/20 hover:border-slate-300 dark:hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{c.type}</span>
                <span className={`inline-block h-2 w-2 rounded-full ${c.status === 'connected' ? 'bg-emerald-500' : 'bg-slate-400'}`} />
              </div>
              <div className="mt-2.5">
                <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">{c.name}</h4>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs" onClick={(e) => e.stopPropagation()}>
                {c.isActive ? (
                  <span className="font-semibold text-sky-600 dark:text-sky-400">Active</span>
                ) : (
                  <span className="text-slate-400">Inactive</span>
                )}
                {c.status === 'connected' ? (
                  <button
                    onClick={(e) => handleDisconnect(c.name, e)}
                    className="text-slate-500 hover:text-rose-500 font-semibold"
                  >
                    Disconnect
                  </button>
                ) : (
                  <button
                    onClick={(e) => handleConnect(c.name, e)}
                    className="text-sky-500 hover:text-sky-400 font-semibold"
                  >
                    Connect
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Connection Modal Overlay */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 max-w-md w-full space-y-4 shadow-xl">
            <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Connect New Database</h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreateConnection} className="space-y-4 text-xs">
              <div>
                <label className="field-label" htmlFor="new-conn-name">Connection Name</label>
                <input
                  id="new-conn-name"
                  type="text"
                  placeholder="e.g. pg_transactions"
                  value={newConnName}
                  onChange={(e) => setNewConnName(e.target.value)}
                  className="input-shell text-xs"
                  required
                />
              </div>

              <div>
                <label className="field-label" htmlFor="new-conn-type">Database Engine</label>
                <select
                  id="new-conn-type"
                  value={newConnType}
                  onChange={(e) => setNewConnType(e.target.value)}
                  className="input-shell text-xs"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                  <option value="mongodb">MongoDB</option>
                  <option value="snowflake">Snowflake</option>
                  <option value="api">API Endpoint</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="field-label" htmlFor="new-conn-host">Host Address</label>
                  <input
                    id="new-conn-host"
                    type="text"
                    placeholder="localhost"
                    className="input-shell text-xs"
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="new-conn-port">Port</label>
                  <input
                    id="new-conn-port"
                    type="text"
                    placeholder="5432"
                    className="input-shell text-xs"
                  />
                </div>
              </div>

              <div className="border-t border-slate-100 dark:border-slate-800 pt-4 flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="secondary-button text-xs py-1.5 px-3"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="primary-button text-xs py-1.5 px-3"
                >
                  {submitting ? 'Connecting...' : 'Connect'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Main Workspace (Rule Builder) */}
      <RuleBuilder />
    </div>
  );
}
