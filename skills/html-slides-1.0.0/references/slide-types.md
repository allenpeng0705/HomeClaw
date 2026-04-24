# 幻灯片页面类型

> **通用规则**：所有颜色使用 `var(--text-secondary)` 或 `style="color: var(--text-secondary)"` 以支持暗/亮模式切换。不要使用硬编码的 Tailwind 灰度类（如 `text-gray-400`）作为正文颜色。

## 1. 封面页

用于演示开场。

**结构：**
- 超大主标题（font-black，居中）
- 副标语（font-light，灰色）
- 系列标识/Logo（可选）
- `data-notes` 属性用于演讲者备注

**示例：**
```html
<div class="slide" data-notes="开场问候，简短自我介绍。">
  <h1 class="text-5xl font-black mb-6 leading-tight">重新定义效率</h1>
  <p class="text-xl font-light" style="color: var(--text-secondary)">AI时代的工作方式</p>
</div>
```

---

## 2. 标题冲击页

用于章节开始或重点强调。

**结构：**
- 单行/双行大标题
- 几乎无正文（最多一行辅助文字）
- `data-notes` 用于演讲者提示

**示例：**
```html
<div class="slide" data-notes="停顿，制造悬念："我不是要讲效率，而是要重新定义它。"">
  <h1 class="text-4xl font-black text-center">
    不是更努力<br>而是更聪明
  </h1>
</div>
```

---

## 3. 金句强调页

用于引用、名言、核心观点。

**结构：**
- 大引号装饰（opacity 0.4 的 secondary 色）
- 金句内容（font-bold）
- 来源/出处（font-light，opacity 0.6 的 secondary 色）

**示例：**
```html
<div class="slide" data-notes="停顿三秒，再读金句。">
  <span class="text-6xl block mb-2" style="color: var(--text-secondary); opacity: 0.4">"</span>
  <p class="text-2xl font-bold mb-6">简单比复杂更难</p>
  <span class="text-lg font-light" style="color: var(--text-secondary); opacity: 0.6">— Steve Jobs</span>
</div>
```

---

## 4. 步骤说明页

用于流程、方法、操作指南。

**结构：**
- 动词型大标题
- 简洁说明（1-2行）
- 可选：步骤编号

**示例：**
```html
<div class="slide" data-notes="详细解释第一步的"为什么"。">
  <span class="text-6xl font-black mb-4" style="color: #3b82f6">01</span>
  <h2 class="text-3xl font-bold mb-4">明确目标</h2>
  <p class="text-lg font-light" style="color: var(--text-secondary)">
    先问自己：这件事最重要的结果是什么？
  </p>
</div>
```

---

## 5. 对比页

用于展示变化、差异、前后对比。

**结构：**
- 左右或上下分栏
- 对比元素使用不同颜色标识
- 简洁文字说明

**示例：**
```html
<div class="slide" data-notes="指出传统方式的问题，再引出新的做法。">
  <div class="text-center mb-8">
    <span class="text-xl line-through" style="color: #f87171">传统方式</span>
  </div>
  <div class="text-center">
    <span class="text-3xl font-bold" style="color: #4ade80">全新体验</span>
  </div>
</div>
```

---

## 6. 数据展示页

用于关键数字、统计、成果。

**结构：**
- 超大数字（font-black）
- 单位/说明（font-light）
- 简短解释

**示例：**
```html
<div class="slide" data-notes="给出数据背后的故事，让数字有温度。">
  <span class="text-7xl font-black">10x</span>
  <p class="text-xl font-light mt-4" style="color: var(--text-secondary)">效率提升</p>
</div>
```

---

## 7. 列表页

用于多点说明，但必须保持极简。

**结构：**
- 标题
- 3-5 个要点（不能更多）
- 每个要点 ≤10 字

**示例：**
```html
<div class="slide" data-notes="逐条解释，每条停一秒。">
  <h2 class="text-2xl font-bold mb-8">三个原则</h2>
  <ul class="space-y-6 text-xl">
    <li>• 少即是多</li>
    <li>• 专注核心</li>
    <li>• 持续迭代</li>
  </ul>
</div>
```

---

## 8. 结尾行动页

用于演示结束，呼吁行动。

**结构：**
- 总结金句
- 行动号召（CTA）
- 联系方式/二维码（可选）

**示例：**
```html
<div class="slide" data-notes="CTA：扫码联系我们，或访问官网。留联系方式。">
  <h1 class="text-3xl font-bold mb-8">现在就开始改变</h1>
  <p class="text-xl font-light" style="color: var(--text-secondary)">扫码获取更多信息</p>
</div>
```

---

## 页面选择指南

| 内容类型 | 推荐页面类型 |
|---------|-------------|
| 演示开场 | 封面页 |
| 章节分隔 | 标题冲击页 |
| 核心观点 | 金句强调页 |
| 操作步骤 | 步骤说明页 |
| 前后对比 | 对比页 |
| 关键数据 | 数据展示页 |
| 多点说明 | 列表页（≤5点）|
| 演示结束 | 结尾行动页 |

## 演讲者备注（data-notes）

在每个 `<div class="slide">` 上添加 `data-notes="..."` 属性：

```html
<div class="slide" data-notes="这里要讲一个关于客户痛点的故事……">
```

向上滑动当前幻灯片即可在演示器视图中显示备注。

## 横屏模式（16:9）

默认竖屏。如需横屏：
1. 生成时在每个 slide 添加 `data-ratio="16/9"`
2. 或在链接后加 `?ratio=16/9`

```html
<div class="slide" data-ratio="16/9">...</div>
```
