# 设计规范详细文档

## 暗亮模式

模板使用 CSS 变量支持暗/亮模式切换：

```css
:root {
  --bg-primary: #0a0a0a;
  --bg-secondary: #000000;
  --text-primary: #ffffff;
  --text-secondary: #9ca3af;
  --spot-opacity: 0.3;
}

body.light {
  --bg-primary: #f8f8f8;
  --bg-secondary: #ffffff;
  --text-primary: #111111;
  --text-secondary: #6b7280;
  --spot-opacity: 0.15;
}
```

**文字颜色规范（支持暗/亮切换）：**
- 主文字：直接使用 `#ffffff`（暗色背景时）或 CSS 变量 `var(--text-primary)`
- 辅助文字：使用 `style="color: var(--text-secondary)"` 而非 Tailwind 硬编码灰度类
- 金句引号：使用 `style="color: var(--text-secondary); opacity: 0.4"`

## 背景效果

### 主背景
- 主色：CSS 变量 `--bg-primary` / `--bg-secondary`（暗色默认 #0a0a0a / #000000）
- 深色渐变底色通过 `linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 100%)` 实现

### 动态光斑（必须包含）
每页必须包含 1~3 个模糊光斑，透明度使用 CSS 变量：

```css
.light-spot {
  position: absolute;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  filter: blur(100px);
  opacity: var(--spot-opacity);  /* 暗 0.3 / 亮 0.15 */
  animation: float 20s ease-in-out infinite;
  pointer-events: none;
}

.light-spot-1 { background: #3b82f6; }  /* 蓝色 */
.light-spot-2 { background: #8b5cf6; }  /* 紫色 */
.light-spot-3 { background: #06b6d4; }  /* 青色 */

@keyframes float {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(-50px, 30px); }
  50% { transform: translate(30px, 50px); }
  75% { transform: translate(50px, -20px); }
}
```

## 字体加载

```html
<!-- Google Fonts（Noto Sans SC + Inter） -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;700;900&family=Noto+Sans+SC:wght@300;400;700;900&display=swap" rel="stylesheet">
```

## 排版层级

```css
/* H1 超大标题 */
.slide-title {
  font-size: 3rem;      /* 48px */
  font-weight: 900;     /* font-black */
  line-height: 1.2;
  color: var(--text-primary);
}

/* H2 副标题 */
.slide-subtitle {
  font-size: 1.5rem;    /* 24px */
  font-weight: 700;     /* font-bold */
  color: var(--text-primary);
}

/* P 说明文字 */
.slide-text {
  font-size: 1.125rem;  /* 18px */
  font-weight: 300;     /* font-light */
  color: var(--text-secondary);
}
```

## 间距规范

- 元素间距：space-y-8 以上（32px+）
- 页面内边距：p-8 或 p-12
- 内容居中：flex items-center justify-center

## 页面容器

```css
.slide {
  width: 100%;
  height: 100%;
  aspect-ratio: 9/16;  /* 默认竖屏 */
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  background: linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
}

/* 横屏 16:9 */
.slide[data-ratio="16/9"] {
  aspect-ratio: 16/9;
  max-width: 800px;
}
```

## 切换动画

```css
.slide {
  opacity: 0;
  transform: translateX(100%);
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide.active {
  opacity: 1;
  transform: translateX(0);
}

.slide.prev {
  opacity: 0;
  transform: translateX(-100%);
}
```

## 演讲者备注

每页可添加 `data-notes` 属性：

```html
<div class="slide" data-notes="这里的演讲者备注内容，向上滑动可查看。">
  ...
</div>
```

CSS 变量式正文颜色替代硬编码 Tailwind 灰度类：

| 效果 | 推荐写法 |
|------|---------|
| 辅助/次要文字 | `style="color: var(--text-secondary)"` |
| 引号装饰 | `style="color: var(--text-secondary); opacity: 0.4"` |
| 引用出处 | `style="color: var(--text-secondary); opacity: 0.6"` |
| 主文字（暗背景） | 直接用白色 `#ffffff` 或 `text-white` |
