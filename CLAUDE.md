# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个名为 **pieces** 的实验性 BitTorrent 客户端，使用 Python 3 的 asyncio 实现。它主要用于学习 BitTorrent 协议和 Python 的 asyncio 库。

**注意**: 此客户端仅支持下载（leeching），不支持做种（seeding）。

## 开发命令

```bash
# 安装依赖
make init

# 运行所有测试（lint + 单元测试）
make test

# 仅运行 lint 检查
make lint

# 仅运行单元测试
make unit

# 运行测试覆盖率报告
make coverage

# 运行客户端下载种子
python pieces.py -v tests/data/bootfloppy-utils.img.torrent
```

### 运行单个测试

```bash
# 运行指定的测试类
python -m unittest tests.test_protocol

# 运行指定的测试方法
python -m unittest tests.test_protocol.TestPeerStreamIterator.test_parse_keep_alive
```

## 架构概述

### 核心组件

**pieces/cli.py**
- 入口点，解析参数并启动 `TorrentClient`
- 优雅处理 Ctrl+C 关闭

**pieces/client.py**
- `TorrentClient`: 中央协调器，管理下载生命周期
  - 定期连接 tracker 获取 peer 列表
  - 维护 `PeerConnection` 工作协程池（最大 40 个连接）
  - 使用 `asyncio.Queue` 向工作协程分发 peers
- `PieceManager`: 实现 piece 选择策略和持久化
  - 使用 **rarest-first 算法** 选择 pieces（见 `_get_rarest_piece()`）
  - 跟踪 piece 状态: missing → ongoing → have
  - 写入磁盘前用 SHA1 校验 piece
  - 通过文件描述符同步将完成的 piece 写入磁盘
- `Piece`/`Block`: 表示 torrent pieces 和 blocks 的数据结构

**pieces/protocol.py**
- `PeerConnection`: 管理单个 peer 的 TCP 连接
  - 处理 BitTorrent 握手协议
  - 维护状态机: choked/unchoked, interested/not interested
  - 从 `available_peers` 队列消费 peers
- `PeerStreamIterator`: 异步迭代器，从 socket 解析 BitTorrent 消息
  - 分块读取原始字节并产出解析后的消息对象
- 消息类: `Handshake`, `Have`, `BitField`, `Request`, `Piece`, `Choke`, `Unchoke` 等
  - 每个类都实现了 `encode()` 和 `decode()` 用于二进制协议格式

**pieces/tracker.py**
- `Tracker`: 使用 `aiohttp` 进行 tracker announce 调用的 HTTP 客户端
- `TrackerResponse`: 解析 bencode 编码的 tracker 响应
- 生成 Azureus 风格的 peer ID: `-PC0001-<随机12位数字>`

**pieces/torrent.py**
- `Torrent`: 解析 `.torrent` 文件并提取元数据
- 计算 info_hash（bencode 编码的 info 字典的 SHA1）
- **限制**: 不支持多文件 torrent

**pieces/bencoding.py**
- `Decoder`/`Encoder`: 实现 BitTorrent 的 bencode 格式

### 数据流

1. `TorrentClient.start()` 循环定期联系 tracker 获取 peers
2. Peers 被添加到 `available_peers` asyncio 队列
3. 40 个 `PeerConnection` 工作协程从队列消费并尝试 TCP 连接
4. 握手后，peers 交换 `BitField` 消息显示可用的 pieces
5. 客户端发送 `Interested`，等待 peer 的 `Unchoke`
6. 被 unchoke 后，通过 `PieceManager.next_request()` 请求 blocks（每个 16KB）
7. 接收到 blocks 后回调到 `PieceManager.block_received()`
8. piece 完成并通过 hash 验证后，通过 `os.write()` 写入磁盘

### 关键常量

- `MAX_PEER_CONNECTIONS = 40` - 并发 peer 连接数
- `REQUEST_SIZE = 2**14` (16KB) - Block 请求大小
- `max_pending_time = 300 * 1000` (5 分钟) - Block 请求超时前重新请求

## 测试

测试位于 `tests/` 目录，使用 Python 的 unittest 框架:
- `test_protocol.py` - BitTorrent 协议消息解析测试
- `test_client.py` - PieceManager 逻辑测试
- `test_torrent.py` - Torrent 文件解析测试
- `test_tracker.py` - Tracker 通信测试
- `test_bencoding.py` - Bencode 编解码测试
- `tests/data/` - 包含用于测试的示例 `.torrent` 文件

## 依赖

见 `requirements.txt`:
- `bitstring==3.1.5` - 用于 BitField 处理
- `aiohttp==0.22.5` - 用于 tracker HTTP 请求
- `flake8==2.5.4` - 代码风格检查
- `coverage==4.1` - 测试覆盖率
