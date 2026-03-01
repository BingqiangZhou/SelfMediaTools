---
name: video-generator-publisher
description: 用于生成自媒体短视频并支持发布到抖音。当用户需要将文本转换为带TTS语音和背景音乐的视频时使用此技能。支持竖屏(1080x1920)和横屏(1920x1080)两种输出格式。视频生成后可选择自动发布到抖音创作者平台，包含AI封面生成、标题内容优化等功能。触发场景：用户提到"生成视频"、"制作视频"、"text to video"、"TTS视频"、"自媒体视频"、"短视频生成"、"发布视频"、"上传抖音"等，或直接要求运行视频生成脚本。
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

### 步骤5: 发布到抖音 (可选)

视频生成完成后，使用 `AskUserQuestion` 工具询问用户是否要将视频发布到抖音：

**问题**: "视频已生成完成！是否要将视频发布到抖音创作者平台？"
- 选项: "是，发布到抖音" / "否，暂时不发布"

#### 5.1 生成标题和内容

如果用户选择发布，根据**原始文案内容**生成吸引人的标题和发布内容。

**重要原则**:
- 标题和内容必须基于用户提供的原始文案进行生成
- 保持内容的真实性和相关性
- 话题标签必须与视频内容相符

**标题生成原则**:
- 长度控制在10-30字
- 使用吸引眼球的词汇（如"AI生成"、"精彩"、"必看"等）
- 可以加入数字或疑问句增加吸引力
- 提炼文案核心主题作为标题亮点

**内容生成原则**:
- 提取文案核心观点，用简洁语言描述
- **必须包含话题标签 #主题** - 格式为 `#主题名称`
- 标签应该与视频内容直接相关
- 可以添加2-3个相关热门话题标签
- 内容长度建议50-200字

**话题标签选择**:
- 根据文案内容确定主要话题（如 #AI技术 #知识分享 #生活感悟 等）
- 标签使用中文，简洁明了
- 避免使用过于冷门或不相关的标签

生成后，使用 `AskUserQuestion` 工具向用户展示：
- **生成的标题**
- **生成的内容**（包含话题标签 #主题）

**询问用户**: "以下是根据文案生成的标题和内容，请确认是否满意？"
- 选项: "确认使用" / "需要修改"

如果用户选择修改，允许用户输入自定义的标题和内容。

#### 5.2 访问抖音创作者平台

使用 Chrome DevTools MCP 工具访问抖音创作者中心：

**Chrome DevTools MCP 工具列表**:
- `list_pages` - 列出所有打开的页面
- `new_page` - 创建新页面并导航到URL
- `take_snapshot` - 获取页面快照（用于查找元素）
- `navigate_page` - 导航到指定URL
- `upload_file` - 上传文件
- `fill` - 填写表单字段
- `click` - 点击元素
- `wait_for` - 等待特定文本出现

**操作步骤**:

1. **创建或选择页面**:
   ```bash
   # 使用 new_page 创建新页面
   mcp__chrome-devtools__new_page(url="https://creator.douyin.com/creator-micro/content/publish")
   ```
   或使用 `navigate_page` 在现有页面导航

2. **等待页面加载**:
   - 使用 `take_snapshot` 获取页面快照
   - 检查页面是否完全加载
   - 如果需要登录，等待用户完成登录操作

#### 5.3 上传视频

1. **获取页面快照**，查找上传按钮：
   ```bash
   mcp__chrome-devtools__take_snapshot()
   ```
   查找包含"上传"、"选择视频"或类似文字的按钮元素

2. **上传视频文件**:
   ```bash
   mcp__chrome-devtools__upload_file(uid="上传按钮的uid", filePath="视频完整路径")
   ```
   - 视频路径：`output/run_YYYYMMDD_HHMMSS/05_final/final_portrait.mp4`（竖屏）
   - 如果只有横屏：`output/run_YYYYMMDD_HHMMSS/05_final/final_landscape.mp4`
   - 优先上传竖屏版本

