import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DataTable } from '@/components/common/DataTable'
import type { ColumnDef } from '@tanstack/react-table'

interface Row {
  id: number
  name: string
}

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'name', header: 'Name' },
]

describe('DataTable', () => {
  it('shows the empty state when there is genuinely no data', () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        total={0}
        limit={10}
        offset={0}
        onOffsetChange={vi.fn()}
      />,
    )
    expect(screen.getByText(/no events recorded/i)).toBeInTheDocument()
  })

  // Regression coverage for the "false empty state" fix: a rolling relative
  // range can shrink the result set out from under an already-paginated
  // view (rows age out between refetches) without any filter changing --
  // previously this rendered a dead-end empty state with no pager visible
  // to get back. It should now step itself back to the last page that
  // still has rows instead.
  it('steps back to the last valid page when the current page comes back empty', async () => {
    const onOffsetChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={[]}
        total={95}
        limit={10}
        offset={100}
        onOffsetChange={onOffsetChange}
      />,
    )

    await waitFor(() => expect(onOffsetChange).toHaveBeenCalledWith(90))
  })

  it('resets to offset 0 when the entire result set disappears', async () => {
    const onOffsetChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={[]}
        total={0}
        limit={10}
        offset={50}
        onOffsetChange={onOffsetChange}
      />,
    )

    await waitFor(() => expect(onOffsetChange).toHaveBeenCalledWith(0))
  })

  it('does not touch a valid offset that already has rows', () => {
    const onOffsetChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: 'Alice' }]}
        total={1}
        limit={10}
        offset={0}
        onOffsetChange={onOffsetChange}
      />,
    )

    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(onOffsetChange).not.toHaveBeenCalled()
  })

  it('shows a total that reached the backend count cap as "at least"', () => {
    render(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: 'Alice' }]}
        total={10_000}
        limit={50}
        offset={0}
        onOffsetChange={vi.fn()}
        totalCap={10_000}
      />,
    )

    expect(screen.getByText(/of 200\+ · 10,000\+ total/)).toBeInTheDocument()
  })

  it('shows an exact total below the cap as-is', () => {
    render(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: 'Alice' }]}
        total={120}
        limit={50}
        offset={0}
        onOffsetChange={vi.fn()}
        totalCap={10_000}
      />,
    )

    expect(screen.getByText('Page 1 of 3 · 120 total')).toBeInTheDocument()
  })
})
