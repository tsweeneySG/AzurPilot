/**
 * @fileoverview 通用配置参数项输入控件（支持文本、数值、选择与开关）。
 */

import { Checkbox, PasswordInput, Select, useDraftInput } from './FormControls'
import { Input } from './ui/input'
import { Switch } from './task-ui/switch'
import type { Value } from '../api/types'
import { lazy, Suspense } from 'react'
import { AutoTextarea } from './AutoTextarea'
import { useApp } from '../app/context'
import { MIXED_SENTINEL, concreteTextDraft, concreteValue, nextSwitch, toggleMultiselect } from '../config/commonEdit'

const YamlEditor = lazy(() => import('./YamlEditor').then(module => ({default: module.YamlEditor})))
const FilterEditor = lazy(() => import('./FilterEditor').then(module => ({default: module.FilterEditor})))

interface Props {
  id: string; value: Value; onChange: (value: Value) => void; type?: string
  options?: Value[]; disabled?: boolean; label: string; mode?: string; translateOption?: (value: Value) => string
  preserveText?: boolean; invalid?: boolean; resubmitOnEdit?: boolean
  /** 各配置取值不一致。提交只发生在用户给出具体值之后。 */
  mixed?: boolean
  /** 多选里只出现在部分配置中的选项。 */
  mixedOptions?: Value[]
}

/**
 * 配置参数的通用输入控件：按 `type` / `mode` 与值的形状分派到文本、数值、时间、
 * 下拉、多选、开关、YAML 或筛选器编辑器；aria 属性统一由内部 accessibility 注入。
 *
 * @param type 参数类型标记（datetime/yaml/multiselect/checkbox/bool/textarea/number/password/filter/task_priority 等）。
 * @param mode 渲染模式：text 强制按文本框处理，yaml/filter 强制用对应编辑器。
 * @param preserveText 时间字段保持原始字符串展示，不做 datetime-local 的格式互转。
 * @param resubmitOnEdit 失焦时编辑过就提交，即使值没变（目前只有 TaskConfig 的心情上限类字段使用）。
 */
