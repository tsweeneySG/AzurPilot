import {describe, expect, it} from 'vitest'
import {allTaskPath, isAllPath, pageSuffix, taskConfigBase} from './allRoute'

describe('全部配置路由', () => {
  it('把 /all 当成共用编辑，而不是名为 All 的实例', () => {
    expect(isAllPath('/all')).toBe(true)
    expect(isAllPath('/all/task/Main')).toBe(true)
    expect(isAllPath('/i/All/task/Main')).toBe(false)
    expect(taskConfigBase('/all/task/Main', 'demo')).toBe('/all')
    expect(taskConfigBase('/i/demo/task/Main', 'demo')).toBe('/i/demo')
  })

  it('切走时保留普通任务页，工具页和调度器回到总览', () => {
    expect(pageSuffix('/all/task/Main')).toBe('task/Main')
    expect(pageSuffix('/all/task/SchedulerProgram')).toBe('overview')
    expect(pageSuffix('/i/demo/statistics')).toBe('statistics')
  })

  it('进入共用编辑时跳过工具页', () => {
    expect(allTaskPath('/i/demo/task/Main', () => false)).toBe('/all/task/Main')
    expect(allTaskPath('/i/demo/task/OpsiSimulator', task => task === 'OpsiSimulator')).toBe('/all/task/Alas')
  })
})
