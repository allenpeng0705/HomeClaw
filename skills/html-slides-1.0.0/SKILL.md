---
name: html-slides
description: "Generate a 乔布斯-style minimal vertical single-page HTML presentation from the user's script (single file, open in browser). Use this skill when the user asks for 乔布斯/极简/竖屏/HTML slides. For standard PowerPoint (.pptx) use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...]). Output goes to user/companion output folder; return the open link. Supports dark/light mode toggle, speaker notes (data-notes attribute), and 16:9 landscape via ?ratio=16/9."
trigger:
  patterns: ["乔布斯|极简.*演示|竖屏.*演示|HTML.*演示|单页.*演示|极简.*幻灯片|乔布斯.*幻灯片|HTML\\s*slides|html\\s*slides|html\\s*slide|生成.*HTML.*[Ss]lides|生成.*幻灯片|总结.*html|生成.*html.*slide|乔布斯.*极简|极简.*乔布斯"]
  instruction: |
    The user asked for 乔布斯-style, 极简, or HTML presentation/slides from a document. You HAVE the html-slides skill: (1) document_read(path) to get the file content, (2) use that text to generate the full HTML (all slides), (3) call save_result_page(title=..., content=<the full HTML you generated>, format='html') or file_write(path='output/...', content=<full HTML>).

    IMPORTANT — output silently, do not show intermediate steps to the user:
    - Do NOT output the refined script as a separate Markdown block
    - Do NOT output the slide structure outline
    - Do NOT paste the raw HTML code in the chat
    - ONLY output: the save confirmation with the link (or "已保存到您的 output 文件夹" + file path)

    For slides always use format='html', never format='markdown'. The content parameter must be the full HTML—never empty or a short fragment. Return the link to the user.

    Speaker notes: add data-notes="..." attribute to each slide div, e.g. <div class="slide" data-notes="Talking point for this slide">. This enables swipe-up reveal in the viewer.

    Aspect ratio: default is 9:16 (portrait). For 16:9 landscape, add ?ratio=16/9 to the viewer URL or add data-ratio="16/9" to each slide.

    If they want standard .pptx only, use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=['--capability', 'outline'|'source'|'presentation'|'documents', ...]) instead.
---

# HTML Slides（乔布斯风竖屏单页演示）

将讲稿转换为乔布斯风极简科技感竖屏**单页 HTML** 演示（非 PPT）。输出为单个 HTML 文件，保存到用户或伴侣的 output 文件夹并返回可打开链接。

## 设计哲学

- **极简主义** - 一屏只讲一件事
- **强视觉对比** - 深色背景 + 白色文字
- **高留白** - 禁止密集排版
- **强节奏感** - 让观众想继续看

## 生成流程（必须严格遵循）

### Step 1: 读取讲稿
读取用户原始讲稿，不修改原稿内容。

### Step 2: 生成提炼版讲稿（内部使用，不输出）
将内容精简、增强冲击力、适配演示场景，输出 Markdown 格式。**此步骤仅供 AI 内部生成参考，不要展示给用户。**

### Step 3: 生成乔布斯风标题
为每个章节生成标题，必须满足：
- ≤12 字
- 采用以下形式之一：对比式、问题式、断言式、数字式、比喻式
- 自检：是否让人想继续听？

### Step 4: 设计幻灯片结构（内部使用，不输出）
规划页面顺序和类型，参考 [references/slide-types.md](references/slide-types.md)。**此步骤仅供 AI 内部规划，不要展示给用户。**

### Step 5: 生成HTML
使用 [assets/template.html](assets/template.html) 作为基础模板生成完整HTML。**禁止将 HTML 代码粘贴到聊天中——只生成完整 HTML 并保存。**

### Step 6: 保存并回复链接（必须执行，且唯一输出）
- 使用 **file_write** 或 **save_result_page** 将完整 HTML 保存到 **output/** 下（路径格式 `output/<标题或日期>_slides.html`），这样文件会进入当前用户或伴侣的 output 文件夹。
- 若使用 **save_result_page**：`format=html`，`content=` 完整 HTML 内容，`title=` 演示标题；工具会返回可打开链接，把该链接回复给用户。
- 若使用 **file_write**：`path=output/xxx.html`，`content=` 完整 HTML；写完后告知用户"已保存到您的 output 文件夹"。
- **用户只会看到这一句话**，不展示中间过程。

## 输出规则（唯一须遵守）

> **只回复用户保存成功的信息和链接。不要输出提炼讲稿、幻灯片大纲或 HTML 代码。**

## 视觉规范速查

| 项目 | 规范 |
|------|------|
| 比例 | 9:16 竖屏（默认）；16:9 横屏（`?ratio=16/9`） |
| 背景 | #000000 或 #0a0a0a + 模糊光斑动画 |
| 主文字 | #ffffff |
| 辅助文字 | #9ca3af |
| 中文字体 | Noto Sans SC |
| 英文字体 | Inter |
| 标题字重 | font-black / font-bold |
| 正文字重 | font-light / font-normal |

详细规范见 [references/design-spec.md](references/design-spec.md)。

## 交互功能

| 功能 | 操作 |
|------|------|
| 翻页 | 键盘 ← → 或 触摸左右滑动 |
| 进度导航 | 点击底部圆点 |
| 暗/亮模式 | 点击右上角 ☀/🌙 按钮 |
| 演讲者备注 | 向上滑动当前幻灯片查看（需 slide 有 data-notes 属性） |
| 横屏模式 | URL 加 `?ratio=16/9` 参数 |
| PDF 导出 | 浏览器打印 → 保存为 PDF |

## 技术栈

- TailwindCSS 3.4（jsDelivr CDN）
- Google Fonts（Noto Sans SC + Inter）
- 单个HTML文件，可直接打开运行

## 严禁行为

- 堆字 / 密集排版
- 花哨配色
- 复杂图表
- 偏离极简科技风
- 在聊天中输出 HTML 代码、Markdown 讲稿或幻灯片大纲

## 默认规则

- 未指定页数：自动生成 8~20 页
- 未指定风格：默认乔布斯风
- 未指定备注：每页可不加 data-notes
