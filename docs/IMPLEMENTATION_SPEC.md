# 贴心小护士 · 前端实施规格书（完整版）

> 读者：编码模型 / 前端工程师。
> 范围：5 个 tab 的全部页面 + 设置等全屏子页。
> 本文只描述「做什么、长什么样、接哪个接口、怎么验收、禁止什么」，不提供完整实现代码。

---

## 0. 给编码模型的启动提示词

把下面这段连同本文件一起交给编码模型：

```text
你是资深前端工程师。请严格按 docs/IMPLEMENTATION_SPEC.md 实现「贴心小护士」前端重构。

开工前必须先读：
- 本文件全部
- frontend/src/App.tsx、components/Layout.tsx、pages/ChatPage.tsx
- frontend/src/api/client.ts、lib/audio.ts、constants/healthRecords.ts
- frontend/tailwind.config.js、src/index.css、vite.config.ts

实施顺序（每完成一步跑一次 npm run build，通过后再进入下一步）：
1) 设计 token + App Shell（TabBar / 语音球 / SOS / 全局状态）
2) 问诊页
3) 监测页
4) 录入页 + OCR 确认子页
5) 用药页（今日打卡 / 全部用药 / 安全提示）
6) 我的页 + 设置、健康档案、管理方案、预警记录子页
7) 全局自检：逐条过第 9 节验收清单、第 10 节反模式清单

硬性约束：
1. 不新增 npm 依赖；尽量不改后端；如需改后端，只允许第 1.3 节列出的缺口，并先说明。
2. 所有网络请求只走 src/api/client.ts，禁止组件内直接 fetch。
3. 颜色/字号只允许用 Tailwind token 或 CSS 变量，禁止散落硬编码。
4. 触控目标 ≥48×48，正文 ≥18px，标题 ≥20px。
5. 规格未覆盖的细节，选最小实现，并在代码注释标 SPEC-GAP。
6. 交付时给出：改动文件清单 + 每个文件做了什么 + 自检结果（逐条打勾）。
```

---

## 1. 范围与总原则

### 1.1 交付范围

| 层 | 内容 |
|---|---|
| App Shell | 页头、5 tab 底部导航、语音悬浮球、SOS、全局 Toast、安全区与层级 |
| 问诊 | 对话流、预警气泡、快捷问句、文字/语音输入、逐条朗读、语音导入二次确认 |
| 监测 | 风险等级卡、今日指标、健康趋势、预警列表 |
| 录入 | 生理指标录入、药品录入、报告上传 + OCR 识别确认子页 |
| 用药 | 今日服药打卡、全部用药管理、用药安全提示 |
| 我的 | 账号卡、健康档案、管理方案、预警记录、设置、退出登录 |
| 设置 | 语音、显示（大字/高对比）、提醒、安全（联系人/改密）、关于 |

### 1.2 明确不做

- 不做独立的知识图谱页、预警中心页、管理方案主页（已并入上述页面）；随访功能整体移除（以 `AGENT_DESIGN.md` 为准）。
- 不做多角色（医生/管理员）界面。
- 不做离线缓存、PWA、推送订阅（浏览器限制，见 1.3）。
- 不做深色模式（只做高对比模式）。

### 1.3 后端能力缺口（必须先看）

以下功能在现有后端**没有对应字段或接口**，实现方必须按下面处理：

| 缺口 | 现状 | 处理方式 |
|---|---|---|
| **服药打卡** | `MedicationReminder` 无打卡字段，无日志表 | **补后端（必需）**：`MedicationLog` 表 + `POST /api/reminders/{id}/checkin`（见 `AGENT_IMPLEMENTATION_SPEC.md` §10.5）；前端不再用 `localStorage` 兜底 |
| **修改密码** | `/api/auth/*` 无改密接口 | 推荐补 `POST /api/auth/change-password`（附录 A）；否则设置项显示「暂未开放」 |
| **意见反馈** | 无接口 | 用 `mailto:` 链接兜底 |
| **测量提醒** | 无后端调度 | 仅作为本地偏好保存；不承诺后台推送，文案写明「打开 App 时提醒」 |
| **用药安全提示** | 后端原无相互作用/过敏检查 | **以后端为准**：新增 `DrugSafetyService` + `GET /api/medication/safety`；前端仅渲染后端返回的 `issues`，`medicationSafety.ts` 降级为兜底（见 `AGENT_IMPLEMENTATION_SPEC.md` §1.3） |
| **WS 鉴权** | `/api/ws/alerts/{patient_id}` 无 token 校验 | 本期照用，代码标 `SECURITY-TODO`；附录 A 给升级契约 |
| **语音结构化抽取** | 后端原只有 ASR | **以后端为准**：新增 `POST /api/agents/extract`（只抽取、不写库）；前端 `parseHealthParams.ts` 降级为接口失败兜底（见 `AGENT_IMPLEMENTATION_SPEC.md` §1.3） |

> 原则：宁可降级并明确告知，也不要写死假数据或伪造接口。

---

## 2. 非功能性要求

| 项 | 要求 |
|---|---|
| 适配 | 375×667 起，内容最大宽 560 居中；平板不拉伸 |
| 安全区 | 顶部 `env(safe-area-inset-top)`、底部 `env(safe-area-inset-bottom)` 必留 |
| 触控 | 所有可点元素 ≥48×48；相邻间距 ≥8，主要操作 ≥12 |
| 字号 | 正文 18，标题 ≥20；全局最小可见文字 18（版本号除外） |
| 对比度 | 正文 ≥4.5:1；大字（≥24px 或 ≥18.66px 粗体）≥3:1 |
| 动效 | 150–200ms ease-out；响应 `prefers-reduced-motion` |
| 可访问性 | 语义化按钮、`aria-label`、`:focus-visible`、键盘可操作 |
| 缩放 | 移除 `user-scalable=no`，允许双指缩放 |
| 图表 | 坐标轴/图例文字 ≥16px 且高对比；触摸点放大 |
| 音频 | 浏览器要求用户手势后才能播放：首次点击任意按钮即解锁；被拦截时不报错，改用球脉冲 + 气泡提示 |
| 性能 | 对话流 >200 条只渲染最近 100 条 + 「加载更早」；长列表虚拟化可选 |

---

## 3. 设计 Token

### 3.1 颜色（在 `tailwind.config.js` 的 `theme.extend.colors` 追加）

保留现有 `primary/nurse/safe/warn/danger`，新增：

