---
name: video-generator
description: 用于生成自媒体短视频。当用户需要将文本转换为带TTS语音和背景音乐的视频时使用此技能。支持竖屏(1080x1920)和横屏(1920x1080)两种输出格式。触发场景：用户提到"生成视频"、"制作视频"、"text to video"、"TTS视频"、"自媒体视频"、"短视频生成"等，或直接要求运行视频生成脚本。
---

# 自媒体短视频生成器

此技能用于将文本内容自动转换为带TTS语音和背景音乐的短视频。

## 前置检查

在开始之前，确保系统已安装：
- **FFmpeg**: 视频处理工具
- **uv**: Python 包管理器和运行器（用于执行代码）
- **Azure TTS**: 语音合成服务（需要API密钥或使用edge-tts）

检查项目路径是否存在：
- 项目路径: `E:/Projects/Works/SelfMediaTools`

**默认配置文件**: `configs/1.yaml`

## 执行流程

### 步骤1: 展示并确认配置

**首先**，使用 `AskUserQuestion` 工具向用户展示所有默认配置设置，并询问是否需要修改。

按以下分组展示配置（使用多选问题）：

#### A. 输入设置
- **text**: 直接输入的文本内容（null表示使用文件）
- **text_file**: 输入文本文件路径

#### B. TTS语音设置
- **voice**: 语音名称（默认: zh-CN-XiaoxiaoNeural）
- **rate**: 语速（默认: +0%，范围: -50% 到 +100%）
- **volume**: 音量（默认: +0%，范围: -50% 到 +100%）
- **tts_start_offset**: 首段开始延迟秒数（默认: 1.0）

#### C. 输出设置
- **output_modes**: 输出模式（portrait=竖屏, landscape=横屏，默认两者）
- **portrait_size**: 竖屏尺寸（默认: 1080x1920）
- **landscape_size**: 横屏尺寸（默认: 1920x1080）
- **fps**: 帧率（默认: 30）

#### D. 并发设置
- **tts_workers**: TTS并发数（默认: 4）
- **image_workers**: 图片渲染并发数（默认: 4）
- **clip_workers**: 视频片段并发数（默认: 2）

#### E. 文字卡片样式
- **font_path**: 字体文件路径（默认: C:/Windows/Fonts/msyh.ttc）
- **font_size**: 字体大小（默认: 72）
- **min_font_size**: 最小字体大小（默认: 28）
- **line_spacing**: 行间距（默认: 1.25）
- **text_margin_x**: 文字水平边距（默认: 80）
- **text_margin_y**: 文字垂直边距（默认: 60）
- **bg_color**: 背景颜色（默认: #000000 黑色）
- **text_color**: 文字颜色（默认: #FFFFFF 白色）

#### F. 叠加图片设置
- **overlay_image**: 固定叠加图片路径（null表示不使用）
- **overlay_dir**: 叠加图片目录（null表示不使用）
- **overlay_height_ratio**: 叠加图片高度占比（默认: 0.35，即35%）
- **overlay_box_width_ratio**: 叠加图片区域宽度占比（默认: 0.68，即68%）
- **overlay_fit**: 图片适配方式（cover=填充, contain=包含，默认: cover）
- **overlay_top_margin**: 顶部边距（默认: 48）
- **overlay_text_gap**: 图片与文字间距（默认: 12）

#### G. 背景音乐(BGM)设置
- **enabled**: 是否启用BGM（默认: false）
- **file**: BGM文件路径
- **volume**: 音量（默认: 0.18，范围: 0-1）
- **fade_in**: 淡入时长秒数（默认: 1.5）
- **fade_out**: 淡出时长秒数（默认: 1.5）
- **audio_bitrate**: 音频比特率（默认: 192k）

**重要提示**:
- 使用 `AskUserQuestion` 工具展示所有设置分组
- 每个分组提供"保持默认"选项
- **所有用户修改的配置都通过命令行参数传递，不修改配置文件**
- 执行命令格式：`uv run main.py --config configs/1.yaml [覆盖参数...]`

### 步骤2: 准备执行环境

1. 进入项目目录：
```bash
cd E:/Projects/Works/SelfMediaTools
```

2. 确认输入源：
- 如果使用 `text`，直接使用用户输入的文本
- 如果使用 `text_file`，确认文件存在

