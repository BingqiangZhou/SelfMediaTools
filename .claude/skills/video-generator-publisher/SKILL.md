---
name: video-generator-publisher
description: 用于生成自媒体短视频并支持发布到抖音。当用户需要将文本转换为带TTS语音和背景音乐的视频时使用此技能。支持竖屏(1080x1920)和横屏(1920x1080)两种输出格式。**当用户未提供文案时，自动生成"共鸣向上、温暖励志"风格的文案内容**。视频生成后可选择自动发布到抖音创作者平台，发布时支持选择视频首帧作为封面，支持标题和文案内容填写、不允许下载设置等功能。触发场景：用户提到"生成视频"、"制作视频"、"text to video"、"TTS视频"、"自媒体视频"、"短视频生成"、"发布视频"、"上传抖音"、"生成文案"、"选择封面"等，或直接要求运行视频生成脚本。
---

# 自媒体短视频生成器

此技能用于将文本内容自动转换为带TTS语音和背景音乐的短视频。

## 子代理协调流程

本技能采用**子代理架构**，由主协调器按顺序调用各子代理：

```
content-agent → config-agent → video-agent → publish-agent (可选)
```

### 子代理说明

| 子代理 | 职责 | 输入 | 输出 |
|--------|------|------|------|
| `content-agent` | 文案生成与确认 | text/text_file(可选) | 确认后的文案、主题关键词 |
| `config-agent` | 配置验证与确认 | 配置参数 | 验证后的配置、CLI参数 |
| `video-agent` | 视频生成执行 | 文案、CLI参数 | 视频文件路径 |
| `publish-agent` | 抖音发布 | 视频路径、文案 | 发布结果 |

### 协调器逻辑

每个代理返回 `AgentResult`，协调器根据结果决定下一步操作：

- `success=True` + `next_action="continue"` → 继续下一个代理
- `success=False` → 记录错误，询问用户重试或中止
- `next_action="confirm_*"` → 询问用户，处理响应后继续

**详细文档**: 参见 `AGENTS.md` 了解各子代理的接口定义和行为。

## 功能模式

### 1. 文案输入模式
用户提供文案内容（通过 `text` 或 `text_file` 参数），直接生成视频。

### 2. 自动文案生成模式（默认）
当用户未提供文案时，自动生成"共鸣向上、温暖励志"风格的文案内容。

## 前置检查

在开始之前，确保系统已安装：
- **FFmpeg**: 视频处理工具
- **uv**: Python 包管理器和运行器（用于执行代码）
- **Azure TTS**: 语音合成服务（需要API密钥或使用edge-tts）

检查项目路径是否存在：
- 项目路径: `E:/Projects/Works/SelfMediaTools`

**默认配置文件**: `configs/config.yaml`

## 执行流程

### 概述

本技能通过顺序调用4个子代理完成视频生成和发布流程：

```
用户输入 → content-agent → config-agent → video-agent → publish-agent (可选)
```

### 步骤1: 调用 content-agent（文案生成与确认）

使用 Task 工具调用 content-agent：

```
<parameter name="prompt">阅读 .claude/skills/video-generator-publisher/agents/content-agent.md 并严格按照指示执行。传入以下参数：
- text: {用户提供的文案或null}
- text_file: {文案文件路径或null}
- auto_generate: {是否自动生成，true如果用户未提供文案}

返回格式必须包含 success、data（text、theme_keyword）、message 字段。</parameter>
<parameter name="subagent_type">general-purpose</parameter>
```

**预期输出**:
```json
{
  "success": true,
  "data": {
    "text": "确认后的文案内容",
    "theme_keyword": "破局",
    "auto_generated": false
  }
}
```

将输出保存到工作上下文：`content_text`、`theme_keyword`

### 步骤2: 调用 config-agent（配置验证与确认）

使用 Task 工具调用 config-agent：

```
<parameter name="prompt">阅读 .claude/skills/video-generator-publisher/agents/config-agent.md 并严格按照指示执行。传入以下参数：
- text: {content_text}
- theme_keyword: {theme_keyword}
- config_file: null
- user_wants_modify: null

返回格式必须包含 success、data（validated_config、cli_args）、message 字段。</parameter>
<parameter name="subagent_type">general-purpose</parameter>
```

**预期输出**:
```json
{
  "success": true,
  "data": {
    "validated_config": {...},
    "cli_args": ["uv", "run", "main.py", "--config", "configs/1.yaml", "--text", "...", "--theme-keyword", "..."]
  }
}
```

将输出保存到工作上下文：`cli_args`

