import type { TenantCredentials } from '../api/types'

const STORAGE_KEY = 'metering-billing-tenant'

function isTenantCredentials(
  value: unknown,
): value is TenantCredentials {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const candidate = value as Partial<TenantCredentials>

  return (
    Number.isInteger(candidate.tenantId) &&
    Number(candidate.tenantId) > 0 &&
    typeof candidate.apiKey === 'string' &&
    candidate.apiKey.trim().length > 0
  )
}

export function loadTenantCredentials(): TenantCredentials | null {
  const stored = sessionStorage.getItem(STORAGE_KEY)

  if (stored === null) {
    return null
  }

  try {
    const parsed: unknown = JSON.parse(stored)

    if (isTenantCredentials(parsed)) {
      return parsed
    }
  } catch {
    // Invalid browser state is discarded below.
  }

  sessionStorage.removeItem(STORAGE_KEY)
  return null
}

export function saveTenantCredentials(
  credentials: TenantCredentials,
): void {
  sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(credentials),
  )
}

export function clearTenantCredentials(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}