| token | 色值 | 用途 |
|---|---|---|
| `primary` | `#4A90D9` | 主蓝：大面积色块、图标、选中态 |
| `primary-deep` | `#3577C2` | 承载 18px 白字的按钮/链接（≈4.6:1） |
| `nurse` | `#FF6B8A` | 情感强调，少量（角标、提醒点） |
| `ink` | `#1B2A3A` | 主文字（白底 ≈14:1） |
| `ink-soft` | `#5B6B7B` | 次要文字（≈5:1） |
| `line` | `#E6EDF5` | 分隔线、边框 |
| `mist` | `#F4F7FB` | 页面底色 |
| `level-green` | `#1F7A55` | 等级·绿（白字 ≈5.3:1） |
| `level-yellow` | `#FFE08A` | 等级·黄底（配 `level-yellow-ink` ≈7.6:1） |
| `level-yellow-ink` | `#5C3D00` | 黄底文字 |
| `level-orange` | `#C2410C` | 等级·橙（白字 ≈5.2:1） |
| `level-red` | `#B42318` | 等级·红（白字 ≈6.6:1） |

**规则**：`safe/warn/danger` 仅用于图标、边框、小色块；色块上写字一律用 `level-*` 深色对。

### 3.2 字号阶（默认 / 大字模式）

在 `src/index.css` 用 CSS 变量 + `@layer components` 定义：

| 类名 | 默认 | 大字 | 用途 | 行高 | 字重 |
|---|---|---|---|---|---|
| `.t-display` | 40 | 50 | 指标大数字、风险等级 | 1.1 | 700 |
| `.t-h1` | 28 | 34 | 页面主标题 | 1.3 | 700 |
| `.t-h2` | 22 | 28 | 区块标题 | 1.4 | 700 |
| `.t-body` | 18 | 22 | 正文、气泡、按钮 | 1.6 | 500 |
| `.t-cap` | 18 | 22 | 次要说明（用 `ink-soft`，不缩小） | 1.5 | 400 |
| `.t-micro` | 16 | 20 | 仅版本号 / 参考范围脚注 | 1.4 | 400 |

切换：`document.documentElement.dataset.textSize = 'large' | 'normal'`，
持久化 `localStorage.text_size`；`main.tsx` 渲染前读取，避免闪烁。
禁止用 `text-sm/text-xs` 写正文。

### 3.3 间距 / 圆角 / 阴影

| 项 | 值 |
|---|---|
| 基准 | 4px |
| 页面内边距 | 20px |
| 卡片内边距 | 20px |
| 区块间距 | 20px |
| 卡片圆角 | 24px |
| 按钮 / 输入框圆角 | 16px（胶囊 999px） |
| 阴影 | `0 2px 8px rgba(27,42,58,0.06)` |

### 3.4 图表配色

| 用途 | 色值 |
|---|---|
| 血糖线 | `#4A90D9` |
| 血压·收缩压 | `#FF6B8A` |
| 血压·舒张压 | `#F2A65A` |
| 参考范围带 | `#4A90D9` 8% 透明度 |
| 异常点 | `#B42318` |

---

## 4. App Shell

### 4.1 结构

```
<div id="app-shell">                     ← 100dvh，flex 纵向
  <PageHeader />                         ← 固定 56px + 顶部安全区
  <main class="page-main">               ← flex-1，独立滚动
      <Outlet />
  </main>
  <TabBar />                             ← 固定底部 64px + 底部安全区
  <VoiceOrb />                           ← 全局浮动 z-30
</div>
```

- 由现有 `components/Layout.tsx` 重写；文件名保留。
- `main` 自己滚动，避免 iOS 回弹导致 fixed 元素错位。
- 内容底部预留 `calc(64px + env(safe-area-inset-bottom))`。

### 4.2 页头

| 页面 | 左 | 右 |
|---|---|---|
| 问诊 | 头像 40 + 「贴心小护士」20 + 「在线」18 | 静音 48 + SOS 88×48 |
| 其他 tab | 页面标题 22 | 静音 48 + SOS 88×48 |
| 子页 | 返回 48 + 标题 22 | 静音 48（不显示 SOS） |

- 静音按钮：喇叭开/关图标，48×48，`aria-label="静音/开启语音播报"`。
- SOS：红色胶囊，`level-red` 底白字，永远在页头，不随滚动。

### 4.3 TabBar

| 项 | 规格 |
|---|---|
| 高度 | 64px + `env(safe-area-inset-bottom)` |
| 路由 | 问诊 `/`、监测 `/monitor`、录入 `/record`、用药 `/medication`、我的 `/me` |
| 每项 | 图标 26 + 文字 18；可点区域 ≥64×64 |
| 选中态 | 浅蓝胶囊底（`primary/10`）+ `primary-deep` 加粗 + 图标变色 |
| 角标 | 问诊项右上红点，数字 ≥18px；>99 显示「99+」 |
| 无障碍 | `<nav aria-label="主导航">`，当前项 `aria-current="page"` |

### 4.4 语音悬浮球

| 项 | 规格 |
|---|---|
| 形态 | 圆形 64，`primary` 渐变 + 麦克风 28 |
| 默认位置 | 右缘 16，垂直约 58%；首次进入 1 次呼吸动画 |
| 主交互 | **按住 300ms 不动 → 录音**，松手识别；录音时球变红，球上方显示「正在聆听… 松开结束」；识别中显示「正在识别…」 |
| 手势区分 | 按下后 300ms 内位移 >16px → 视为**拖动**，跟随手指移动且不启动录音；300ms 后保持不动 → 进入录音，录音期间移动不再改变位置 |
| 事件 | `pointerdown` 记录起点并启动 300ms 计时；计时到调 `start()`；`pointerup` 调 `stop()`；`pointercancel` 丢弃；快速轻点（<300ms）不录音 |
| 位置 | 支持拖动，松手吸附最近左/右边缘；设置页「语音 → 语音球位置 → 复位」恢复默认 |
| 短按 | 按住短于 300ms 或录音短于 500ms 不送识别，释放麦克风并轻提示「按住说话；按住后移动可拖动」 |
| 边界 | y ∈ `[header 底+8, TabBar 顶−12]`；问诊页上限再抬到输入区上沿−12 |
| 结果 | 识别文本先走健康参数解析：命中 → 弹「确认卡」；未命中 → 轻提示「没太听清」；不直接入库 |
| 静音态 | 球不随播报开关变灰（避免误以为不能录音）；播报开关看页头喇叭 |
| 记忆 | `localStorage.orb_position`；设置页「语音 → 语音球位置 → 复位」 |
| 跨页 | 挂 `AppShell`，不随路由重建 |
| 主动播报 | 预警到达：脉冲 1.5s + 球上方小气泡「有 1 条提醒」+ 语音（开启时） |

### 4.5 SOS

| 项 | 规格 |
|---|---|
| 触发 | 页头红色胶囊 88×48 |
| 弹窗 | 全屏遮罩 + 居中卡片（宽 min(86vw,360)，圆角 24） |
| 内容 | 标题「需要紧急帮助吗？」+ 联系人电话 `.t-h2` + 64px 倒计时环（5→1）+ 两个 56px 按钮 |
| 按钮 | 「取消」为主（更大、靠左）；「立即拨打」为次（`level-red`） |
| 倒计时 | 归零触发 `tel:`；任一点取消 / 点遮罩 / Esc 即关闭 |
| 无联系人 | 「还没有紧急联系人」+「拨打 120」+「去设置添加」 |
| 号码解析 | `patient.emergency_contact` 取最后连续 11 位数字；不足则视为无 |

