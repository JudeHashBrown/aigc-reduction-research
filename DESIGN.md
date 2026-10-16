# DESIGN.md — 学术论文 AI 降低率与文本人性化平台设计指南

## 1. 核心设计原则 (Core Design Principles)

### 1.1 学术可信与权威感 (Academic Credibility & Trust)

- **拒绝浮夸 AI 元素**：禁用炫彩渐变（Rainbow Glow）、发光粒子或过度的 3D 拟真元素。学术用户对“AI 幻觉”和“伪科学”极度敏感，界面需传递类似 LaTeX、Nature / IEEE 论文排版或 Google Scholar 的专业与严谨。
- **信息高透明度**：清楚展示降重逻辑（如“语义替换”、“句式重组”、“学术化提炼”），不提供“一键神仙降重”这种黑盒承诺，强化算法透明度和检测源说明。

### 1.2 极致的对比与编辑专注度 (Dual-Pane Focus & Diff Precision)

- **双栏等位对照**：核心工作区采用 1:1 双栏（原句 vs 降重句）设计，字号、行高严格对齐，支持滚动联动。
- **无干扰视效**：降低非核心 UI（如导航栏、侧边栏）的视觉权重，在编辑状态下自动沉浸，确保长文本阅读时不产生视觉疲劳。

### 1.3 渐进式掌控 (Progressive Control & Risk Visibility)

- **实时风险预警**：AI 检出率/拟合度指标用分级色彩呈现（安全/中危/高危），避免纯红色的强刺激焦虑，采用带学术衬度（Slate / Sage / Amber）的调和色。
- **粒度可控**：提供“微调（保持原意）”、“中度（学术重构）”、“深度（语义重塑）”等多阶控制阀，将控制权交给作者。

## 2. 视觉语言与设计 Token (Visual Design Tokens)

### 2.1 色彩系统 (Color Palette)

采用了沉稳的**学术蓝灰（Slate Navy）\**作为主色调，搭配功能性的\**高亮对比色（Diff Tone）**。

| **Token 名称**        | **Hex / Value**       | **语义描述与应用场景**                                       |
| --------------------- | --------------------- | ------------------------------------------------------------ |
| `color-bg-base`       | `#F8FAFC`             | 全局背景：极淡的灰蓝，比纯白更护眼，接近高品质纸张           |
| `color-surface`       | `#FFFFFF`             | 卡片/编辑器背景：纯白，突出版面核心内容                      |
| `color-primary`       | `#0F172A`             | 主文字/主视觉锚点：深 Slate 色，非纯黑（#000），避免视觉刺眼 |
| `color-academic-blue` | `#1E3A8A`             | 品牌/强调色：深沉的学术蓝，用于主按钮、选中态、专业徽章      |
| `color-diff-deleted`  | `#FEE2E2` / `#991B1B` | 变更高亮（删减/高风险）：淡粉红底 + 深红字                   |
| `color-diff-added`    | `#DCFCE7` / `#166534` | 变更高亮（新增/优化）：淡薄荷绿底 + 深绿字                   |
| `color-risk-safe`     | `#059669`             | AI 率低于 15%：安全绿（Sage Green）                          |
| `color-risk-warning`  | `#D97706`             | AI 率 15%~40%：警示黄（Muted Amber）                         |
| `color-risk-danger`   | `#DC2626`             | AI 率高于 40%：风险红（Rust Red）                            |

### 2.2 字体排版 (Typography)

学术文本要求极高的可读性，中英文混排需兼顾字距与对齐。

```
Font Family (Sans-serif):
  "Inter", -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;

Font Family (Monospace / Diff View):
  "JetBrains Mono", "Fira Code", "Source Code Pro", monospace;
```

- **正文排版（编辑器内）**：`Font-Size: 15px` / `Line-Height: 1.75` / `Letter-Spacing: 0.01em`
- **标题排版**：采用紧凑的字距与加粗，表现专业感。
- **比对高亮**：改写部分的底色填充需有 `2px` 内边距与 `3px` 圆角，切忌大面积块状死板高亮。

### 2.3 间距与圆角 (Spacing & Radius)

- **圆角风格**：微圆角克制风格。控制板与卡片采用 `6px` ~ `8px`，按钮与 Tag 采用 `4px`，避免大圆角（16px+）带来的玩具感/娱乐感。
- **阴影级别**：极轻量阴影 `box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05)`，主要依靠 `1px solid #E2E8F0` 的边框切割空间。

