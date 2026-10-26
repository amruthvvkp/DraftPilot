import { type ReactNode, useEffect, useRef } from 'react'

type ConfirmDialogProps = {
  title: string
  confirmLabel: string
  children?: ReactNode
  busy?: boolean
  onCancel: () => void
  onConfirm: () => void
}

/** A modal confirmation for destructive actions; Escape or Cancel closes it. */
export default function ConfirmDialog({ title, confirmLabel, children, busy = false, onCancel, onConfirm }: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    cancelRef.current?.focus()
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onCancel])
  return <div className="modal-backdrop" role="presentation" onClick={onCancel}>
    <section className="wizard delete-dialog" role="dialog" aria-modal="true" aria-label={title} onClick={event => event.stopPropagation()}>
      <h2>{title}</h2>
      {children}
      <div className="dialog-actions">
        <button ref={cancelRef} type="button" className="button quiet" onClick={onCancel}>Cancel</button>
        <button type="button" className="button danger" disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </section>
  </div>
}
