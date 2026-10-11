import { describe, expect, it } from 'vitest'

import {
  clearTenantCredentials,
  loadTenantCredentials,
  saveTenantCredentials,
} from './session'

describe('tenant credential session', () => {
  it('stores and restores credentials', () => {
    const credentials = {
      tenantId: 42,
      apiKey: 'tenant-test-key',
    }

    saveTenantCredentials(credentials)

    expect(loadTenantCredentials()).toEqual(credentials)
  })

  it('clears stored credentials', () => {
    saveTenantCredentials({
      tenantId: 42,
      apiKey: 'tenant-test-key',
    })

    clearTenantCredentials()

    expect(loadTenantCredentials()).toBeNull()
  })

  it('discards malformed browser state', () => {
    sessionStorage.setItem(
      'metering-billing-tenant',
      '{"tenantId":0,"apiKey":""}',
    )

    expect(loadTenantCredentials()).toBeNull()
    expect(
      sessionStorage.getItem('metering-billing-tenant'),
    ).toBeNull()
  })
})