/**
 * @fileoverview 共用配置编辑的混合态提交规则。
 *
 * 控件可以显示「混合」，但只有用户给出具体值才写入全部配置。
 */

import type { Value } from '../api/types'

/** 与后端 module/webui/common_editor.py 的 MIXED_SENTINEL 一致。 */
export const MIXED_SENTINEL = '__ALAS_MIXED__'

export function sameValue(left: Value, right: Value) {
  return JSON.stringify(left) === JSON.stringify(right)
}

/** 混合态的选择或文本若仍是哨兵，则不算一次提交。 */
export function concreteValue(next: Value): Value | undefined {
  if (next === MIXED_SENTINEL) return undefined
  return next
}

/**
 * 混合文本的空草稿不是清空：数字字段若把空串交给 prepareValue，会回落成默认值并写进全部配置。
 * shown 是控件当前展示的文本，未改动时与草稿相同。
 */
export function concreteTextDraft(mixed: boolean, shown: string, draft: string): string | undefined {
  if (mixed && draft === shown) return undefined
  return draft
}

/** 混合开关的第一次点击写成开；之后按普通开关翻转。 */
export function nextSwitch(mixed: boolean, value: boolean) {
  return mixed ? true : !value
}

/** 多选点击产出一份具体数组：未选和混合项变成选中，已选变成取消。 */
export function toggleMultiselect(checked: Value[], indeterminate: Value[], option: Value): Value[] {
  const hit = (item: Value) => sameValue(item, option)
  if (indeterminate.some(hit) || !checked.some(hit)) return [...checked, option]
  return checked.filter(item => !hit(item))
}
