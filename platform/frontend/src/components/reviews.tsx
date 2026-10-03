/** Effectiveness reviews for one control (codified-rules 10.3, REV-1 to REV-5).
 *
 * A review opens when a deployment is repaired and closes on a passing retest.
 * Until it closes, nothing that depends on the control is told it works again,
 * so an open review is the reason a risk is still at its inherent score. */

import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'
import { formatDate } from '../lib/format'
import { GatePanel } from './governance'
import { Badge, Card, useToast } from './ui'

export function EffectivenessReviews({
  objectiveId,
  onChanged,
}: {
  objectiveId: string
  onChanged?: () => void
}) {
  const [reviews, setReviews] = useState<any[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const { push } = useToast()

  const load = useCallback(
    () =>
      api
        .get<any[]>(`/control-reviews?objective_id=${objectiveId}`)
        .then(setReviews)
        .catch(() => setReviews([])),
    [objectiveId],
  )

  useEffect(() => {
    load()
  }, [load])

  if (!reviews || reviews.length === 0) return null

  const fire = async (review: any, target: string, reason?: string) => {
    setBusy(target)
    try {
      await api.post(`/control-reviews/${review.id}/transition`, { target, reason })
      push({
        kind: 'ok',
        title: target === 'Completed' ? review.reference + ' completed' : review.reference + ' cancelled',
        body:
          target === 'Completed'
            ? 'Linked risks, threat scenarios and requirements have been prompted to re-assess.'
            : undefined,
      })
      await load()
      onChanged?.()
    } catch (err) {
      if (err instanceof ApiError) push({ kind: 'error', title: 'Refused', body: err.message, rule: err.rule })
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card
      title="Effectiveness reviews"
      subtitle="Opened when a deployment is repaired. Closed only by a passing retest, which is what tells the risks, threat scenarios and requirements that depend on this control to re-assess (REV-1 to REV-3)."
    >
      <ul className="space-y-3">
        {reviews.map((r) => (
          <li key={r.id} className="rounded-lg border p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <span className="mono text-ink-faint">{r.reference}</span>
              <span className="text-ink">
                {r.deployment_reference} on {r.asset}
              </span>
              <Badge value={r.lifecycle_state} />
              {r.overdue && (
                <span className="chip border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-300">
                  overdue{r.escalated_at ? ', escalated' : ''}
                </span>
              )}
              <span className="ml-auto text-xs text-ink-muted">
                opened {formatDate(r.opened_at)} · due {formatDate(r.due_date)}
              </span>
            </div>
            {r.lifecycle_state === 'Open' ? (
              <GatePanel gates={r.gates} onFire={(t, reason) => fire(r, t, reason)} busy={busy} />
            ) : (
              <p className="text-xs text-ink-muted">
                {r.lifecycle_state === 'Completed'
                  ? 'Completed ' + formatDate(r.completed_at) + ' on a passing retest.'
                  : 'Cancelled: ' + (r.cancellation_reason ?? '')}
              </p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}