### 4.6 层级与安全区

| 层 | z-index |
|---|---|
| 页面内容 | 0 |
| 语音球 | 30 |
| TabBar | 40 |
| 页头 / SOS | 50 |
| 确认卡 / 底部面板 | 70 |
| SOS 弹窗 | 80 |
| 全局轻提示 | 90 |

**规则**：TabBar 永远高于语音球，保证导航可点；SOS 永远高于语音球。

### 4.7 全局状态

| Provider | 职责 |
|---|---|
| `AlertProvider` | 患者 id、预警列表、未读数、WS 连接与重连、已读标记 |
| `VoiceProvider` | 播报开关/音量/语速、`speak(text)`、`stop()`、当前是否在播报 |
| `SettingsProvider` | 大字模式、高对比模式、提醒开关（本地持久化） |
| `ToastProvider` | 轻提示（底部，2s，`aria-live="polite"`），**禁止用于预警** |

---

## 5. 组件清单

| 组件 | 文件 | 关键 props / 状态 | 用在哪 |
|---|---|---|---|
| `Layout` | `components/Layout.tsx` | — | 全局 |
| `PageHeader` | `components/PageHeader.tsx` | `title?`、`identity?`、`onBack?`、`showSos?` | 全部页面 |
| `TabBar` | `components/TabBar.tsx` | `unreadAlertCount` | 全局 |
| `VoiceOrb` | `components/VoiceOrb.tsx` | — | 全局 |
| `SosButton` | `components/SosButton.tsx` | `onClick` | 页头 |
| `SosDialog` | `components/SosDialog.tsx` | `open`、`contact`、`onClose` | 全局 |
| `MessageBubble` | `components/MessageBubble.tsx` | `role`、`content`、`streaming`、`onSpeak` | 问诊 |
| `AlertBubble` | `components/AlertBubble.tsx` | `alert`、`onAck`、`onSpeak` | 问诊 |
| `VoiceConfirmCard` | `components/VoiceConfirmCard.tsx` | `draft`、`onConfirm`、`onRetry` | 全局 |
| `RiskCard` | `components/RiskCard.tsx` | `level`、`copy` | 监测 |
| `MetricTile` | `components/MetricTile.tsx` | `label`、`value`、`unit`、`abnormal`、`time` | 监测 |
| `TrendChart` | `components/TrendChart.tsx` | `series`、`range` | 监测 |
| `AlertListItem` | `components/AlertListItem.tsx` | `alert`、`onOpen` | 监测 / 我的 |
| `MetricForm` | `components/MetricForm.tsx` | `onSubmitted` | 录入 |
| `MedicationForm` | `components/MedicationForm.tsx` | `onSaved`、`initial?` | 录入 / 用药 |
| `DocumentUploader` | `components/DocumentUploader.tsx` | `onUploaded` | 录入 |
| `DocumentConfirmForm` | `components/DocumentConfirmForm.tsx` | `document`、`onConfirmed` | 录入子页 |
| `CheckinRow` | `components/CheckinRow.tsx` | `reminder`、`checks`、`onCheck` | 用药 |
| `SafetyIssueCard` | `components/SafetyIssueCard.tsx` | `issue` | 用药 |
| `BigTextToggle` | `components/BigTextToggle.tsx` | `value`、`onChange` | 设置 |
| `SwitchRow` | `components/SwitchRow.tsx` | `label`、`desc?`、`checked`、`onChange` | 设置 |
| `SectionCard` | `components/SectionCard.tsx` | `title?`、`action?` | 通用 |

---

## 6. 页面规格

> 通用：页面内边距 20；卡片圆角 24、内边距 20；区块间距 20；首屏只放一个主任务，其余下移滚动。

### 6.1 问诊（首页，`/`）

```
┌─────────────────────────────────────┐
│ 🧑‍⚕️ 贴心小护士                 [🔊][SOS] │ header 56
│    在线                              │
├─────────────────────────────────────┤
│  今天                                │
│  ╭───────────────────╮              │
│  │ 早上好！今天血压测了吗？│           │
│  ╰───────────────────╯              │
│              ╭──────────────────╮   │ 对话流 flex-1
│              │ 我有点头晕          │   │
│              ╰──────────────────╯   │
│  ╭──────────────────────────────╮   │
│  │⚠ 预警·需要关注                 │   │
│  │ 您的血压 165/98，比平时高       │   │
│  │ [ 已了解 ]  ▶ 听一遍           │   │
│  ╰──────────────────────────────╯   │
├─────────────────────────────────────┤
│ [我头晕怎么办][帮我记血糖][查看预警]  │ 快捷句 52
├─────────────────────────────────────┤
│ ╭─────────────────────╮ ╭────────╮  │
│ │ 输入您想说的话…        │ │  发送   │  │ 输入区
│ ╰─────────────────────╯ ╰────────╯  │
│ ╭────────── 按住说话 ──────────╮    │
│ ╰──────────────────────────────╯    │
├─────────────────────────────────────┤
│  问诊①  监测   录入   用药   我的     │ TabBar
└─────────────────────────────────────┘
```

| 区块 | 占比 | 内容 | 交互 | 数据来源 |
|---|---|---|---|---|
| 页头 | 8% | 身份 + 静音 + SOS | 静音切换；SOS 弹窗 | 患者资料 |
| 对话流 | 52% | 消息 + 预警气泡按时间合并；顶部「今天」 | 滚动；逐条朗读；预警已了解 | 会话消息 + 预警 |
| 快捷句 | 8% | 4 个大胶囊横滑 | 一点即发送 | 静态配置 |
| 输入区 | 20% | 输入框 56 + 发送 56×56 + 按住说话 64 | 发送 / 录音识别 | `chat/stream`、`voice/transcribe` |
| TabBar | 10% | 5 项 + 角标 | 切换 | `AlertContext` |

**气泡规格**

- 护士气泡：白底、圆角 16、内边距 16、最大宽 85%、`.t-body`；下方「▶ 听一遍」48px。
- 若响应含 `presentation`：优先渲染 `summary`（结论）+ `key_points`（≤3）+ `action_items`；`reply` 作全文兜底；「▶ 听一遍」播放 `tts_text`。
- 用户气泡：`primary-deep` 底白字、右对齐。
- 预警气泡：白底 + 左 4px 等级色条 + 等级标签 + 标题 `.t-h2` + 一句人话 `.t-body` + 「已了解」56px + 「▶ 听一遍」48px + 「查看详情」文字按钮。
- 合并规则：消息来自 `GET /agents/sessions/{id}/messages`；预警来自 `GET /alerts` + WS；按 `created_at` 升序合并，预警按 `id` 去重。
- 空会话：静态欢迎气泡（不落库）。
- 流式中：气泡末尾「…」；中断保留已收文本 + 重试按钮。