### 步骤3: 调用 video-agent（视频生成执行）

使用 Task 工具调用 video-agent：

```
<parameter name="prompt">阅读 .claude/skills/video-generator-publisher/agents/video-agent.md 并严格按照指示执行。传入以下参数：
- cli_args: {cli_args}
- text: {content_text}
- theme_keyword: {theme_keyword}

项目路径: E:/Projects/Works/SelfMediaTools

返回格式必须包含 success、data（output_dir、video_paths、timestamp）、message 字段。</parameter>
<parameter name="subagent_type">general-purpose</parameter>
```

**预期输出**:
```json
{
  "success": true,
  "data": {
    "output_dir": "E:/Projects/Works/SelfMediaTools/output/run_20250302_143022",
    "video_paths": [".../final_portrait.mp4", ".../final_landscape.mp4"],
    "timestamp": "20250302_143022"
  },
  "message": "视频生成完成！..."
}
```

将输出保存到工作上下文：`video_paths`、`output_dir`

### 步骤4: 询问是否发布到抖音

使用 AskUserQuestion 工具询问用户：

**问题**: "视频已生成完成！是否要将视频发布到抖音创作者平台？"
- 选项: "是，发布到抖音" / "否，暂时不发布"

如果用户选择"否"，结束流程。

### 步骤5: 调用 publish-agent（抖音发布，可选）

如果用户选择发布，使用 Task 工具调用 publish-agent：

```
<parameter name="prompt">阅读 .claude/skills/video-generator-publisher/agents/publish-agent.md 并严格按照指示执行。传入以下参数：
- video_path: {优先选择竖屏视频路径}
- original_text: {content_text}

可以使用以下 Chrome DevTools MCP 工具：
- mcp__chrome-devtools__new_page
- mcp__chrome-devtools__take_snapshot
- mcp__chrome-devtools__upload_file
- mcp__chrome-devtools__fill
- mcp__chrome-devtools__click
- mcp__chrome-devtools__wait_for
- mcp__chrome-devtools__type_text

返回格式必须包含 success、data（published、url）、message 字段。</parameter>
<parameter name="subagent_type">general-purpose</parameter>
```

**预期输出**:
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

## 输出目录结构

视频输出到以下目录结构：

```
output/run_YYYYMMDD_HHMMSS/
├── 01_sentences/      # 分割后的句子
├── 02_images/         # 渲染的图片
│   ├── portrait/      # 竖屏图片（含封面）
│   └── landscape/     # 横屏图片（含封面）
├── 03_audio/          # TTS音频文件
├── 04_segments/       # 视频片段
│   ├── portrait/      # 竖屏片段
│   └── landscape/     # 横屏片段
└── 05_final/          # 最终视频
    ├── final_portrait.mp4    # 竖屏成品
    └── final_landscape.mp4   # 横屏成品
```

## 错误处理

### 子代理调用失败

当子代理返回 `success: false` 时：

1. 检查返回的 `error` 或 `message` 字段
2. 向用户显示错误信息
3. 根据错误类型提供解决建议：
   - **文件不存在**: 检查文件路径
   - **配置错误**: 引导用户修改配置
   - **视频生成失败**: 检查 FFmpeg、字体等环境
   - **发布失败**: 保存视频，建议手动发布

### 重试机制

对于可重试的错误，询问用户是否重试当前步骤。

**注意**: 发布流程的详细步骤（包括标题生成、内容生成、上传视频、选择封面、发布设置等）已在 `agents/publish-agent.md` 中定义。publish-agent 会自动处理所有步骤。

## 自动文案生成

当用户未提供 `text` 和 `text_file` 参数时，进入自动文案生成模式。

### 文案生成

使用以下提示词生成文案：

**角色**: 写出让人看到自己、相信命运、感受向上的力量的文案创作者

**输出结构**:
```
标题：xxx（10-20字，有画面感、戳心、点题）
关键词：xxx（2-4字，贴近命运/转折/逆风/破局/新生/馈赠/绽放）
文案：xxx（80-120字）
```

**文案结构要求**:
- **第一句必须是标题内容**：直接用标题或其变体作为文案开篇，立即点题
- **先点题，再展开**：开篇点明主题，然后用具体画面和感受来诠释
- **结尾向上**：以希望、力量、光明的意象收尾

