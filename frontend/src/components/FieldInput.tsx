/**
 * @fileoverview 通用配置参数项输入控件（支持文本、数值、选择与开关）。
 */

import { Checkbox, PasswordInput, Select, useDraftInput } from './FormControls'
import type { Value } from '../api/types'
import { lazy, Suspense } from 'react'
import { AutoTextarea } from './AutoTextarea'
import { useApp } from '../app/context'
import { MIXED_SENTINEL, concreteTextDraft, concreteValue, nextSwitch, toggleMultiselect } from '../config/commonEdit'

const YamlEditor = lazy(() => import('./YamlEditor').then(module => ({default: module.YamlEditor})))

interface Props {
  id: string; value: Value; onChange: (value: Value) => void; type?: string
  options?: Value[]; disabled?: boolean; label: string; mode?: string; translateOption?: (value: Value) => string
  preserveText?: boolean; invalid?: boolean
  /** 各配置取值不一致。提交只发生在用户给出具体值之后。 */
  mixed?: boolean
  /** 多选里只出现在部分配置中的选项。 */
  mixedOptions?: Value[]
}
export function FieldInput({id, value, onChange, type, options, disabled, label, mode, translateOption, preserveText, invalid, mixed, mixedOptions}: Props) {
  const {ui} = useApp()
  const accessibility = {'aria-label': label, 'aria-invalid': invalid || undefined, 'aria-describedby': invalid ? `${id}-status` : undefined}
  // 只读时间沿用旧界面的原始文本，保留秒、小数秒和历史格式。
  if (type === 'datetime' && disabled) return <input id={id} aria-label={label} readOnly value={String(value ?? '').replace('T', ' ')} />
  if (mode === 'yaml' || type === 'yaml') return <Suspense fallback={<div role="status">{ui('field.loadingEditor')}</div>}><YamlEditor id={id} value={String(value ?? '')} onChange={onChange} disabled={disabled} label={label} invalid={invalid}/></Suspense>
  if (type === 'multiselect') return <div className="multi-options" id={id} role="group" {...accessibility}>{options?.map(option => {
    const selected = Array.isArray(value) ? value : []
    const partial = mixedOptions ?? []
    const checked = selected.includes(option as never)
    const indeterminate = mixed && partial.includes(option as never)
    return <Checkbox key={JSON.stringify(option)} checked={checked && !indeterminate} indeterminate={indeterminate} disabled={disabled} onChange={() => onChange(toggleMultiselect(selected, indeterminate ? partial : [], option))}>{translateOption?.(option) ?? String(option)}</Checkbox>
  })}</div>
  if (type === 'checkbox' || type === 'bool' || typeof value === 'boolean') {
    return <button id={id} type="button" role="switch" {...accessibility} aria-checked={mixed ? 'mixed' : !!value} disabled={disabled}
      className={`toggle ${mixed ? 'mixed' : value ? 'on' : ''}`} onClick={() => onChange(nextSwitch(Boolean(mixed), !!value))}><span /></button>
  }
  if (options?.length) {
    const selectValue = mixed ? JSON.stringify(MIXED_SENTINEL) : JSON.stringify(value)
    return <Select {...accessibility} id={id} value={selectValue} disabled={disabled} onChange={event => {
      const next = JSON.parse(event.target.value) as Value
      if (concreteValue(next) === undefined) return
      onChange(next)
    }}>
      {mixed && <option value={JSON.stringify(MIXED_SENTINEL)}>{ui('common.mixed')}</option>}
      {!mixed && !options.some(option => option === value) && <option value={JSON.stringify(value)}>{String(value ?? ui('common.notSet'))}</option>}
      {options.map(option => <option value={JSON.stringify(option)} key={JSON.stringify(option)}>{translateOption?.(option) ?? String(option)}</option>)}
    </Select>
  }
  if (type === 'textarea' || type === 'task_priority') return <AutoTextarea id={id} value={String(value ?? '')} disabled={disabled} label={label} invalid={invalid} onChange={onChange}/>
  // mode=text 用于语义上允许数字或文本的字段；即使旧配置当前存的是数字也必须显示文本框。
  const isNumber = mode !== 'text' && (typeof value === 'number' || ['int', 'number', 'float'].includes(type ?? ''))
  const Input = type === 'password' ? PasswordInput : 'input'
  const display = mixed ? '' : type === 'datetime' && !preserveText ? String(value ?? '').replace(' ', 'T').slice(0, 23) : value === null ? '' : String(value)
  /* 键入期间只改草稿，失焦或回车才提交。混合态未改动的空草稿不提交。 */
  const draft = useDraftInput(display, next => {
    if (concreteTextDraft(Boolean(mixed), display, next) === undefined) return
    onChange(preserveText ? next : type === 'datetime' ? (next.length === 16 ? `${next.replace('T', ' ')}:00` : next.replace('T', ' ')) : isNumber && next !== '' ? Number(next) : next)
  })
  return <Input {...accessibility} id={id} disabled={disabled} placeholder={mixed ? ui('common.mixed') : undefined}
    inputMode={isNumber ? 'decimal' : undefined}
    type={type === 'password' ? 'password' : type === 'datetime' && !preserveText ? 'datetime-local' : isNumber && !preserveText ? 'number' : 'text'}
    step={type === 'datetime' ? 1 : 'any'} autoComplete={type === 'password' ? 'new-password' : 'off'}
    value={draft.value} onFocus={draft.onFocus} onChange={draft.onChange} onBlur={draft.onBlur} onKeyDown={draft.onKeyDown}/>
}
