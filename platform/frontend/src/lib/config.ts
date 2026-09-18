/**
 * Configuration served by the API, in two parts with two different audiences.
 *
 * `/api/config` is unauthenticated and returns branding only, because the
 * sign-in page needs the organisation's name before anyone has a token. It
 * deliberately does not carry the appetite model, the role hierarchy or the
 * separation-of-duties design: how an organisation governs is not public.
 *
 * `/api/config/governance` returns the whole configured operating model and
 * requires authentication. Nothing in the UI hardcodes a taxonomy — control
 * families, risk tiers, compliance frameworks, roles and appetite bands are all
 * rendered from whatever config/governance.yml holds — so a deployment that
 * replaces the defaults gets its own vocabulary everywhere without a rebuild.
 */

import { useEffect, useState } from 'react'
import { api, getToken } from './api'

export interface Branding {
  organisation: { name: string; short_name: string; tagline: string }
}

export interface GovernanceConfig extends Branding {
  ratings: string[]
  rating_bands: { rating: string; min: number; max: number; appetite: string }[]
  acceptance_rules: Record<
    string,
    { acceptable: boolean; max_days: number; approver: string | null; max_renewals: number }
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
    data_classifications: string[]
    sensitive_classification_threshold: string
    trust_zones: { id: string; label: string; trust: number }[]
    exposure_levels: string[]
    data_types: string[]
    risk_link_types: { id: string; label: string; creates_risk: boolean }[]
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

let brandingCache: Branding | null = null
let brandingInflight: Promise<Branding> | null = null

/** Unauthenticated: the sign-in page needs the organisation name. */
export function fetchBranding(): Promise<Branding> {
  if (brandingCache) return Promise.resolve(brandingCache)
  if (!brandingInflight) {
    brandingInflight = fetch('/api/config')
      .then((r) => {
        if (!r.ok) throw new Error('config unavailable')
        return r.json() as Promise<Branding>
      })
      .then((c) => {
        brandingCache = c
        return c
      })
      .finally(() => {
        brandingInflight = null
      })
  }
  return brandingInflight
}

export function useConfig(): Branding | null {
  const [config, setConfig] = useState<Branding | null>(brandingCache)
  useEffect(() => {
    if (brandingCache) return
    let alive = true
    fetchBranding()
      .then((c) => alive && setConfig(c))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return config
}

let governanceCache: GovernanceConfig | null = null

/** Authenticated: the full operating model, for pages that render the taxonomy. */
export function useGovernance(): GovernanceConfig | null {
  const [config, setConfig] = useState<GovernanceConfig | null>(governanceCache)
  useEffect(() => {
    if (governanceCache || !getToken()) return
    let alive = true
    api
      .get<GovernanceConfig>('/config/governance')
      .then((c) => {
        governanceCache = c
        if (alive) setConfig(c)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return config
}

/** Clears cached configuration. Called on sign-out so a different deployment,
 *  or a config change, is picked up rather than served from a stale cache. */
export function clearConfigCache() {
  brandingCache = null
  governanceCache = null
}

/** Two-letter mark for the sidebar badge, derived from the configured name. */
export function orgInitials(name: string | undefined): string {
  if (!name) return 'SM'
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}