## 3. 核心界面架构与布局规范 (Layout & Structure)

系统主要由三个核心区域构成：**导航头部（Minimal Header）**、**控制与指标栏（Control Bar）**、**双栏对比工作区（Main Diff Workspace）**。

```
+-----------------------------------------------------------------------+
|  Logo / 学术引擎状态                 [论文类型: 理工/人文] [导出/复制]  |  <-- Header
+-----------------------------------------------------------------------+
|  AI 检出率预测: 12% [安全] | 模式: 降重/学术化 | 改写强度: [--o--]     |  <-- Control Bar
+-------------------------------------------------+---------------------+
| 原文 (Original) - 780 字                        | 优化后 (Humanized)  |
|                                                 |                     |
| 本研究通过构建基于深度学习的检测模型...         | 我们建立了一个深度...|
| [划线删除区]                                    | [绿底新增区]        |
|                                                 |                     |
+-------------------------------------------------+---------------------+
```

### 3.1 双栏对比工作区 (Diff Workspace)

1. **左栏（Input / Original）**：允许粘贴、拖拽 `.docx` / `.pdf` 上传。高亮显示被检测为“AI 特征明显”的重灾区句段（带黄色/红色虚线底纹）。
2. **右栏（Output / Optimized）**：显示降重/人性化改写后的文本。
   - **Diff 模式切换**：提供 `直观阅读模式`（隐藏删除线，只看最终文本）与 `修订对比模式`（红绿 Git 式比对）。
   - **单句悬浮悬停（Hover Sync）**：鼠标悬停在左侧某句子时，右侧对应改写的句子自动加高亮边框并互相锚定。

### 3.2 仪表盘与 AI 拟合指标 (Metrics Dashboard)

- **AI 概率仪表盘**：采用环形进度条或分段状态条，直观展示 **处理前 AI 概率 vs 处理后预期 AI 概率**。
- **学术规范指标**：额外提供“学术词汇丰富度”、“句式复杂度”、“重复率预估”三项微观指标，进一步强化专业工具感。

## 4. 关键交互与状态设计 (Key Interactions & States)

### 4.1 局部微调交互 (Inline Sentence Polish)

用户往往不希望全盘接受 AI 的改写，需要“局部替换”。

- **点击单句**：弹出 Floating Action Bar（浮动工具栏）。
- **提供 3 种变体（Variants）**：
  - 变体 A：学术增强（更严谨的学术词汇）
  - 变体 B：精简表达（缩减冗余）
  - 变体 C：主动/被动语态翻转（有效规避 AI 检测特征）
- **一键采纳**：键盘快捷键 `Enter` 采纳当前选中的变体。

### 4.2 空状态与加载状态 (Empty & Loading States)

- **空状态**：提供“导入示例论文段落（理工科/社科/医学）”按钮，降低新用户的试用门槛。
- **处理中状态（Processing）**：
  - **禁止使用全屏 Blur 遮罩**。
  - 采用逐句“扫光/脉冲（Skeleton Pulse）”特效，并在右栏逐步流式输出（Streaming），营造实时协同修剪的仪式感。

### 4.3 安全防错与隐私声明 (Safety & Privacy)

- **隐私水印/承诺**：在编辑器底部显著位置标注：“*文本采用端到端加密传输，承诺不纳入任何 AI 训练集，不留存查重库*”。
- **历史版本回滚**：支持 `Ctrl+Z` / `Ctrl+Y`，并在右上角显示版本历史栈（Version History）。

## 5. 前端组件与样式代码指导 (Implementation Spec)

针对 UI 工程师落地时的 CSS/Tailwind 建议：

CSS

```
/* 典型 Diff 变动样式 */
.diff-deleted {
  background-color: #fee2e2;
  color: #991b1b;
  text-decoration: line-through;
  padding: 1px 4px;
  border-radius: 3px;
  margin: 0 1px;
}

.diff-added {
  background-color: #dcfce7;
  color: #166534;
  font-weight: 500;
  padding: 1px 4px;
  border-radius: 3px;
  margin: 0 1px;
  border-bottom: 2px solid #22c55e;
}

/* 编辑器高品质排版约束 */
.academic-editor {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 0.9375rem; /* 15px */
  line-height: 1.75;
  color: #0f172a;
  background-color: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 1.5rem;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}
```
