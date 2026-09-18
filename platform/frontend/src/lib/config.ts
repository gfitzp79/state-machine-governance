/**
 * The organisation's configured governance model, fetched once from
 * /api/config and shared across the app.
 *
 * Nothing in the UI hardcodes a taxonomy. Control families, risk tiers,
 * compliance frameworks, roles and appetite bands are all rendered from
 * whatever config/governance.yml holds, so a deployment that replaces the
 * defaults gets its own vocabulary everywhere without a rebuild.
 */

import { useEffect, useState } from 'react'

export interface GovernanceConfig {
  organisation: { name: string; short_name: string; tagline: string }
  ratings: string[]
  rating_bands: { rating: string; min: number; max: number; appetite: string }[]
  acceptance_rules: Record<
    string,
    { acceptable: boolean; max_days: number; approver: string | null }
  >
  review_cadence_days: Record<string, number>
  ce_ratings: string[]
  ce_likelihood_reduction: Record<string, number>
  ce_expiry_months: Record<string, number>
  ce_degradation_sla_days: Record<string, number>
  treatment_strategies: string[]
  risk: {
    tiers: { id: string; label: string; description: string }[]
    intake_sources: string[]
  }
  controls: {
    families: string[]
    types: string[]
    test_frequencies: string[]
    asset_tiers: string[]
  }
  policy: {
    types: string[]
    review_cycles: string[]
    compliance_frameworks: string[]
    annual_audit_frameworks: string[]
    exception_max_days: number
    exception_extended_max_days: number
  }
  threat: {
    local_acceptance_max_days: number
    minimum_promotable_severity: string
    severities: string[]
  }
  roles: {
    definitions: { id: string; level: number; description: string }[]
    levels: Record<string, number>
    seniority_ladder: string[]
    ownership_by_severity: Record<string, string>
  }
  treatment: {
    loe_bands: string[]
    checkin_frequencies: string[]
    checkin_statuses: string[]
  }
  escalation: Record<string, number>
}

let cached: GovernanceConfig | null = null
let inflight: Promise<GovernanceConfig> | null = null

/** Unauthenticated: the sign-in page needs the organisation name too. */
export function fetchConfig(): Promise<GovernanceConfig> {
  if (cached) return Promise.resolve(cached)
  if (!inflight) {
    inflight = fetch('/api/config')
      .then((r) => {
        if (!r.ok) throw new Error('config unavailable')
        return r.json() as Promise<GovernanceConfig>
      })
      .then((c) => {
        cached = c
        return c
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export function useConfig(): GovernanceConfig | null {
  const [config, setConfig] = useState<GovernanceConfig | null>(cached)
  useEffect(() => {
    if (cached) return
    let alive = true
    fetchConfig()
      .then((c) => alive && setConfig(c))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return config
}

/** Two-letter mark for the sidebar badge, derived from the configured name. */
export function orgInitials(name: string | undefined): string {
  if (!name) return 'SM'
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}
