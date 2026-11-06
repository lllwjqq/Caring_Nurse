import { useCallback, useEffect, useMemo, useState } from 'react'
import { medicationApi, reminderApi } from '../api/client'
import CheckinRow from '../components/CheckinRow'
import ConfirmDialog from '../components/ConfirmDialog'
import MedicationForm from '../components/MedicationForm'
import SafetyIssueCard from '../components/SafetyIssueCard'
import SectionCard from '../components/SectionCard'
import { useToast } from '../components/Toast'
import { useAlert } from '../context/AlertContext'
import { loadChecks, nowHHMM, saveChecks, todayDate, type CheckMap } from '../lib/checkin'
import { checkMedicationSafety } from '../lib/medicationSafety'
import type { ReminderItem } from '../lib/types'

const FREQ_LABELS: Record<string, string> = {
  qd: '每日1次',
  bid: '每日2次',
  tid: '每日3次',
  qid: '每日4次',
  q8h: '每8小时',
  qn: '睡前',
  prn: '按需',
}

function doseText(r: ReminderItem): string {
  const dose = `${r.dose ?? ''}${r.dose_unit ?? ''}`.trim()
  return dose || '按医嘱'
}

interface TodayReminder extends ReminderItem {
  checks?: Record<string, string>
}

interface DisplayIssue {
  level: string
  title: string
  why: string
  advice: string
}

