# Video Generator Publisher - 子代理定义

本文档定义了 video-generator-publisher 技能的所有子代理。每个子代理是一个独立的 Agent，通过 Task 工具调用。

## 架构概述

本技能采用**子代理架构**，将复杂工作流拆分为独立的代理：

```
主协调器 (SKILL.md)
    ├── content-agent (文案生成与确认)
    ├── config-agent (配置验证与确认)
    ├── video-agent (视频生成执行)
    └── publish-agent (抖音发布)
```

## 调用方式

### 在 SKILL.md 中调用子代理

```markdown
## 步骤1: 文案生成与确认

使用 Task 工具调用 content-agent：

<parameter name="prompt">根据以下输入生成或确认文案...</parameter>
<parameter name="subagent_type">general-purpose</parameter>
<parameter name="context">
{
  "text": "用户提供的文案或null",
  "text_file": "文件路径或null",
  "auto_generate": true
}
</parameter>
```

### 子代理文件位置

每个子代理的 prompt 定义在 `agents/` 目录下：

```
.claude/skills/video-generator-publisher/agents/
├── content-agent.md   # 文案代理 prompt
├── config-agent.md    # 配置代理 prompt
├── video-agent.md     # 视频代理 prompt
└── publish-agent.md   # 发布代理 prompt
```

## 代理列表

### 1. content-agent - 文案生成与确认代理

**Prompt 文件**: `agents/content-agent.md`

**职责**:
- 检测输入模式（文案输入 vs 自动生成）
- 自动生成"共鸣向上、温暖励志"风格的文案
- 提取主题关键词（2-6字）
- 与用户确认文案内容

**输入参数**:
```json
{
  "text": "string | null",
  "text_file": "string | null",
  "auto_generate": boolean
}
```

**输出结果**:
```json
{
  "success": true,
  "data": {
    "text": "确认后的文案内容",
    "theme_keyword": "提炼的关键词（2-6字）",
    "auto_generated": false
  },
  "message": "使用用户提供的文案"
}
```

**用户交互**:
- 询问用户对生成文案的满意度
- 选项：满意使用 / 重新生成 / 手动修改

---

### 2. config-agent - 配置验证与确认代理

**Prompt 文件**: `agents/config-agent.md`

**职责**:
- 加载默认配置
- 询问用户是否需要修改配置
- 验证资源配置（字体、BGM等）
- 构建 CLI 参数列表

**输入参数**:
```json
{
  "text": "string",
  "theme_keyword": "string",
  "config_file": "string | null",
  "user_wants_modify": "boolean | null",
  "modifications": "object | null"
}
```

**输出结果**:
```json
{
  "success": true,
  "data": {
    "validated_config": {...},
    "cli_args": ["uv", "run", "main.py", "--config", "...", "--text", "..."]
  },
  "message": "配置验证通过"
}
```

**配置分组**:
- **TTS 设置**: voice, rate, volume, tts_start_offset
- **输出设置**: output_modes, portrait_size, landscape_size, fps
- **渲染设置**: font_path, font_size, colors 等
- **BGM 设置**: bgm_enabled, bgm_file, bgm_volume 等

---

### 3. video-agent - 视频生成执行代理

**Prompt 文件**: `agents/video-agent.md`

**职责**:
- 执行 `uv run main.py` 命令
- 监控执行进度
- 解析输出目录和视频文件路径
- 返回生成结果

**输入参数**:
```json
{
  "cli_args": ["uv", "run", "main.py", ...],
  "text": "string",
  "theme_keyword": "string"
}
```

**输出结果**:
```json
{
  "success": true,
  "data": {
    "output_dir": "output/run_20250302_143022",
    "video_paths": [
      "output/run_20250302_143022/05_final/final_portrait.mp4",
      "output/run_20250302_143022/05_final/final_landscape.mp4"
    ],
    "timestamp": "20250302_143022"
  },
  "message": "视频生成完成！"
}
```