**会话恢复**：进入页面取 `GET /agents/sessions` 最近一条，加载其消息；无会话则新会话。

**不做**：对话内 AgentTrace（后端照常记录，前端不渲染）。

### 6.2 监测（`/monitor`）

```
┌─────────────────────────────────────┐
│ 我的健康                       [🔊][SOS]│
├─────────────────────────────────────┤
│ ╭─────────────────────────────────╮ │
│ │ 🟢 稳定                          │ │ 风险卡 ~22%
│ │ 今天指标不错，继续保持            │ │
│ │ 刚更新                           │ │
│ ╰─────────────────────────────────╯ │
│ 今日指标                             │
│ ╭────────╮╭────────╮╭────────╮     │ 今日指标 ~20%
│ │血糖 6.8 ││血压135/85││心率 78 │     │
│ │空腹·正常 ││ 正常     ││ 正常    │     │
│ ╰────────╯╰────────╯╰────────╯     │
│ 健康趋势          [血糖|血压] [7|30]  │ 趋势 ~28%
│ ╭─────────────────────────────────╮ │
│ │        折线图 + 参考范围带        │ │
│ ╰─────────────────────────────────╯ │
│ 预警提醒（红→橙→黄→绿）              │ 预警 ~22%
│ ╭─────────────────────────────────╮ │
│ │🔴 严重异常·血糖 17.2            >│ │
│ ╰─────────────────────────────────╯ │
└─────────────────────────────────────┘
```

| 区块 | 占比 | 内容 | 交互 | 数据来源 |
|---|---|---|---|---|
| 风险卡 | 22% | `risk_level` 映射等级色 + 一句人话 + 更新时间 | 点击展开解释；可朗读 | `GET /health/dashboard` |
| 今日指标 | 20% | 2×2 卡：指标名 + 今日最新值 40px + 单位 + 时间 + 异常标记 | 点卡展开该指标 7 天小趋势 | `dashboard.today_records` |
| 健康趋势 | 28% | ECharts：血糖单线；血压收缩/舒张双线；参考范围带 | 切「血糖/血压」与「7/30 天」 | `GET /health/records?days=` |
| 预警列表 | 22% | 按等级排序（红>橙>黄>绿，同级按时间倒序） | 点击展开详情 +「已处理」 | `GET /alerts` |

**规则**
- 今日指标取每类最新一条，按 `recorded_at`；无记录显示「今日未记录」。
- 预警列表默认只显示未处理，已处理折叠在「查看已处理」。
- 风险卡等级与 `risk_level` 一一映射，禁止自行计算。

### 6.3 录入（`/record`）

```
┌─────────────────────────────────────┐
│ 记录健康数据                   [🔊][SOS]│
├─────────────────────────────────────┤
│ ╭─────────────────────────────────╮ │
│ │ ✚  记一项指标                 >  │ │ 入口 18%
│ ╰─────────────────────────────────╯ │
│ ╭─────────────────────────────────╮ │
│ │ 💊 添加用药                   >  │ │
│ ╰─────────────────────────────────╯ │
│ ╭─────────────────────────────────╮ │
│ │ 📷 上传报告                   >  │ │
│ ╰─────────────────────────────────╯ │
├─────────────────────────────────────┤
│ 选中后的表单区（62%）                 │
└─────────────────────────────────────┘
```

| 区块 | 占比 | 内容 | 交互 |
|---|---|---|---|
| 三个入口 | 18% | 三张高 72 大卡 | 选中后下方展开对应表单，入口保持可见 |
| 指标表单 | 62% | 类型胶囊 5 个；血压双输入；血糖场景；时间；备注；提交 | 提交后出结果反馈卡（正常/异常 + 参考范围 + 朗读） |
| 药品表单 | 62% | 药名、剂量、单位、频次大按钮组、时点 | 保存生成提醒；可返回编辑 |
| 报告上传 | 子页 | 全宽拍照按钮 120 高 + 相册/PDF | 上传后进入确认子页 |

**指标表单细节**
- 类型：血压 / 血糖 / 体重 / 血脂 / 血氧（`heart_rate` 不单列，可由语音或报告带入）。
- 血糖场景：空腹 / 餐后 2h / 随机 / 睡前 → `extra_data.type`。
- 血压：`value` = 收缩压，`extra_data.systolic/diastolic`。
- 提交：`POST /health/records` → 用返回的 `feedback` 渲染反馈卡；
  `feedback.alert_level` 非绿时给出「去监测页看看」链接。

**OCR 确认子页**（`/record/document/:id`）

```
← 确认识别结果
[ 体检/化验单 ]
检测日期：2026-10-08
╭────────────────────────────╮
│ 空腹血糖 6.8 mmol/L   [改]  │ 低置信度黄色提示
│ 血压 135/85 mmHg      [改]  │
╰────────────────────────────╯
[ 放弃 ]        [ 确认入库 ]
```

- 数据：`GET /documents/{id}` 取 `ocr_text`、`parsed_data`、`doc_type`。
- 化验单：渲染 `parsed_data.metrics`（可改 value、unit、context、systolic/diastolic）。
- 处方：渲染 `parsed_data.medications`（可改剂量、单位、频次、时点）。
- 确认：`POST /documents/{id}/confirm`，body 传用户编辑后的 `{metrics}` 或 `{medications}` 与 `exam_date`。
- 返回 `actions[]` 逐条展示「已记录 X」「已创建提醒 Y」。
- 放弃：`POST /documents/{id}/reject`。
- 已确认/已放弃的文档在「历史单据」里只读展示。

### 6.4 用药（`/medication`）

```
┌─────────────────────────────────────┐
│ 我的用药                       [🔊][SOS]│
├─────────────────────────────────────┤
│ ╭─────────────────────────────────╮ │
│ │⚠ 用药安全提示：…        查看全部 >│ │ 安全提示 ~12%
│ ╰─────────────────────────────────╯ │
│ 今日服药                     3/5     │
│ ▓▓▓▓▓▓▓▓▓▓░░░                      │ 今日 ~40%
│ ╭─────────────────────────────────╮ │
│ │ 08:00  二甲双胍片 0.5g          │ │
│ │         [ ✓ 已服 ]  [ 跳过 ]     │ │
│ ╰─────────────────────────────────╯ │
│ ╭─────────────────────────────────╮ │
│ │ 12:30  氨氯地平 5mg  [已服 12:31] │ │
│ ╰─────────────────────────────────╯ │
├─────────────────────────────────────┤
│ 全部用药                     [+ 添加] │ 全部 ~36%
│ 阿司匹林 100mg 每日1次   [暂停] [删] │
└─────────────────────────────────────┘
```

