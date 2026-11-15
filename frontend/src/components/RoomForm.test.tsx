import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
})
