// frontend/src/components/admin/ConfirmDialog.jsx
//
// Confirmation dialog for Admin actions (Milestone M3B-2). Render it only while it is open. It is modal:
// focus starts on Cancel, Tab and Shift+Tab stay inside, the page behind does not scroll, and Escape or a
// click on the backdrop cancels. While the action is running, both buttons are disabled and the dialog
// cannot be dismissed. Focus returns to the element that opened it.
import { useEffect, useId, useRef } from 'react';

const CONFIRM_TONES = {
  danger: 'bg-red-600 hover:bg-red-700 focus-visible:outline-red-600',
  primary: 'bg-blue-600 hover:bg-blue-700 focus-visible:outline-blue-600',
};

const ConfirmDialog = ({ title, message, confirmLabel, pendingLabel, tone = 'primary', pending = false, onConfirm, onCancel }) => {
  const titleId = useId();
  const messageId = useId();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const latest = useRef({ pending, onCancel });

  useEffect(() => {
    latest.current = { pending, onCancel };
  });

  useEffect(() => {
    const opener = document.activeElement;
    cancelRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        if (!latest.current.pending) latest.current.onCancel();
        return;
      }
      if (event.key !== 'Tab') return;
      const buttons = [...(dialogRef.current?.querySelectorAll('button:not([disabled])') ?? [])];
      if (buttons.length === 0) {
        event.preventDefault();
        return;
      }
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/60 p-4 sm:items-center"
      onClick={() => {
        if (!pending) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        aria-busy={pending}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
      >
        <h2 id={titleId} className="text-lg font-bold text-slate-900">{title}</h2>
        <p id={messageId} className="mt-2 text-sm text-slate-600">{message}</p>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer ${CONFIRM_TONES[tone] ?? CONFIRM_TONES.primary}`}
          >
            {pending && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden="true" />}
            {pending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