| 区块 | 占比 | 内容 | 交互 | 数据来源 |
|---|---|---|---|---|
| 安全提示 | 12% | 后端 `issues`，最多 2 条 | 点开查看全部与建议 | `GET /api/medication/safety`（不可用时前端兜底） |
| 今日服药 | 40% | 时间轴；每条「已服/跳过」；顶部进度 | 打卡即时更新；全部完成提示 | `GET /reminders/today` + 打卡接口（附录 A） |
| 全部用药 | 36% | 药名 + 剂量 + 频次 + 状态 | 编辑 / 暂停 / 删除（删除二次确认） | `GET/PATCH/DELETE /reminders` |

**6.4.1 今日服药**
- 数据：`GET /reminders/today`（返回今日有效提醒）。
- 每条按 `times_of_day` 展开为多个时间点（如 bid 两条）。若后端返回的是整条提醒，前端按 `times_of_day` 展开成「提醒 × 时间点」行。
- 打卡：`POST /reminders/{id}/checkin`（附录 A），body `{date, slot, status}`。
- 未打卡 → 双按钮；已服 → 绿色对勾 + 时间；已跳过 → 灰色「已跳过」+「撤销」。
- 进度 = 已打点数 / 今日总点数。

**6.4.2 全部用药**
- `GET /reminders` 列表；`PATCH /reminders/{id}` 修改；`PATCH` `{active:false}` 暂停；`DELETE` 删除。
- 删除必须自定义确认弹窗（大取消键），禁止 `window.confirm`。

**6.4.3 用药安全规则（后端权威，前端兜底）**

主路径：调用 `GET /api/medication/safety`，直接渲染后端返回的 `issues`。
兜底：仅当接口不可用时，才用 `lib/medicationSafety.ts` 的本地规则（规则见下表）。

输入：`patient.allergies`、`patient.medications`、`reminders[]`。输出 `SafetyIssue[]`，每条含 `level`、`title`、`why`、`advice`。

| 规则 | 判定 | 等级 |
|---|---|---|
| S1 过敏冲突 | `allergies` 按 `、,，空格` 拆分；药名包含过敏词 | red |
| S2 重复用药 | 药名去剂型/规格后相同，或同一通用名 ≥2 条 | orange |
| S3 剂量缺失 | `dose` 为空 | yellow |
| S4 剂量异常 | `dose > 5`（片/粒/袋）或 `dose > 1000`（mg） | orange |
| S5 常见相互作用 | 硬编码表命中（阿司匹林/氯吡格雷+华法林；二甲双胍+含碘造影剂；硝苯地平+西柚；他汀+克拉霉素/红霉素） | orange |

- 每条必须写清「是什么 / 可能什么后果 / 现在怎么做」。
- 列表底部固定一行小字：「以上为规则提示，不构成医疗建议，请咨询医生或药师。」
- 无命中时不显示该区块。

### 6.5 我的（`/me`）

```
┌─────────────────────────────────────┐
│ 我的                           [🔊][SOS]│
├─────────────────────────────────────┤
│ ╭─────────────────────────────────╮ │
│ │  ╭────╮  王阿姨                  │ │ 账号卡 ~22%
│ │  │头像│  68 岁 · 高血压 · 糖尿病  │ │
│ ╰─────────────────────────────────╯ │
│ ╭─────────────────────────────────╮ │
│ │ 🩺 健康档案                   >  │ │
│ │ 📋 管理方案                   >  │ │ 列表 ~52%
│ │ 🔔 预警记录                   >  │ │
│ │ ⚙️ 设置                       >  │ │
│ ╰─────────────────────────────────╯ │
│          退出登录（危险，红色）        │ ~8%
└─────────────────────────────────────┘
```

| 区块 | 占比 | 内容 | 交互 | 数据来源 |
|---|---|---|---|---|
| 账号卡 | 22% | 头像 72 + 姓名 + 年龄 + 慢病标签 | 点击进健康档案 | `GET /auth/me` + `GET /patients/me` |
| 列表 | 52% | 健康档案 / 管理方案 / 预警记录 / 设置 | 整行可点，进子页 | — |
| 退出登录 | 8% | 红色文字按钮 | 二次确认 → 清 token → `/login` | `POST /auth/logout` |

**6.5.1 健康档案子页**（`/me/profile`）
- 表单：性别、出生日期、身高、体重、慢病（4 个多选胶囊）、过敏史、长期用药、紧急联系人。
- 读取 `GET /patients/me`，保存 `PUT /patients/me`。
- 字段旁给示例文案，不强制填写；保存后轻提示。

**6.5.2 管理方案子页**（`/me/plans`）
- `GET /care-plans`，最新一条置顶。
- 三张卡：🥗 饮食（`diet_plan.items`）、🏃 运动（`exercise_plan.items`）、📊 监测（`monitoring_plan.items`）。
- 每条右侧「▶」可朗读；`medication_notes` 放底部提示条。
- 空态：「还没有管理方案，去问诊页说『请为我制定管理方案』」。

**6.5.3 预警记录子页**（`/me/alerts`）
- `GET /alerts`（全部），按时间倒序；顶部等级筛选胶囊（全部/红/橙/黄）。
- 每条：等级色条 + 标题 + 一句话 + 时间 + 已处理/未处理标签。
- 点击展开处理建议；未处理的给「标记已处理」。

**6.5.4 设置子页**（`/me/settings`）

| 分组 | 项目 | 实现 |
|---|---|---|
| 语音 | 播报开关、音量滑块、语速滑块 | 本地设置，作用于 TTS |
| 显示 | 大字模式、高对比模式 | `data-*` 属性 + 本地持久化 |
| 提醒 | 服药提醒开关、测量提醒开关 | 本地开关；测量提醒文案注明「打开 App 时提醒」 |
| 安全 | 紧急联系人管理、修改密码 | `PUT /patients/me`；改密见附录 A |
| 关于 | 免责声明、隐私政策、版本号、意见反馈 | 静态页 + `mailto:` |

- 每行 64px，右侧控件 ≥48。
- 免责声明/隐私政策为全屏子页，正文 `.t-body`，可朗读。

---

## 7. 交互流程

### 7.1 语音导入指标 / 用药 → 先复述、后入库

