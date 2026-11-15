import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RoomFormView } from './RoomForm'
import { SAMPLE_FORM, validate, type RoomForm } from '../room'

afterEach(cleanup)

function setup(form: RoomForm = SAMPLE_FORM, busy = false) {
  const onChange = vi.fn()
  const onSubmit = vi.fn()
  const onReset = vi.fn()
  render(<RoomFormView form={form} errors={validate(form)} busy={busy} onChange={onChange} onSubmit={onSubmit} onReset={onReset} />)
  return { onChange, onSubmit, onReset }
}

describe('RoomFormView', () => {
  it('shows the sample room, with a visible label for every field', () => {
    setup()
    expect(screen.getByLabelText('Width (in)')).toHaveValue(144)
    expect(screen.getByLabelText('Depth (in)')).toHaveValue(192)
    expect(screen.getByLabelText(/Door position/)).toHaveValue(56)
    expect(screen.getByLabelText(/Window position/)).toHaveValue(48)
    expect(screen.getByRole('checkbox', { name: /Closet/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'top', checked: true })).toBeInTheDocument()
  })

  it('groups the wall choices with a legend', () => {
    setup()
    expect(screen.getByRole('group', { name: 'Door wall' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Window wall' })).toBeInTheDocument()
  })

  it('reports number edits, leaving the rest of the form alone', () => {
    const { onChange } = setup()
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '120' } })
    expect(onChange).toHaveBeenCalledWith({ ...SAMPLE_FORM, width: 120 })
  })

  it('reports a cleared field as not-a-number so it can be flagged', () => {
    const { onChange } = setup()
    fireEvent.change(screen.getByLabelText('Depth (in)'), { target: { value: '' } })
    expect(onChange.mock.calls[0][0].depth).toBeNaN()
  })

  it('reports wall and closet choices', () => {
    const { onChange } = setup()
    fireEvent.click(screen.getAllByRole('radio', { name: 'left' })[0])
    expect(onChange).toHaveBeenLastCalledWith({ ...SAMPLE_FORM, doorWall: 'left' })
    fireEvent.click(screen.getAllByRole('radio', { name: 'right' })[1])
    expect(onChange).toHaveBeenLastCalledWith({ ...SAMPLE_FORM, windowWall: 'right' })
    fireEvent.click(screen.getByRole('checkbox', { name: /Closet/ }))
    expect(onChange).toHaveBeenLastCalledWith({ ...SAMPLE_FORM, closet: false })
  })

  it('submits a valid room', () => {
    const { onSubmit } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Find furniture that fits' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('shows the problem and blocks submit for a room that cannot work', () => {
    const { onSubmit } = setup({ ...SAMPLE_FORM, doorOffset: 130 })
    expect(screen.getByRole('alert')).toHaveTextContent(/door does not fit/)
    const button = screen.getByRole('button', { name: 'Find furniture that fits' })
    expect(button).toBeDisabled()
    fireEvent.submit(button.closest('form')!)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not submit twice while a search is running', () => {
    const { onSubmit } = setup(SAMPLE_FORM, true)
    const button = screen.getByRole('button', { name: 'Searching…' })
    expect(button).toBeDisabled()
    fireEvent.submit(button.closest('form')!)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('resets to the sample room', () => {
    const { onReset } = setup({ ...SAMPLE_FORM, width: 100 })
    fireEvent.click(screen.getByRole('button', { name: 'Use the sample room' }))
    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('picks an example: fills the whole form from the preset', () => {
    const { onChange } = setup()
    fireEvent.change(screen.getByLabelText('Start from an example'), { target: { value: 'small' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ width: 120, depth: 168, needs: ['nightstand', 'dresser'] }))
  })

  it('shows the matching example and its blurb, or "Custom room" once the form is changed', () => {
    setup()
    expect(screen.getByLabelText('Start from an example')).toHaveValue('starter')
    expect(screen.getByText(/12 x 16 ft with a closet/)).toBeInTheDocument()
    cleanup()
    setup({ ...SAMPLE_FORM, width: 150 })
    expect(screen.getByLabelText('Start from an example')).toHaveValue('')
  })

  it('has a "What do you need?" group: the bed is always on, the others toggle', () => {
    const { onChange } = setup()
    const group = screen.getByRole('group', { name: 'What do you need?' })
    expect(within(group).getByRole('checkbox', { name: /Bed/ })).toBeDisabled()
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Dresser' }))
    expect(onChange).toHaveBeenCalledWith({ ...SAMPLE_FORM, needs: ['nightstand', 'desk'] })
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Desk and chair' }))
    expect(onChange).toHaveBeenLastCalledWith({ ...SAMPLE_FORM, needs: ['nightstand', 'dresser'] })
  })

  it('turning a need back on keeps the canonical order', () => {
    const { onChange } = setup({ ...SAMPLE_FORM, needs: ['desk'] })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Nightstand' }))
    expect(onChange).toHaveBeenCalledWith({ ...SAMPLE_FORM, needs: ['nightstand', 'desk'] })
  })

  it('has a bed size choice, auto by default', () => {
    const { onChange } = setup()
    const select = screen.getByLabelText('Bed size')
    expect(select).toHaveValue('auto')
    fireEvent.change(select, { target: { value: 'queen' } })
    expect(onChange).toHaveBeenCalledWith({ ...SAMPLE_FORM, bedSize: 'queen' })
  })
})