**输出目录结构**:
```
output/run_YYYYMMDD_HHMMSS/
├── 01_sentences/      # 分割后的句子
├── 02_images/         # 渲染的图片
├── 03_audio/          # TTS音频文件
├── 04_segments/       # 视频片段
└── 05_final/          # 最终视频
    ├── final_portrait.mp4    # 竖屏成品
    └── final_landscape.mp4   # 横屏成品
```

---

### 4. publish-agent - 抖音发布代理

**Prompt 文件**: `agents/publish-agent.md`

**职责**:
- 根据原始文案生成标题和发布内容
- 与用户确认标题和内容
- 使用 Chrome DevTools 上传视频到抖音
- 填写发布信息并提交

**输入参数**:
```json
{
  "video_path": "path/to/final_portrait.mp4",
  "original_text": "原始文案内容"
}
```

**输出结果**:
```json
{
  "success": true,
  "data": {
    "published": true,
    "url": "https://creator.douyin.com/..."
  },
  "message": "发布成功！"
}
```

**发布工作流**:
1. 导航到抖音创作者平台
2. 上传视频文件
3. 填写标题和文案内容
4. 选择竖封面(3:4)和横封面(4:3)
5. 设置不允许下载
6. 提交发布

---

## 执行流程

### 主协调器在 SKILL.md 中的流程

```markdown
## 执行流程

### 步骤1: 文案生成与确认

调用 content-agent 处理文案...

### 步骤2: 配置确认

调用 config-agent 验证配置...

### 步骤3: 视频生成

调用 video-agent 生成视频...

### 步骤4: 发布到抖音（可选）

询问用户是否发布，如需发布则调用 publish-agent...
```

### 状态传递

每个代理的输出作为下一个代理的输入：

```
用户输入
  ↓
content-agent → {text, theme_keyword}
  ↓
config-agent → {cli_args}
  ↓
video-agent → {video_paths}
  ↓
publish-agent → {published}
```

---

## 错误处理

### 代理执行失败

当子代理返回 `success: false` 时：

1. 检查 `error` 字段获取错误信息
2. 根据错误类型决定：
   - 可重试错误（如网络问题）→ 询问用户是否重试
   - 配置错误 → 引导用户修正配置
   - 严重错误 → 中止流程并显示错误

### 错误恢复策略

| 错误类型 | 处理方式 |
|---------|---------|
| 文件不存在 | 提示用户检查文件路径 |
| 配置验证失败 | 显示具体配置项，引导修改 |
| 视频生成失败 | 显示错误日志，建议解决方案 |
| 发布失败 | 保存视频，建议手动发布 |

---

## 独立测试

每个子代理可以独立测试：

### 测试 content-agent

```
用户：帮我生成一个励志文案
→ 调用 content-agent，参数 {"auto_generate": true}
→ 返回生成的文案和关键词
```

### 测试 config-agent

```
用户：使用默认配置
→ 调用 config-agent，参数 {"text": "...", "theme_keyword": "..."}
→ 返回 CLI 参数列表
```

### 测试 video-agent

```
用户：生成视频，文案是：测试文案
→ 调用 video-agent，参数 {"cli_args": [...]}
→ 返回视频文件路径
```

---

## Chrome DevTools MCP 工具

publish-agent 使用以下工具：

| 工具 | 用途 |
|-----|------|
| `new_page` | 创建新页面并导航到抖音 |
| `take_snapshot` | 获取页面快照查找元素 |
| `upload_file` | 上传视频文件 |
| `fill` | 填写表单字段 |
| `type_text` | 输入文本内容 |
| `click` | 点击元素 |
| `wait_for` | 等待特定文本出现 |

---

## 扩展指南

### 添加新子代理

1. 在 `agents/` 目录创建新的 `.md` 文件
2. 定义代理的职责、输入输出格式
3. 在 SKILL.md 中添加调用步骤
4. 更新此文档

### 修改现有代理

1. 直接编辑对应的 `.md` 文件
2. 更新输入输出格式
3. 同步更新 SKILL.md 中的调用方式
