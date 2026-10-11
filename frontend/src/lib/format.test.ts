import { describe, expect, it } from 'vitest'

import {
  formatDate,
  formatMicrousd,
  formatNumber,
  formatPlan,
  formatStatus,
} from './format'

describe('billing formatters', () => {
  it('converts micro-USD to dollars', () => {
    expect(formatMicrousd(7_376_990)).toBe('$7.38')
  })

  it('formats quantities with separators', () => {
    expect(formatNumber(5_000_000)).toBe('5,000,000')
  })

  it('keeps UTC billing dates on the correct day', () => {
    expect(formatDate('2026-10-01T00:00:00Z')).toBe(
      'Oct 1, 2026',
    )
  })

  it('formats plan and status labels', () => {
    expect(formatPlan('pro')).toBe('Pro')
    expect(formatStatus('past_due')).toBe('Past Due')
  })
})