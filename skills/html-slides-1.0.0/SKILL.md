---
name: html-slides
description: "Generate a 乔布斯-style minimal vertical single-page HTML presentation from the user's script (single file, open in browser). Use this skill when the user asks for 乔布斯/极简/竖屏/HTML slides. For standard PowerPoint (.pptx) use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...]). Output goes to user/companion output folder; return the open link."
trigger:
  patterns: ["乔布斯|极简.*演示|竖屏.*演示|HTML.*演示|单页.*演示|极简.*幻灯片|乔布斯.*幻灯片|HTML\\s*slides|html\\s*slides|html\\s*slide|生成.*HTML.*[Ss]lides|生成.*幻灯片|总结.*html|生成.*html.*slide|乔布斯.*极简|极简.*乔布斯"]
  instruction: "The user asked for 乔布斯-style, 极简, or HTML presentation/slides from a document. You HAVE the html-slides skill: (1) document_read(path) to get the file content, (2) use that text to generate the full HTML (all slides), (3) call save_result_page(title=..., content=<the full HTML you generated>, format='html') or file_write(path='output/...', content=<full HTML>). For slides always use format='html', never format='markdown'. The content parameter must be the full HTML—never empty or a short fragment. Return the link to the user. If they want standard .pptx only, use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=['--capability', 'outline'|'source'|'presentation'|'documents', ...]) instead."
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

### Step 2: 生成提炼版讲稿
将内容精简、增强冲击力、适配演示场景，输出 Markdown 格式。

### Step 3: 生成乔布斯风标题
为每个章节生成标题，必须满足：
- ≤12 字
- 采用以下形式之一：对比式、问题式、断言式、数字式、比喻式
- 自检：是否让人想继续听？

### Step 4: 设计幻灯片结构
规划页面顺序和类型，参考 [references/slide-types.md](references/slide-types.md)。

### Step 5: 生成HTML
使用 [assets/template.html](assets/template.html) 作为基础模板生成完整HTML。

### Step 6: 填充内容
添加动态背景光斑、交互逻辑、平滑切换动画。

### Step 7: 保存到 output 并返回链接（必须执行）
- 使用 **file_write** 或 **save_result_page** 将完整 HTML 保存到 **output/** 下（路径格式 `output/<标题或日期>_slides.html`），这样文件会进入当前用户或伴侣的 output 文件夹。
- 若使用 **save_result_page**：`format=html`，`content=` 完整 HTML 内容，`title=` 演示标题；工具会返回可打开链接，把该链接回复给用户。
- 若使用 **file_write**：`path=output/xxx.html`，`content=` 完整 HTML；写完后告知用户“已保存到您的 output 文件夹”，并可说明可通过“打开 output 文件夹”或报告链接查看。

## 输出顺序（必须依次输出）

1. **提炼后的讲稿**（Markdown）
2. **幻灯片结构大纲**
3. **完整HTML代码**
4. **保存到 output 并回复链接或路径说明**

## 视觉规范速查

| 项目 | 规范 |
|------|------|
| 比例 | 9:16 竖屏 |
| 背景 | #000000 或 #0a0a0a + 模糊光斑动画 |
| 主文字 | #ffffff |
| 辅助文字 | #9ca3af |
| 中文字体 | HarmonyOS Sans SC / 思源黑体 |
| 英文字体 | Inter / Roboto |
| 标题字重 | font-black / font-bold |
| 正文字重 | font-light / font-normal |

详细规范见 [references/design-spec.md](references/design-spec.md)。

## 交互要求

- 键盘 ← → 翻页
- 底部进度导航条
- 平滑切换动画

## 技术栈

- TailwindCSS（国内CDN）
- 复杂页面使用 Vue3（CDN）
- 单个HTML文件，可直接打开运行

## 严禁行为

- 堆字 / 密集排版
- 花哨配色
- 复杂图表
- 横屏比例
- 偏离极简科技风

## 默认规则

- 未指定页数：自动生成 8~20 页
- 未指定风格：默认乔布斯风
