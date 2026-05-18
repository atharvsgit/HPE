const toneStyles = {
  danger:
    'border-rose-400/30 bg-rose-400/10 text-rose-100 hover:border-rose-300/50 hover:bg-rose-400/20',
  primary:
    'border-cyan-400/30 bg-cyan-400/10 text-white hover:border-cyan-300/50 hover:bg-cyan-400/20',
};

export default function ConfirmationModal({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'primary',
  onConfirm,
  onClose,
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-md">
      <div className="glass-panel w-full max-w-xl animate-slide-up p-4 sm:p-6">
        <p className="section-kicker">Confirmation Required</p>
        <h3 className="mt-3 text-2xl font-semibold text-white">{title}</h3>
        <p className="mt-4 text-sm leading-7 text-slate-300">{message}</p>

        <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="secondary-button w-full sm:w-auto"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`primary-button w-full sm:w-auto ${toneStyles[tone] || toneStyles.primary}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