```
① 按住语音球并保持不动约 300ms（或按住输入区「按住说话」）→ 录音；按住即移动是拖动，不录音；松手 → 识别
② 松手 → POST /voice/transcribe → 文本
③ 先调后端 POST /agents/extract（主路径）；
   成功 → ④；失败 → 前端 parseHealthParams 兜底；仍失败 → 「没太听清，能再说一次吗？」→ 回 ①
④ 语音复述（播报开启）：「我听到您说，空腹血糖 6.8，对吗？」
   同时底部弹「确认卡」
⑤ 确认卡：标题「我听到您说」+ 主信息（.t-display）+ 
   「对，记下来」56 主 / 「不对，重说」56 次
⑥ 「对」→ 指标走 POST /health/records，用药走 POST /reminders
   → 成功提示 + 语音「已经帮您记好了」→ 关卡片
   「不对」→ 关卡片，重新录音
   遮罩/返回 → 放弃，草稿丢弃
```

**兜底解析规则（`parseHealthParams`，仅在后端 `/agents/extract` 失败时使用）**

| 意图 | 触发词 | 抽取 | 输出 |
|---|---|---|---|
| 血糖 | 血糖 | 数值 + 场景（空腹/餐后/随机/睡前） | `blood_glucose` + `extra_data.type` |
| 血压 | 血压/高压/低压 | `135/85` 或「高压 135 低压 85」 | `blood_pressure` + systolic/diastolic |
| 体重 | 体重 | 数值 + kg/公斤/千克 | `weight` |
| 心率 | 心率/脉搏 | 数值 | `heart_rate` |
| 血氧 | 血氧/血氧饱和度 | 数值 | `spo2` |
| 血脂 | 低密度/总胆固醇/甘油三酯/高密度 | 数值 | `blood_lipid` + `extra_data.type` |
| 用药 | 吃/服用/开/加 + 药名 | 药名 + 剂量/单位 + 频次词 | 提醒草稿 |

- 数值合理区间校验（血糖 1–33、血压 40–300、心率 30–220、血氧 50–100），越界判「没听清」。
- 一句话多意图：只取第一个，并提示「先记这个，其他的可以再说一次」。
- 确认卡展示原始文本，便于核对。

### 7.2 预警进入对话并播报

```
① AlertProvider 挂载：GET /patients/me → id
   GET /alerts?unresolved_only=true → 初始列表
   new WebSocket(`/api/ws/alerts/${id}`)
② 收到消息：按 id 去重插入；未读 +1；角标更新；
   若播报开启且未在播报 → 播报模板；
   若在问诊页 → 追加预警气泡并滚到底
③ WS 断开：指数退避（1s→30s，最多 5 次）；仍失败降级 60s 轮询
④ 进入问诊页：未读预警插入对话末尾；
   逐条 PATCH /alerts/{id}/read；角标递减
```

**播报模板（≤2 句）**

| 等级 | 文案 |
|---|---|
| red | 「小护士提醒您：{标题}。请立即联系医生或拨打 120。」 |
| orange | 「小护士提醒您：{标题}。建议尽快联系医生。」 |
| yellow | 「小护士提醒您：{标题}。先休息一下，再测一次。」 |
| green | 不播报 |

**硬性**：不做全局横幅、不做 toast；多条只播最新一条；音频被浏览器拦截时静默降级为球脉冲 + 气泡。

### 7.3 SOS 倒计时

```
点 SOS → 全屏遮罩 + 卡片
  标题「需要紧急帮助吗？」+ 电话 + 倒计时环 5→1
  [ 取消 ]  [ 立即拨打 ]
归零 → tel: 拨号
取消 / 遮罩 / Esc → 关闭
无联系人 → 「拨打 120」+「去设置添加」
```

- `setInterval` 每 1s 递减，卸载清理。
- 取消键视觉大于拨打键。
- 桌面端 `tel:` 无响应时显示可复制号码。

### 7.4 服药打卡

```
用药页 → 今日服药
每条「提醒 × 时间点」一行：[✓ 已服] [跳过]
点已服 → 绿色对勾 + 时间；进度 +1
点跳过 → 灰色「已跳过」+「撤销」
全部完成 → 「今天的药都吃完啦」+ 克制动效
刷新后状态保留（后端或 localStorage，见附录 A）
```

### 7.5 指标录入

```
录入页 → 记一项指标 → 选类型 → 填数值/场景/时间
→ 提交 POST /health/records
→ 反馈卡：message + reference_range + 等级色
→ 异常时给「去监测页看看」；可「▶ 朗读」
→ 继续录入 / 返回
```

### 7.6 报告 OCR 确认

```
上传 → POST /documents/upload → 返回文档对象
→ 跳 /record/document/:id
→ 渲染可编辑识别项（低置信度黄色提示）
→ 放弃：POST /documents/{id}/reject
→ 确认：POST /documents/{id}/confirm {metrics|medications, exam_date}
→ 展示 actions[]（已记录/已建提醒）
```

---

## 8. 状态与边界

| 场景 | 处理 |
|---|---|
| 未登录 | 重定向 `/login`（沿用拦截器） |
| 无患者档案 404 | 重定向 `/setup` |
| 患者未填疾病 | 页面正常，不阻塞 |
| 空会话 | 欢迎气泡 |
| 发送中 | 禁用发送 + 「…」 |
| 流式中断 | 保留已收文本 + 重试 |
| 语音未配置 503 | 保留按钮，点击提示「语音服务未配置」 |
| 麦克风无权限 | 提示改用打字 |
| WS 不可用 | 轮询降级，不阻塞 |
| TTS 失败 | 按钮复原 + 轻提示 |
| 图表无数据 | 显示「暂无数据，先记录一次」 |
| 打卡数据缺失 | 显示未打卡，不报错 |
| 报告识别为空 | 确认页提示「未识别到指标，请重拍」 |
| 上传失败 | 错误卡 + 「重新上传」 |

---

## 9. 验收清单

### 9.1 结构

- [ ] 底部 5 个 tab，顺序 问诊/监测/录入/用药/我的，无第 6 入口
- [ ] 登录后默认落在 `/`（问诊）
- [ ] 所有 tab 可点，无白屏
- [ ] 页头/TabBar 固定，内容独立滚动
- [ ] 安全区不被刘海/Home 条遮挡

### 9.2 语音球 / SOS

- [ ] 球默认右缘，不遮挡 TabBar、页头、输入框
- [ ] 按住不动约 300ms 后开始录音，球变红并显示「正在聆听…」；松手才识别
- [ ] 按住后立即移动可拖动球，不进入录音；松手吸附左右边缘
- [ ] 快速轻点或录音短于 0.5 秒不送识别，只提示手势
- [ ] 设置页可复位球位置
- [ ] 静音状态在页头喇叭可见、可恢复
- [ ] SOS 常驻页头、88×48、5 秒倒计时、可取消
- [ ] 无联系人显示「拨打 120」

### 9.3 问诊

- [ ] 历史消息恢复并滚到底
- [ ] 文字发送走 SSE 逐字出现
- [ ] 按住说话可识别并回填
- [ ] 护士消息可逐条朗读/停止
- [ ] 预警以气泡出现，不弹横幅
- [ ] 角标随未读增减，进入问诊清零
- [ ] 语音导入先确认后入库，取消不入库
- [ ] 三态（空/加载/失败）齐全

