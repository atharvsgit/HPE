const toneClasses = {
  success: 'status-badge-success',
  pending: 'status-badge-pending',
  error: 'status-badge-error',
};

export default function StatusBadge({
  tone = 'pending',
  children,
  className = '',
}) {
  return (
    <span className={`status-badge ${toneClasses[tone] || toneClasses.pending} ${className}`}>
      <span className="h-2 w-2 rounded-full bg-current opacity-80" />
      <span>{children}</span>
    </span>
  );
}
