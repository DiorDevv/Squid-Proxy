import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConfigAdvisorPanel } from '@/components/analytics/ConfigAdvisorPanel'
import type { ConfigFinding } from '@/types/api'

describe('ConfigAdvisorPanel', () => {
  it('renders a localized title and description per finding code', () => {
    const findings: ConfigFinding[] = [
      { code: 'no_caching', severity: 'warning', value: 0.004, detail: null },
      { code: 'no_proxy_auth', severity: 'info', value: 0.995, detail: null },
    ]
    render(<ConfigAdvisorPanel findings={findings} />)
    expect(screen.getByText("Squid isn't caching")).toBeInTheDocument()
    expect(screen.getByText('No user attribution')).toBeInTheDocument()
    // ratio value formatted as a percentage
    expect(screen.getByText('0.4%')).toBeInTheDocument()
  })

  it('formats sensitive_allowed as a rounded count and single_domain with its detail', () => {
    const findings: ConfigFinding[] = [
      { code: 'sensitive_allowed', severity: 'warning', value: 1234, detail: null },
      { code: 'single_domain_dominant', severity: 'info', value: 0.72, detail: 'one.example' },
    ]
    render(<ConfigAdvisorPanel findings={findings} />)
    expect(screen.getByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('72% · one.example')).toBeInTheDocument()
  })
})