### 9.4 监测

- [ ] 风险卡等级与 `risk_level` 一致
- [ ] 今日指标取每类最新一条，无记录显示「今日未记录」
- [ ] 趋势可切血糖/血压与 7/30 天
- [ ] 预警按等级排序，可标记已处理

### 9.5 录入

- [ ] 三种入口切换不丢已填内容（或明确重置提示）
- [ ] 血压双输入、血糖场景可选
- [ ] 提交后反馈卡显示参考范围与等级
- [ ] 报告上传后进入确认页
- [ ] 确认页可编辑/移除识别项，确认后展示 actions
- [ ] 放弃后文档状态为已放弃

### 9.6 用药

- [ ] 今日按时间点展开，打卡状态正确
- [ ] 进度随打卡变化，刷新保留
- [ ] 全部用药可编辑/暂停/删除（删除二次确认）
- [ ] 安全提示命中规则，且带免责小字
- [ ] 无命中时区块隐藏

### 9.7 我的 / 设置

- [ ] 账号信息正确（姓名/年龄/慢病标签）
- [ ] 健康档案可读写
- [ ] 管理方案展示三项计划，可朗读
- [ ] 预警记录可筛选、可标记已处理
- [ ] 设置项全部可用并持久化
- [ ] 大字模式即时生效且布局不破
- [ ] 高对比模式可读性提升
- [ ] 退出登录二次确认

### 9.8 适老化 / 工程

- [ ] 正文 ≥18、标题 ≥20（逐元素抽查）
- [ ] 触控 ≥48×48
- [ ] 正文对比度 ≥4.5:1
- [ ] 危险操作均二次确认
- [ ] 键盘可走通主要流程，焦点可见
- [ ] `prefers-reduced-motion` 下动画关闭
- [ ] 允许双指缩放
- [ ] 无新增依赖、无组件内 fetch、无硬编码色值/字号、无 `console.log`
- [ ] `npm run build` 通过

---

## 10. 反模式清单（禁止项）

| 禁止 | 为什么 | 正确做法 |
|---|---|---|
| 后台管理风（侧边栏、表格、密集列表） | 与适老化目标相反 | 单列卡片流 |
| 新增第 6 个 tab 或二级 tab | IA 锁定 | 深层内容用全屏子页 |
| 用全局 toast/横幅弹预警 | 要求预警只进问诊 | 气泡 + 角标 + 语音 |
| 把录音藏在弹窗/面板里 | 多一步操作，老人易迷路 | 悬浮球按住即录，录音状态直接显示在球上 |
| 让拖动和录音在同一瞬间抢手势 | 一拖就进识别，或一按就移动 | 用 300ms 按住确认区分：先移动=拖动，后保持=录音 |
| 正文 <18、触控 <48 | 硬约束 | `.t-*` + 统一按钮尺寸 |
| `div` + `onClick` 当按钮 | 语义/焦点丢失 | `button`/`a` + `:focus-visible` |
| 组件内直接 `fetch` | 契约漂移 | 只走 `api/client.ts` |
| 硬编码色值/字号 | 大字模式失效 | token + CSS 变量 |
| 新装 UI 库 | 包体与风格冲突 | 原生 + Tailwind |
| 危险操作无二次确认 | 老人误触 | 自定义确认弹窗，取消键更大 |
| 语音球固定/遮挡 TabBar | 交互契约 | 可拖 + 吸附 + 夹紧 |
| 只做正常态 | 真机白屏 | 三态齐全 |
| 写死演示数据兜底 | 掩盖真实问题 | 失败显示错误态 |
| 把 AgentTrace 渲染进对话 | 对老人是噪音 | 不渲染 |
| 图表 10px 小字 | 看不清 | ≥16px 且高对比 |
| 用 `window.confirm` | 样式不可控、按钮太小 | 自定义弹窗 |
| 删除/改写后端接口与模型 | 破坏契约 | 只增不改，改前说明 |
| 用表情符号代替图标 | 风格不稳、语义弱 | 统一 SVG 图标 |

---

## 11. 文件改动清单

### 新增

```
frontend/src/components/TabBar.tsx
frontend/src/components/PageHeader.tsx
frontend/src/components/VoiceOrb.tsx
frontend/src/components/SosButton.tsx
frontend/src/components/SosDialog.tsx
frontend/src/components/MessageBubble.tsx
frontend/src/components/AlertBubble.tsx
frontend/src/components/VoiceConfirmCard.tsx
frontend/src/components/RiskCard.tsx
frontend/src/components/MetricTile.tsx
frontend/src/components/TrendChart.tsx
frontend/src/components/AlertListItem.tsx
frontend/src/components/MetricForm.tsx
frontend/src/components/MedicationForm.tsx
frontend/src/components/DocumentUploader.tsx
frontend/src/components/DocumentConfirmForm.tsx
frontend/src/components/CheckinRow.tsx
frontend/src/components/SafetyIssueCard.tsx
frontend/src/components/BigTextToggle.tsx
frontend/src/components/SwitchRow.tsx
frontend/src/components/SectionCard.tsx
frontend/src/components/Toast.tsx
frontend/src/context/AlertContext.tsx
frontend/src/context/VoiceContext.tsx
frontend/src/context/SettingsContext.tsx
frontend/src/lib/parseHealthParams.ts
frontend/src/lib/medicationSafety.ts
frontend/src/lib/voiceSettings.ts
frontend/src/lib/settings.ts
frontend/src/constants/legal.ts
frontend/src/pages/MonitorPage.tsx
frontend/src/pages/RecordPage.tsx
frontend/src/pages/MedicationPage.tsx
frontend/src/pages/ProfilePage.tsx
frontend/src/pages/SubPages/HealthProfilePage.tsx
frontend/src/pages/SubPages/CarePlansPage.tsx
frontend/src/pages/SubPages/AlertHistoryPage.tsx
frontend/src/pages/SubPages/SettingsPage.tsx
frontend/src/pages/SubPages/LegalPage.tsx
frontend/src/pages/DocumentConfirmPage.tsx
```

### 修改

```
frontend/tailwind.config.js        追加 3.1 颜色 token
frontend/src/index.css             追加 .t-*、CSS 变量、安全区、reduced-motion
frontend/vite.config.ts            /api 代理加 ws: true
frontend/index.html                移除 user-scalable=no / maximum-scale=1
frontend/src/App.tsx               新路由表（见下）
frontend/src/components/Layout.tsx 重写为 AppShell
frontend/src/pages/ChatPage.tsx    重构 UI 与交互，保留 SSE/录音/TTS
frontend/src/api/client.ts         仅在需要时追加 methods（不新增 fetch）
```

### 删除 / 停止使用

