/**
 * @fileoverview 存储项字段的内容展示与清空组件。
 */

import { Trash2 } from 'lucide-react'
import type { Value } from '../api/types'
import { useApp } from '../app/context'

export function StorageField({value, disabled, onClear, hideClear = false}: {value: Value; disabled: boolean; onClear: () => void; hideClear?: boolean}) {
  const {ui} = useApp()
  return <div className="storage-field"><pre aria-label={ui('storage.content')}>{JSON.stringify(value, null, 2)}</pre>{!hideClear && <button type="button" className="button danger subtle" disabled={disabled} onClick={onClear}><Trash2 size={15}/>{ui('storage.clear')}</button>}</div>
}