export function FieldInput({
  id,
  value,
  onChange,
  type,
  options,
  disabled,
  label,
  mode,
  translateOption,
  preserveText,
  invalid,
  resubmitOnEdit,
  mixed,
  mixedOptions,
}: Props) {
  const {ui} = useApp()
  const accessibility = {
    'aria-label': label,
    'aria-invalid': invalid || undefined,
    'aria-describedby': invalid ? `${id}-status` : undefined,
  }

  // 只读时间沿用旧界面的原始文本，保留秒、小数秒和历史格式。
  if (type === 'datetime' && disabled) {
    return <Input id={id} aria-label={label} readOnly value={String(value ?? '').replace('T', ' ')}/>
  }

  if (mode === 'yaml' || type === 'yaml') {
    return (
      <Suspense fallback={<div role="status">{ui('field.loadingEditor')}</div>}>
        <YamlEditor id={id} value={String(value ?? '')} onChange={onChange} disabled={disabled} label={label} invalid={invalid} />
      </Suspense>
    )
  }

  if (type === 'multiselect') {
    return (
      <div className="multi-options" id={id} role="group" {...accessibility}>
        {options?.map(option => {
          const selected = Array.isArray(value) ? value : []
          const partial = mixedOptions ?? []
          const indeterminate = Boolean(mixed && partial.includes(option as never))
          const checked = selected.includes(option as never)
          return (
            <Checkbox
              key={JSON.stringify(option)}
              checked={checked && !indeterminate}
              indeterminate={indeterminate}
              disabled={disabled}
              onChange={() => onChange(toggleMultiselect(selected, indeterminate ? partial : [], option))}
            >
              {translateOption?.(option) ?? String(option)}
            </Checkbox>
          )
        })}
      </div>
    )
  }

  if (type === 'checkbox' || type === 'bool' || typeof value === 'boolean') {
    return (
      <Switch
        id={id}
        checked={mixed ? false : !!value}
        disabled={disabled}
        {...accessibility}
        aria-checked={mixed ? 'mixed' : undefined}
        data-mixed={mixed ? '' : undefined}
        onCheckedChange={next => onChange(mixed ? nextSwitch(true, !!value) : next)}
      />
    )
  }

  if (options?.length) {
    return (
      <Select
        {...accessibility}
        id={id}
        value={mixed ? JSON.stringify(MIXED_SENTINEL) : JSON.stringify(value)}
        disabled={disabled}
        onChange={event => {
          const next = JSON.parse(event.target.value) as Value
          if (concreteValue(next) === undefined) return
          onChange(next)
        }}
      >
        {mixed && <option value={JSON.stringify(MIXED_SENTINEL)}>{ui('common.mixed')}</option>}
        {!mixed && !options.some(option => option === value) && (
          <option value={JSON.stringify(value)}>{String(value ?? ui('common.notSet'))}</option>
        )}
        {options.map(option => (
          <option value={JSON.stringify(option)} key={JSON.stringify(option)}>
            {translateOption?.(option) ?? String(option)}
          </option>
        ))}
      </Select>
    )
  }

  // 未显式标注类型的筛选字段靠启发式兜底：id 以 filter/priority/order 结尾，或值里带 > 类比较符。
  const isFilter =
    mode === 'filter' ||
    type === 'filter' ||
    type === 'task_priority' ||
    /(?:^|[._])\w*(?:filter|priority|order)$/i.test(id) ||
    (typeof value === 'string' && /[>＞﹥›˃ᐳ❯]/.test(value))

  if (isFilter) {
    return (
      <Suspense fallback={<AutoTextarea id={id} value={String(value ?? '')} disabled={disabled} label={label} invalid={invalid} onChange={onChange} />}>
        <FilterEditor id={id} value={String(value ?? '')} disabled={disabled} label={label} invalid={invalid} onChange={onChange} />
      </Suspense>
    )
  }

  if (type === 'textarea') {
    return <AutoTextarea id={id} value={String(value ?? '')} disabled={disabled} label={label} invalid={invalid} onChange={onChange} />
  }

  // mode=text 用于语义上允许数字或文本的字段；即使旧配置当前存的是数字也必须显示文本框。
  const isNumber = mode !== 'text' && (typeof value === 'number' || ['int', 'number', 'float'].includes(type ?? ''))
  // 可编辑时间转成 datetime-local 要的 T 分隔并截到毫秒；preserveText 字段保持原样。
  const shown = type === 'datetime' && !preserveText ? String(value ?? '').replace(' ', 'T').slice(0, 23) : value === null ? '' : String(value)
  const display = mixed ? '' : shown

  // 键入期间只改草稿，失焦或回车才提交。混合态未改动的空草稿不提交。
  const draft = useDraftInput(
    display,
    next => {
      if (concreteTextDraft(Boolean(mixed), display, next) === undefined) return
      onChange(
        preserveText
          ? next
          : type === 'datetime'
            // datetime-local 只给到分钟（16 字符）时补上 :00，提交值始终带秒。
            ? next.length === 16
              ? `${next.replace('T', ' ')}:00`
              : next.replace('T', ' ')
            : isNumber && next !== ''
              ? Number(next)
              : next,
      )
    },
    resubmitOnEdit,
  )

  const inputProps = {
    ...accessibility,
    id,
    disabled,
    placeholder: mixed ? ui('common.mixed') : undefined,
    inputMode: isNumber ? 'decimal' as const : undefined,
    type: type === 'password'
      ? 'password' as const
      : type === 'datetime' && !preserveText
        ? 'datetime-local' as const
        : isNumber && !preserveText
          ? 'number' as const
          : 'text' as const,
    step: type === 'datetime' ? 1 : 'any',
    autoComplete: type === 'password' ? 'new-password' : 'off',
    value: draft.value,
    onFocus: draft.onFocus,
    onChange: draft.onChange,
    onBlur: draft.onBlur,
    onKeyDown: draft.onKeyDown,
  }

  return type === 'password'
    ? <PasswordInput {...inputProps}/>
    : <Input {...inputProps}/>
}