**核心原则**:
- **写"看到"，不写"做到"**: 让读者在文案中看到自己的影子、自己的经历、自己的情绪，而不是告诉他该怎么做
- **写"命运"，不写"道理"**: 聚焦命运的安排、转折、馈赠，用命运的语言说话，而不是讲成功学道理
- **写"力量"，不写"方法"**: 传递向上的能量和信念，而不是给方法或步骤
- **写"原来"，不写"应该"**: 用"原来...""原来...也可以"这样的顿悟感，而不是"你应该..."的说教感
- **用画面说话**: 用具体场景和自然意象（深夜的灯、破土的种子、逆风的风、黎明的光、远方的路、绽放的花）

**命运与成功主题库**（作为创作源泉）:
- 命运从不会丢下每一个认真用力的人
- 所有的弯路，都是命运在为你绕远去遇见更好的风景
- 那些暗处里的坚持，命运都替你记着
- 命运给你的每一次打击，都是在为你日后的荣光积攒弹药
- 你以为的运气，是命运在偷偷奖励不肯认输的你
- 命运的馈赠，从来都包装成困难的模样
- 每一个咬牙坚持的瞬间，都是命运在为你铺路
- 你不是运气不好，只是成功还在赶来的路上
- 命运会奖励每一个不肯低头的人
- 所有的至暗时刻，都是为了迎接破晓的光

**禁用词汇清单**（绝对不要用）:
- 命令式：应该、必须、要、一定得、务必、千万、请、不要
- 指导式：教你、告诉你、建议你、你要学会、需要、如何、怎么
- 评判式：这样做不对、你应该这样、更好的方式是、才能成功
- 说教式：只有...才能...、只要...就...、努力就会...、坚持就会...
- 方法式：首先、其次、最后、第一步、接下来、方法、技巧

**推荐表达方式**:
- 用"原来..."代替"你应该..."
- 用"有人..."代替"你要..."
- 用"那些...的人"代替"你要成为..."
- 用"命运..."代替"成功需要..."
- 用"会..."代替"你要..."
- 用"终会..."代替"只要...就..."
- 用"正在..."代替"你要开始..."

**风格要求**: 共鸣、温暖、有力量、向上。聚焦命运转折与成功主题，让读者看到自己的影子，感受到命运在冥冥中的安排，相信未来会更好。多用描述性语言，避免说教式指导。结尾要有光、有希望、有力量。

**参考示例**:
```
标题：那些咬牙的夜晚，命运都替你记着
关键词：馈赠
文案：那些咬牙的夜晚，命运都替你记着。凌晨两点的台灯下，有人还在死磕。不是不累，只是心里有团火灭不掉。那些独自吞下的委屈，那些被说"不合适"的倔强，命运都在悄悄替你攒着。你以为的无人问津，其实是命运在为你蓄力。所有不被看见的日子，都是为了被更好地看见。
```

```
标题：命运给你关的门，是在等你开窗
关键词：破局
文案：命运给你关的门，是在等你开窗。有人说你这辈子就这样了，你偏不信。那些被嘲笑的坚持，那些被否定的选择，原来都是命运在为你转场。你以为走进了死胡同，其实只是命运在等你换条路。继续走下去，前面有光。
```

```
标题：所有的好运，都是命运在偷偷奖励你
关键词：厚积
文案：所有的好运，都是命运在偷偷奖励你。别人看不见的时候，你还在发光。那些无人问津的努力，那些咬牙不放弃的瞬间，命运都没有忘记。你以为的运气不好，其实只是时间还没到。星光从来不会辜负每一个认真赶路的人。你的名字，会被命运写在最好的位置。
```

```
标题：你现在的至暗时刻，是命运在为你铺路
关键词：黎明
文案：你现在的至暗时刻，是命运在为你铺路。有人看不见光，但心里有灯。那些跌倒后的爬起，那些被否定后的重头再来，都是命运在为你积攒向上的力量。你以为是终点，其实只是起点。前面就是黎明。
```

### 执行流程

1. 生成文案 → 展示给用户
2. 询问确认：满意使用 / 重新生成 / 手动修改
3. 提取参数：`--theme-keyword` 关键词，`--text` 文案内容（标题不传给视频程序）

## 配置速查表

### 完整CLI参数列表