/** 用药页（规格 §6.4）。 */
export default function MedicationPage() {
  const { patient } = useAlert()
  const { showToast } = useToast()

  const [today, setToday] = useState<ReminderItem[]>([])
  const [all, setAll] = useState<ReminderItem[]>([])
  const [checks, setChecks] = useState<CheckMap>(() => loadChecks())
  const [source, setSource] = useState<'server' | 'local'>('local')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [editing, setEditing] = useState<ReminderItem | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ReminderItem | null>(null)
  const [showAllIssues, setShowAllIssues] = useState(false)
  const [issues, setIssues] = useState<DisplayIssue[]>([])
  const [safetySource, setSafetySource] = useState<'server' | 'local'>('local')

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [t, a] = await Promise.all([reminderApi.today(), reminderApi.list()])
      const items = (t.data || []) as TodayReminder[]
      setToday(items)
      setAll(a.data as ReminderItem[])

      // 后端已支持打卡：优先使用服务端 checks；旧后端/离线时回退本机存储
      const serverChecks: CheckMap = {}
      let serverSupported = false
      for (const r of items) {
        if (r.checks && typeof r.checks === 'object') {
          serverSupported = true
          for (const [slot, status] of Object.entries(r.checks)) {
            if (status === 'taken' || status === 'skipped') {
              serverChecks[`${r.id}:${slot}`] = { status }
            }
          }
        }
      }
      if (serverSupported) {
        setChecks(serverChecks)
        setSource('server')
      } else {
        setChecks(loadChecks())
        setSource('local')
      }
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const slots = useMemo(() => {
    const rows: Array<{ reminder: ReminderItem; slot: string; key: string }> = []
    for (const r of today) {
      for (const s of r.times_of_day ?? []) {
        rows.push({ reminder: r, slot: s, key: `${r.id}:${s}` })
      }
    }
    return rows.sort((a, b) => a.slot.localeCompare(b.slot))
  }, [today])

  const doneCount = slots.filter((s) => checks[s.key]).length
  const pct = slots.length ? Math.round((doneCount / slots.length) * 100) : 0

  // 用药安全以后端药品库为准；后端不可用时才回退本地规则（规格 §1.3 裁决 1）
  const loadSafety = useCallback(async () => {
    try {
      const { data } = await medicationApi.getSafety()
      setIssues((data.issues || []) as DisplayIssue[])
      setSafetySource('server')
    } catch {
      setIssues(
        checkMedicationSafety({
          allergies: patient?.allergies,
          longTermMeds: patient?.medications,
          reminders: all,
        }),
      )
      setSafetySource('local')
    }
  }, [patient?.allergies, patient?.medications, all])

  useEffect(() => {
    void loadSafety()
  }, [loadSafety])

  const setCheck = async (reminder: ReminderItem, slot: string, status: 'taken' | 'skipped') => {
    const key = `${reminder.id}:${slot}`
    const next: CheckMap = {
      ...checks,
      [key]: { status, time: status === 'taken' ? nowHHMM() : undefined },
    }
    setChecks(next)
    saveChecks(next)
    try {
      await reminderApi.checkin(reminder.id, { slot, status, date: todayDate() })
      setSource('server')
    } catch {
      setSource('local')
    }
  }

  const undoCheck = async (reminder: ReminderItem, slot: string) => {
    const key = `${reminder.id}:${slot}`
    const next = { ...checks }
    delete next[key]
    setChecks(next)
    saveChecks(next)
    try {
      await reminderApi.uncheckin(reminder.id, { slot, date: todayDate() })
    } catch {
      setSource('local')
    }
  }

  const toggleActive = async (r: ReminderItem) => {
    try {
      await reminderApi.update(r.id, { active: !r.active })
      await load()
    } catch {
      showToast('操作失败，请重试')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await reminderApi.remove(deleteTarget.id)
      setDeleteTarget(null)
      await load()
      showToast('已删除该提醒')
    } catch {
      showToast('删除失败，请重试')
    }
  }

  if (loading) {
    return (
      <div className="px-5 py-8 text-center">
        <span className="t-body text-ink-soft">正在加载用药信息…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-5 py-5">
        <div className="rounded-card bg-white p-5 text-center shadow-card">
          <p className="t-body text-ink-soft">用药信息加载失败，请稍后重试</p>
          <button
            type="button"
            onClick={() => void load()}
            className="btn btn-primary mt-4"
            style={{ minHeight: 48 }}
          >
            重新加载
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 px-5 py-5">
      {issues.length > 0 && (
        <SectionCard
          title="用药安全提示"
          action={
            <button
              type="button"
              onClick={() => setShowAllIssues((v) => !v)}
              className="t-cap text-primary-deep underline"
            >
              {showAllIssues ? '收起' : '查看全部'}
            </button>
          }
        >
          <div className="space-y-3">
            {(showAllIssues ? issues : issues.slice(0, 2)).map((issue, i) => (
              <SafetyIssueCard key={i} issue={issue} />
            ))}
          </div>
          <p className="t-cap mt-3 text-ink-soft">
            {safetySource === 'server' ? '由后端药品库校验' : '后端不可用，使用本地规则兜底'}
          </p>
          <p className="t-cap mt-1 text-ink-soft">以上为规则提示，不构成医疗建议，请咨询医生或药师。</p>
        </SectionCard>
      )}

      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="t-h2">今日服药</h2>
          <span className="t-h2 text-primary-deep">
            {doneCount}/{slots.length}
          </span>
        </div>

        <div className="h-3 w-full rounded-full bg-line" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-3 rounded-full bg-level-green" style={{ width: `${pct}%` }} />
        </div>
        {/* 后端打卡可用时写云端；不可用时回退本机存储 */}
        <p className="t-cap mt-1 text-ink-soft">
          {source === 'server' ? '打卡记录已同步到云端' : '仅本机记录，换设备不会同步'}
        </p>

        <div className="mt-3 space-y-3">
          {slots.length === 0 ? (
            <p className="t-body text-ink-soft">今日暂无服药安排</p>
          ) : (
            slots.map((s) => (
              <CheckinRow
                key={s.key}
                reminder={s.reminder}
                slot={s.slot}
                entry={checks[s.key]}
                onCheck={(status) => void setCheck(s.reminder, s.slot, status)}
                onUndo={() => void undoCheck(s.reminder, s.slot)}
              />
            ))
          )}
        </div>

        {slots.length > 0 && doneCount === slots.length && (
          <p className="t-body mt-3 text-center text-level-green">今天的药都吃完啦</p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="t-h2">全部用药</h2>
          <button
            type="button"
            onClick={() => {
              setEditing(null)
              setCreating(true)
            }}
            className="t-cap text-primary-deep underline"
          >
            + 添加
          </button>
        </div>

        {all.length === 0 ? (
          <p className="t-body text-ink-soft">暂无用药，可通过处方上传或手动添加</p>
        ) : (
          <div className="space-y-3">
            {all.map((r) => (
              <div key={r.id} className="rounded-card bg-white p-4 shadow-card">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className={`t-body ${r.active ? '' : 'text-ink-soft line-through'}`}>
                      {r.medication_name}
                    </p>
                    <p className="t-cap text-ink-soft">
                      {doseText(r)} · {FREQ_LABELS[r.frequency] ?? r.frequency}
                    </p>
                  </div>
                  <span
                    className={`t-cap shrink-0 rounded-full px-2 py-0.5 ${
                      r.active ? 'bg-level-green text-white' : 'bg-mist text-ink-soft'
                    }`}
                  >
                    {r.active ? '进行中' : '已暂停'}
                  </span>
                </div>

                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(r)
                      setCreating(false)
                    }}
                    className="btn btn-ghost flex-1"
                    style={{ minHeight: 48 }}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => void toggleActive(r)}
                    className="btn btn-ghost flex-1"
                    style={{ minHeight: 48 }}
                  >
                    {r.active ? '暂停' : '恢复'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(r)}
                    className="btn btn-ghost flex-1 text-level-red"
                    style={{ minHeight: 48 }}
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {(creating || editing) && (
        <SectionCard
          title={editing ? '编辑用药' : '添加用药'}
          action={
            <button
              type="button"
              onClick={() => {
                setCreating(false)
                setEditing(null)
              }}
              className="t-cap text-ink-soft underline"
            >
              取消
            </button>
          }
        >
          <MedicationForm
            initial={editing}
            onSaved={() => {
              setCreating(false)
              setEditing(null)
              void load()
            }}
          />
        </SectionCard>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除这条用药提醒？"
        message={deleteTarget ? `「${deleteTarget.medication_name}」删除后将不再提醒。` : undefined}
        confirmLabel="删除"
        danger
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
