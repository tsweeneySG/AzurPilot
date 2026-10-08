import {describe, expect, it} from 'vitest'
import {MIXED_SENTINEL, concreteTextDraft, concreteValue, nextSwitch, toggleMultiselect} from './commonEdit'

describe('共用编辑的混合态', () => {
  it('开关和选择不会把混合哨兵交给保存队列', () => {
    expect(nextSwitch(true, false)).toBe(true)
    expect(concreteValue(MIXED_SENTINEL)).toBeUndefined()
    expect(concreteValue('12-4')).toBe('12-4')
  })

  it('未改动的混合数字草稿不会提交', () => {
    expect(concreteTextDraft(true, '', '')).toBeUndefined()
    expect(concreteTextDraft(true, '', '3')).toBe('3')
    expect(concreteTextDraft(false, '', '')).toBe('')
  })

  it('多选点击写出一份具体数组', () => {
    expect(toggleMultiselect(['a'], ['b'], 'b')).toEqual(['a', 'b'])
    expect(toggleMultiselect(['a', 'b'], [], 'a')).toEqual(['b'])
  })
})
