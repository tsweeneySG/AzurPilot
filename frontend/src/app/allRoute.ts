/**
 * @fileoverview 「全部配置」路由与实例页之间的路径换算。
 */

import { SCHEDULER_EDITOR } from '../components/taskNavItems'

export function isAllPath(pathname: string) {
  return pathname === '/all' || pathname.startsWith('/all/')
}

/** 任务链接的前缀：共用编辑走 /all，单个实例走 /i/:name。 */
export function taskConfigBase(pathname: string, instance?: string) {
  if (isAllPath(pathname)) return '/all'
  return instance ? `/i/${instance}` : ''
}

/** 切到另一个实例时保留的页型。共用编辑里的调度器页没有对应的单实例页型以外的入口，回到总览。 */
export function pageSuffix(pathname: string) {
  const instancePage = pathname.match(/^\/i\/[^/]+\/(.*)$/)
  if (instancePage) return instancePage[1] || 'overview'
  const allPage = pathname.match(/^\/all\/(.*)$/)
  const rest = allPage?.[1]
  if (rest?.startsWith('task/') && rest !== `task/${SCHEDULER_EDITOR}`) return rest
  return 'overview'
}

/** 进入共用编辑时沿用当前任务；工具页和调度器编辑没有共用形态，回到系统设置。 */
export function allTaskPath(pathname: string, isTool: (task: string) => boolean) {
  const task = pathname.match(/\/task\/([^/]+)/)?.[1]
  if (task && task !== SCHEDULER_EDITOR && !isTool(task)) return `/all/task/${task}`
  return '/all/task/Alas'
}