3. **等待上传完成**:
   - 使用 `wait_for` 等待"上传完成"、"100%"或类似提示
   - 或定期使用 `take_snapshot` 检查上传进度

#### 5.4 设置封面

**重要**: 必须设置AI智能生成封面，包含**两个封面**：
- **竖封面** (3:4比例) - 必须设置
- **横封面** (4:3比例) - 建议设置，获得更多流量

**操作步骤**:

1. **设置竖封面** (3:4):
   - 点击"选择封面"或"设置封面"按钮
   - 封面编辑器打开后，查找"AI封面"或"智能封面"选项卡
   - 点击"AI生成封面"或"智能生成"按钮
   - **等待AI生成**（重要：等待"生成中"状态消失，出现封面预览或"重新生成"按钮）
   - 使用 `wait_for` 或定期 `take_snapshot` 检查生成状态
   - 生成完成后，点击"完成"或"确定"按钮应用

2. **设置横封面** (4:3):
   - 如果系统提示"横封面缺失"或显示设置横封面的入口
   - 点击"设置横封面"按钮
   - 同样使用"AI封面"功能生成横版封面
   - 等待AI生成完成
   - 点击"完成"应用

**AI封面生成等待策略**:
```bash
# 等待生成完成的关键词
mcp__chrome-devtools__wait_for(text=["重新生成", "更换封面", "完成", "确定"])
```

#### 5.5 填写发布信息

1. **填写标题**:
   - 使用 `take_snapshot` 获取页面快照
   - 查找标题输入框（通常包含"标题"、"作品标题"等提示文字）
   - 使用 `fill` 工具填入用户确认的标题：
   ```bash
   mcp__chrome-devtools__fill(uid="标题输入框uid", value="用户确认的标题")
   ```

2. **填写内容**:
   - 查找内容/简介输入区域（通常包含"内容"、"简介"、"描述"等提示）
   - 填入包含话题标签的内容：
   ```bash
   mcp__chrome-devtools__fill(uid="内容输入框uid", value="包含#话题标签的内容")
   ```
   - 确保话题标签格式正确（如 `#AI技术 #知识分享`）

#### 5.6 检查并发布

1. **等待内容检测**:
   - 使用 `wait_for` 等待"检测完成"、"未见异常"或类似状态
   - 或使用 `take_snapshot` 检查页面状态

2. **确认发布设置**:
   - 谁可以看：确认设置为"公开"
   - 发布时间：确认设置为"立即发布"

3. **提交发布**:
   - 查找并点击"发布"按钮
   ```bash
   mcp__chrome-devtools__click(uid="发布按钮uid")
   ```

4. **等待发布完成**:
   - 使用 `wait_for` 等待"发布成功"提示
   - 或等待页面跳转到作品管理页面

#### 5.7 发布结果

告知用户发布结果：
- **成功**: 显示"发布成功！"，告知作品管理页面链接
- **失败**: 说明错误原因，建议用户手动处理

**注意事项**:
- 如果需要短信验证码，暂停操作，告知用户输入验证码后继续
- 如果发布过程中出现异常（如页面卡死、元素找不到），保存当前状态，建议用户手动完成
- 竖封面和横封面都设置完整可以获得更多流量推荐
- 每次操作前使用 `take_snapshot` 确认页面状态
- 如果页面元素找不到，告知用户当前页面状态，请用户手动操作

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

## Theme Keyword Cover Update (2026-03)

- After generating title/content, summarize one 2-6 Chinese character theme keyword from the source text.
- Pass it to the video pipeline by CLI:

```bash
uv run main.py --config configs/1.yaml --theme-keyword "<关键词>"
```

- CLI mapping addition:
- `theme_keyword` -> `--theme-keyword`
- If keyword is empty, pipeline falls back to `天命之人`.
