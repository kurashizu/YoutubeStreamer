# Youtube Streamer

这是一个基于 `yt-dlp` 和 `ffmpeg` 的网络视频推流工具。它提供了一个简单的Web界面，用于管理视频播放队列，并将来自YouTube、Bilibili等网站的视频流实时转码并推送到指定的RTMP服务器。

## ✨ 功能特性

- **支持多平台**: 目前支持从YouTube、Bilibili等多种视频网站获取视频与直播源~~（甚至支持P*rnH*b）~~。
- **Web操作界面**: 通过网页轻松管理播放列表和推流状态。
- **视频队列系统**: 支持将多个视频URL添加到播放队列，自动按顺序播放。
- **多平台支持**: 利用 `yt-dlp`，支持从YouTube、Bilibili等多种视频网站获取视频源。
- **多推流端点**: 可在配置文件中定义多个独立的推流端点，并分别进行管理。
- **实时转码**: 使用 `ffmpeg` 进行实时视频转码和推流。
- **硬件加速**: 支持VA-API硬件加速（可在代码中配置），显著降低CPU使用率。
- **动态水印**: 在视频画面上实时显示当前播放信息、队列状态、服务器性能等动态水印。
- **空闲待机流**: 当播放队列为空时，自动推流一个包含状态信息的待机画面，避免断流。
- **灵活配置**: 通过 `config.json` 文件轻松配置所有参数。

## ⚙️ 系统需求

- **Python 3.x**
- **Flask**: `pip install flask`
- **ffmpeg**: 确保已安装并添加到系统的 `PATH` 环境变量中。若要使用硬件加速，请确保 `ffmpeg` 编译时已包含相应模块（如 `h264_vaapi`）。
- **yt-dlp**: 确保已安装并添加到系统的 `PATH` 环境变量中。

## 🚀 安装与启动

1.  **克隆仓库**
    ```bash
    git clone <your-repository-url>
    cd streamer
    ```

2.  **安装依赖**
    ```bash
    pip install flask
    ```

3.  **创建配置文件**
    将项目中的 `config_sample.json` 复制一份并重命名为 `config.json`。
    ```bash
    cp config_sample.json config.json
    ```

4.  **修改配置文件**
    根据您的需求，编辑 `config.json` 文件。详细说明请参考下一章节。

5.  **运行应用**
    ```bash
    python3 app.py
    ```
    服务启动后，您可以通过 `http://<listening_addr>:<listening_port>` 访问Web操作界面。

## 📄 配置文件说明 (`config.json`)

配置文件分为几个主要部分：

### `rtmp`
- `base_url`: 您的RTMP推流服务器的基础地址，例如 `rtmp://your-server/live/`。
- `streams`: 一个字符串列表，定义了所有可用的推流密钥（也作为独立的管理端点）。最终推流地址将是 `base_url` + `stream_key`。
- `distributors`: (可选) 一个对象列表，用于在Web界面上生成可复制的播放地址（例如CDN地址），方便观众选择。实际拉流地址为 `base_url` + `stream_key.m3u8`，RTMP服务器需要支持HLS格式的直播流。

### `server`
- `public_base_url`: 此Web API服务的公开访问地址。前端界面会使用此地址与后端通信。
- `listening_addr`: Web服务监听的IP地址，`0.0.0.0` 表示监听所有网络接口。
- `listening_port`: Web服务监听的端口。

### `yt-dlp`
- `cookie_file`:
  - `youtube`: (可选) 指向YouTube的cookie文件路径。
  - `bilibili`: (可选) 指向Bilibili的cookie文件路径。

## 🕹️ 使用指南

1.  **访问Web界面**: 在浏览器中打开 `http://<your-server-ip>:<port>`。

2.  **选择推流端点**: 在页面顶部的下拉菜单中，选择一个您想管理的推流端点 (Endpoint)。

3.  **添加视频到队列**:
    - 在 "Video URL" 输入框中粘贴一个视频链接 (例如 `https://www.youtube.com/watch?v=...`)。
    - 您可以设置推流码率 (Bitrate)、是否仅音频 (Audio Only) 等参数。
    - 点击 **"Add to Queue"** 按钮。

4.  **管理队列**:
    - 视频添加成功后，会出现在 "Playlist" 区域。
    - 如果当前没有视频在播放，队列中的第一个视频会自动开始推流。
    - 您可以点击视频旁边的 **"Remove"** 按钮将其从队列中删除。

5.  **监控状态**:
    - "Status" 区域会实时显示当前推流状态、`ffmpeg` 的日志输出以及性能信息。
    - 您可以点击 **"Terminate"** 按钮来强制停止当前正在播放的视频。播放列表中的下一个视频会自动开始。

## 📡 API 端点

本项目提供了一组简单的HTTP GET接口用于程序化控制。

- `GET /streamer/enqueue`
  - **功能**: 添加一个视频到队列。
  - **参数**: `endpoint`, `url`, `bitrate`, `audioOnly`, `FPS`, `GOP`, `index`。

- `GET /streamer/dequeue`
  - **功能**: 从队列中移除一个视频。
  - **参数**: `endpoint`, `index`。

- `GET /streamer/status`
  - **功能**: 获取指定端点的当前状态、日志和播放列表。
  - **参数**: `endpoint`。

- `GET /streamer/terminate`
  - **功能**: 停止当前正在播放的视频。
  - **参数**: `endpoint`。

## 🤝 致谢

- ffmpeg: 强大的音视频处理框架。
- yt-dlp: 功能丰富的视频下载工具。
- Flask: 轻量级的Web应用框架。