| 配置项 | CLI参数 | 说明 | 默认值 |
|--------|---------|------|--------|
| **输入** | | | |
| text | `--text` | 文案内容 | 无 |
| text_file | `--text-file` | 文案文件路径 | 无 |
| **TTS设置** | | | |
| voice | `--voice` | TTS语音 | zh-CN-XiaoxiaoNeural |
| rate | `--rate` | 语速 | +0% |
| volume | `--volume` | 音量 | +0% |
| tts_start_offset | `--tts-start-offset` | TTS起始偏移(秒) | 1.0 |
| tts_workers | `--tts-workers` | TTS并发数 | 4 |
| **输出设置** | | | |
| output_modes | `--output-modes` | 输出模式(竖屏/横屏) | portrait,landscape |
| portrait_size | `--portrait-size` | 竖屏尺寸 | 1080x1920 |
| landscape_size | `--landscape-size` | 横屏尺寸 | 1920x1080 |
| fps | `--fps` | 帧率 | 30 |
| work_dir | `--work-dir` | 工作目录 | . |
| **渲染设置** | | | |
| font_path | `--font-path` | 字体文件路径 | 自动检测Windows字体 |
| font_size | `--font-size` | 字体大小 | 72 |
| min_font_size | `--min-font-size` | 最小字体大小 | 28 |
| line_spacing | `--line-spacing` | 行间距 | 1.25 |
| text_margin_x | `--text-margin-x` | 水平边距 | 80 |
| text_margin_y | `--text-margin-y` | 垂直边距 | 60 |
| bg_color | `--bg-color` | 背景色 | #000000 |
| text_color | `--text-color` | 主文字颜色 | #FFFFFF |
| text_colors | `--text-colors` | 文字颜色序列（逗号分隔） | #FFD700,#00BFFF,#FF6347,#7CFC00 |
| text_effects | `--text-effects` | 文字效果序列（逗号分隔） | fadein,slide_left,slide_right,slide_top,slide_bottom |
| effect_duration | `--effect-duration` | 特效持续时间(秒) | 0.5 |
| **BGM设置** | | | |
| bgm_enabled | `--bgm-enabled` | 是否启用BGM | false |
| bgm_file | `--bgm-file` | BGM文件路径 | 无 |
| bgm_volume | `--bgm-volume` | BGM音量(0-1) | 0.18 |
| bgm_fade_in | `--bgm-fade-in` | BGM淡入时长(秒) | 1.5 |
| bgm_fade_out | `--bgm-fade-out` | BGM淡出时长(秒) | 1.5 |
| bgm_audio_bitrate | `--bgm-audio-bitrate` | BGM音频比特率 | 192k |
| **封面设置** | | | |
| theme_keyword | `--theme-keyword` | 主题关键词 | 天命之人(默认) |
| cover_enabled | `--cover-enabled` | 是否启用封面 | true |
| cover_bg_color | `--cover-bg-color` | 封面背景色 | #000000 |
| cover_text_color | `--cover-text-color` | 封面文字颜色 | #D00000 |
| **并发设置** | | | |
| clip_workers | `--clip-workers` | 视频片段并发数 | 2 |

### 输出尺寸
- 竖屏: 1080x1920 (抖音/快手等)
- 横屏: 1920x1080 (B站/YouTube等)

### 常用语音 (Azure)
- `zh-CN-XiaoxiaoNeural` - 女声，温柔
- `zh-CN-YunxiNeural` - 男声，稳重
- `zh-CN-YunyangNeural` - 男声，年轻
- `zh-CN-XiaoyiNeural` - 女声，活泼

### 语速调整
- `+0%` = 正常
- `+10%` = 稍快
- `-10%` = 稍慢

### BGM音量建议
- 0.10-0.15: 较轻的背景音
- 0.18-0.25: 平衡（推荐）
- 0.30-0.40: 较明显的背景音

## 故障排查

如果执行失败，检查以下内容：

1. **FFmpeg未安装**: 提示安装FFmpeg
2. **字体文件不存在**: 检查font_path路径，或让系统自动检测Windows字体
3. **TTS失败**: 检查网络连接和API密钥
4. **BGM文件不存在**: 检查bgm_file路径
5. **内存不足**: 减少tts_workers/clip_workers的值

## 示例对话

**场景1 - 无文案（自动生成）**:
用户: "生成一个视频"
→ 生成文案 → 展示确认 → 用户满意 → 执行视频生成

**场景2 - 有文案（直接使用）**:
用户: "生成视频，文案是：xxx"
→ 直接执行：`uv run main.py --config configs/config.yaml --text "xxx"`

## Theme Keyword Cover Update (2026-03)

- After generating title/content, summarize one 2-6 Chinese character theme keyword from the source text.
- Pass it to the video pipeline by CLI:

```bash
uv run main.py --config configs/config.yaml --theme-keyword "<关键词>"
```

- CLI mapping addition:
- `theme_keyword` -> `--theme-keyword`
- If keyword is empty, pipeline falls back to `天命之人`.