```
frontend/src/pages/DashboardPage.tsx   内容并入 MonitorPage（可删）
frontend/src/pages/AlertsPage.tsx      内容并入监测 + 我的（可删）
frontend/src/pages/PlansPage.tsx       并入 我的/管理方案（可删）
frontend/src/pages/FollowupPage.tsx    随访功能已移除（可删）
frontend/src/pages/KnowledgePage.tsx   新 IA 不再使用（可删）
frontend/src/pages/RecordsPage.tsx     由 RecordPage 取代（可删）
frontend/src/pages/RemindersPage.tsx   由 MedicationPage 取代（可删）
frontend/src/components/AgentTrace.tsx 不再渲染（保留文件）
```

### 路由表

```
/login
/register
/setup

/                          问诊
/monitor                   监测
/record                    录入
/record/document/:id       报告确认
/medication                用药
/me                        我的
/me/profile                健康档案
/me/plans                  管理方案
/me/alerts                 预警记录
/me/settings               设置
/me/settings/legal/:doc    免责声明 / 隐私政策
```

---

## 12. 数据契约总表

| 用途 | 方法 | 路径 | 备注 |
|---|---|---|---|
| 注册 | POST | `/api/auth/register` | 需 `agreed_disclaimer` |
| 登录 | POST | `/api/auth/login` | |
| 当前用户 | GET | `/api/auth/me` | |
| 退出 | POST | `/api/auth/logout` | 后端为空实现，前端清 token |
| 刷新 | POST | `/api/auth/refresh` | |
| 患者资料 | GET/PUT | `/api/patients/me` | 含 `diseases`、`emergency_contact` |
| 初始化档案 | POST | `/api/patients/me/setup` | |
| 仪表盘 | GET | `/api/health/dashboard` | 风险/今日/趋势（`pending_followups` 字段保留但不使用） |
| 记录列表 | GET | `/api/health/records?days=` | 趋势图数据 |
| 新建记录 | POST | `/api/health/records` | 返回 `{record, feedback}` |
| 删除记录 | DELETE | `/api/health/records/{id}` | |
| 生活方式 | POST/GET | `/api/health/lifestyle` | 录入页可选用 |
| 预警列表 | GET | `/api/alerts?unresolved_only=` | |
| 标记已读 | PATCH | `/api/alerts/{id}/read` | |
| 标记已处理 | PATCH | `/api/alerts/{id}/resolve` | |
| 管理方案 | GET | `/api/care-plans` | |
| 随访（已停用） | GET | `/api/follow-ups` | 随访功能移除，前端不再调用 |
| 随访（已停用） | POST | `/api/follow-ups/{id}/submit` | 随访功能移除，前端不再调用 |
| 上传报告 | POST | `/api/documents/upload` | multipart |
| 文档列表 | GET | `/api/documents` | |
| 文档详情 | GET | `/api/documents/{id}` | |
| 确认文档 | POST | `/api/documents/{id}/confirm` | |
| 放弃文档 | POST | `/api/documents/{id}/reject` | |
| 会话列表 | GET | `/api/agents/sessions` | |
| 会话消息 | GET | `/api/agents/sessions/{id}/messages` | |
| 流式问诊 | POST | `/api/agents/chat/stream` | SSE |
| 删除会话 | DELETE | `/api/agents/sessions/{id}` | |
| 服药提醒列表 | GET | `/api/reminders` | |
| 今日提醒 | GET | `/api/reminders/today` | |
| 新建提醒 | POST | `/api/reminders` | |
| 修改提醒 | PATCH | `/api/reminders/{id}` | `active` 暂停 |
| 删除提醒 | DELETE | `/api/reminders/{id}` | |
| 语音识别 | POST | `/api/voice/transcribe` | form-data wav |
| 语音合成 | POST | `/api/voice/tts` | 返回 blob |
| 实时预警 | WS | `/api/ws/alerts/{patient_id}` | 无鉴权，标 TODO |

---

## 附录 A：需要的后端补充（必需，与 `AGENT_IMPLEMENTATION_SPEC.md` 对齐）

### A.1 服药打卡

```sql
-- 新表
medication_logs(
  id            SERIAL PRIMARY KEY,
  patient_id    INT NOT NULL REFERENCES patients(id),
  reminder_id   INT NOT NULL REFERENCES medication_reminders(id),
  log_date      DATE NOT NULL,
  slot          VARCHAR(5) NOT NULL,   -- '08:00'
  status        VARCHAR(10) NOT NULL,  -- taken | skipped
  recorded_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE (reminder_id, log_date, slot)
)
```

```
POST /api/reminders/{id}/checkin
body: { "date": "2026-11-04", "slot": "08:00", "status": "taken" }
resp: { "ok": true }

GET /api/reminders/today?date=2026-11-04
resp: [{ ...reminder, "checks": { "08:00": "taken", "20:00": "skipped" } }]
```

打卡为后端必需能力，前端不做本地兜底。

### A.2 修改密码

```
POST /api/auth/change-password
body: { "old_password": "...", "new_password": "..." }
resp: { "ok": true }
```

不允许时：设置项显示「暂未开放」，不提供假成功。

### A.3 意见反馈

```
POST /api/feedback
body: { "content": "...", "contact": "可选" }
```

不允许时：`mailto:feedback@example.com?subject=...`。

### A.4 WebSocket 鉴权

```
ws://host/api/ws/alerts/{patient_id}?token=<access_token>
后端校验 token 的 sub 与 patient 归属一致，否则 4401 关闭。
```

### A.5 语音结构化抽取（必需，后端权威）

```
POST /api/agents/extract
body: { "text": "空腹血糖6.8" }
resp: {
  "kind": "metric",
  "metric": { "record_type": "blood_glucose", "value": 6.8, "unit": "mmol/L",
              "extra_data": { "type": "fasting" } }
}
```

前端先调此接口；失败时才用 `parseHealthParams` 本地规则兜底。成功仍走确认卡，不直接入库。

---

## 附录 B：实现顺序与验收节奏

| 步骤 | 交付 | 通过标准 |
|---|---|---|
| 1 | token + App Shell | 5 tab 可切换；球可拖；SOS 倒计时可用；构建通过 |
| 2 | 问诊页 | 流式对话、语音识别、预警气泡、语音导入确认可用 |
| 3 | 监测页 | 风险卡/今日/趋势/预警四块数据正确 |
| 4 | 录入页 + OCR | 指标入库、药品建提醒、报告确认分发正确 |
| 5 | 用药页 | 打卡、全部用药 CRUD、安全提示规则命中 |
| 6 | 我的 + 设置 | 档案读写、方案展示、预警历史、设置持久化 |
| 7 | 全局自检 | 第 9 节全勾选，第 10 节零违反 |

每步结束后：`npm run build` 通过 + 按第 9 节对应小节自检 + 报告改动文件。
