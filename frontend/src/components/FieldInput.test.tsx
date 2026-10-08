import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { AppContext, type AppContextValue } from '../app/context'
import { translateUi } from '../i18n'
import { FieldInput } from './FieldInput'

describe('配置输入控件', () => {
  it('显式文本模式不会被旧的数字配置值改回数字输入框', () => {
    const html = renderToStaticMarkup(
      <AppContext.Provider value={{ui: (key, params) => translateUi('zh-CN', key, params)} as AppContextValue}>
        <FieldInput id="target-zone" label="指定海域" type="input" mode="text" value={12} onChange={vi.fn()}/>
      </AppContext.Provider>,
    )

    expect(html).toContain('type="text"')
    expect(html).not.toContain('inputMode="decimal"')
  })

  it('混合开关、选择和数字框只展示混合，不把哨兵写进控件值', () => {
    const ui = (key: string) => key === 'common.mixed' ? '混合' : key
    const wrap = (node: ReactNode) => renderToStaticMarkup(
      <AppContext.Provider value={{ui} as AppContextValue}>{node}</AppContext.Provider>,
    )
    const onChange = vi.fn()
    const switchHtml = wrap(<FieldInput id="enable" label="启用" type="checkbox" value={false} mixed onChange={onChange}/>)
    expect(switchHtml).toContain('aria-checked="mixed"')
    const selectHtml = wrap(<FieldInput id="stage" label="关卡" type="select" value="12-4" options={['12-4', '7-2']} mixed onChange={onChange}/>)
    expect(selectHtml).toContain('混合')
    expect(selectHtml).toContain('__ALAS_MIXED__')
    const numberHtml = wrap(<FieldInput id="amount" label="数量" type="number" value={12} mixed onChange={onChange}/>)
    expect(numberHtml).toContain('placeholder="混合"')
    expect(numberHtml).toContain('value=""')
    expect(onChange).not.toHaveBeenCalled()
  })
})