3. 确认资源文件：
- 字体文件存在（font_path）
- 如果使用overlay_image，确认图片存在
- 如果启用BGM，确认bgm_file存在

### 步骤3: 执行视频生成

**重要原则**: **不要修改默认配置文件** `configs/1.yaml`。所有用户自定义的配置更改都通过命令行参数传递。

#### 执行方式：基础配置 + CLI参数覆盖

使用默认配置作为基础，通过命令行参数覆盖需要修改的设置：

```bash
uv run main.py --config configs/1.yaml [覆盖参数...]
```

**示例**：
```bash
# 只修改BGM音量，其他使用默认值
uv run main.py --config configs/1.yaml --bgm-volume 0.27

# 修改多个设置
uv run main.py --config configs/1.yaml \
  --bgm-volume 0.27 \
  --voice zh-CN-XiaoxiaoNeural \
  --output-modes portrait,landscape

# 完全自定义
uv run main.py --config configs/1.yaml \
  --text "自定义文本内容" \
  --voice zh-CN-XiaoxiaoNeural \
  --rate "+10%" \
  --output-modes portrait,landscape \
  --bgm-enabled true \
  --bgm-file ./assets/bgm.MP3 \
  --bgm-volume 0.25
```

#### 命令行参数映射表
| 配置项 | CLI参数 | 示例 |
|--------|---------|------|
| text | `--text` | `--text "输入文本"` |
| text_file | `--text-file` | `--text-file ./assets/input.txt` |
| voice | `--voice` | `--voice zh-CN-XiaoxiaoNeural` |
| rate | `--rate` | `--rate "+10%"` |
| volume | `--volume` | `--volume "+0%"` |
| output_modes | `--output-modes` | `--output-modes portrait,landscape` |
| font_path | `--font-path` | `--font-path C:/Windows/Fonts/simhei.ttf` |
| font_size | `--font-size` | `--font-size 80` |
| bg_color | `--bg-color` | `--bg-color "#1a1a1a"` |
| text_color | `--text-color` | `--text-color "#FFFF00"` |
| overlay_image | `--overlay-image` | `--overlay-image ./image.jpg` |
| bgm_enabled | `--bgm-enabled` | `--bgm-enabled true` |
| bgm_file | `--bgm-file` | `--bgm-file ./assets/bgm.MP3` |
| bgm_volume | `--bgm-volume` | `--bgm-volume 0.25` |
| bgm_fade_in | `--bgm-fade-in` | `--bgm-fade-in 2.0` |
| bgm_fade_out | `--bgm-fade-out` | `--bgm-fade-out 2.0` |

**常用命令行参数映射**:
| 配置项 | CLI参数 |
|--------|---------|
| text | `--text` |
| text_file | `--text-file` |
| voice | `--voice` |
| rate | `--rate` |
| volume | `--volume` |
| output_modes | `--output-modes` |
| font_path | `--font-path` |
| bgm_enabled | `--bgm-enabled` |
| bgm_file | `--bgm-file` |

### 步骤4: 输出结果

视频输出到以下目录结构：
```
output/run_YYYYMMDD_HHMMSS/
├── 01_sentences/      # 分割后的句子
├── 02_images/         # 渲染的图片
├── 03_audio/          # TTS音频文件
├── 04_segments/       # 视频片段
└── 05_final/          # 最终视频
    └── final.mp4      # 最终成品
```

告知用户：
1. 输出目录的完整路径
2. 最终视频文件的路径
3. 如果是多模式输出，分别说明竖屏和横屏视频的位置

## 配置速查表

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
2. **字体文件不存在**: 检查font_path路径
3. **TTS失败**: 检查网络连接和API密钥
4. **BGM文件不存在**: 检查bgm_file路径
5. **内存不足**: 减少tts_workers/image_workers/clip_workers的值

## 示例对话

**用户**: "生成一个视频"

**你的回复**:
展示当前配置摘要，询问用户需要修改哪些设置...

**用户**: "把BGM音量改成0.27"

**你的回复**:
确认修改，然后执行命令：
```bash
uv run main.py --config configs/1.yaml --bgm-volume 0.27
```

**用户**: "修改语音为女声，输出竖屏和横屏"

**你的回复**:
执行命令：
```bash
uv run main.py --config configs/1.yaml \
  --voice zh-CN-XiaoxiaoNeural \
  --output-modes portrait,landscape
```
