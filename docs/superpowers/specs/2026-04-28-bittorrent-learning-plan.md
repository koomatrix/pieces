# BitTorrent 客户端学习计划

**目标读者**：具有 Python 基础知识，熟悉 Kotlin 和 TypeScript 的开发者

**学习目标**：全面学习 BitTorrent 协议原理、Python asyncio 异步编程、以及网络客户端架构设计

**学习方式**：结构化文档阅读（自研）

---

## 项目背景

这是一个实验性 BitTorrent 客户端，使用 Python 3 的 asyncio 实现。主要功能是下载（leeching），不支持做种（seeding），也不支持多文件 torrent。

**技术栈**：
- Python 3.10+
- asyncio（异步编程）
- aiohttp（HTTP 客户端）
- bitstring（BitField 处理）

---

## 学习路径

采用**协议驱动学习**方案：按照 BitTorrent 协议的执行流程学习，从启动到完成下载的全过程。

**理由**：
- 能够自然地将协议、异步编程、架构三个维度结合
- 按执行流程学习，更容易理解设计动机
- 适合"先鸟瞰后深入"的学习需求

---

## 第一部分：总体架构鸟瞰

### 系统边界与限制

| 特性 | 状态 |
|------|------|
| 下载 | 支持 |
| 做种 (seeding) | 不支持 |
| 多文件 torrent | 不支持 |
| 并发连接数 | 40 个 |
| Block 请求大小 | 16KB (2^14) |

### 核心组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                        TorrentClient                         │
│                    (中央协调器 - asyncio 主循环)              │
│  - 定期联系 Tracker 获取 Peer 列表                            │
│  - 维护 40 个并发 PeerConnection 工作协程                     │
│  - 使用 asyncio.Queue 分发 Peers                              │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌────────┐  ┌─────────┐  ┌──────────────┐
   │Tracker │  │PieceMgr │  │PeerConnection│
   │        │  │         │  │   (x40)      │
   └────────┘  └─────────┘  └──────────────┘
        │           │              │
        ▼           ▼              ▼
   ┌────────┐  ┌─────────┐  ┌──────────────┐
   │Torrent │  │ Piece  │  │PeerStream    │
   │        │  │ Block  │  │Iterator      │
   └────────┘  └─────────┘  └──────────────┘
```

### 数据流概览

```
.torrent 文件 → Torrent 解析 → info_hash → Tracker
                                                    ↓
                                              Peer 列表 (队列)
                                                    ↓
                                          PeerConnection (40 协程)
                                                    ↓
                                  握手 → BitField → Interested → Unchoke
                                                    ↓
                                          PieceManager 稀缺优先选择
                                                    ↓
                                          请求 Blocks (16KB)
                                                    ↓
                                          接收数据 → SHA1 校验
                                                    ↓
                                          写入磁盘
```

### 关键异步模式

- **生产者-消费者**：Tracker 产生 peers，PeerConnection 消费 peers
- **协程池**：40 个 PeerConnection 并发工作
- **回调机制**：PieceManager.block_received() 作为数据接收回调
- **队列通信**：asyncio.Queue 作为组件间通信通道

---

## 第二部分：章节结构

```
第 1 章：环境准备与项目概览
    ├─ 1.1 环境搭建
    ├─ 1.2 项目结构一览
    └─ 1.3 运行第一个下载

第 2 章：.torrent 文件解析（Torrent 模块）
    ├─ 2.1 bencode 编码格式
    ├─ 2.2 Torrent 类的结构
    └─ 2.3 info_hash 的计算与作用

第 3 章：Tracker 通信（Tracker 模块）
    ├─ 3.1 Tracker 的工作原理
    ├─ 3.2 announce 请求参数详解
    ├─ 3.3 响应解析与 peer 列表
    └─ 3.4 aiohttp 异步 HTTP 请求

第 4 章：BitTorrent 协议消息（Protocol 模块 - 消息层）
    ├─ 4.1 握手协议
    ├─ 4.2 消息类型与格式
    ├─ 4.3 消息编解码实现
    └─ 4.4 PeerStreamIterator 异步流解析

第 5 章：Peer 连接管理（Protocol 模块 - 连接层）
    ├─ 5.1 PeerConnection 协程生命周期
    ├─ 5.2 状态机
    ├─ 5.3 超时与重试机制
    └─ 5.4 与 PieceManager 的交互

第 6 章：Piece 管理与稀缺优先算法（Client 模块 - PieceManager）
    ├─ 6.1 Piece/Block 数据结构
    ├─ 6.2 稀缺优先算法原理与实现
    ├─ 6.3 piece 状态转换
    ├─ 6.4 SHA1 校验
    └─ 6.5 数据写入磁盘

第 7 章：客户端协调器（Client 模块 - TorrentClient）
    ├─ 7.1 主循环设计
    ├─ 7.2 协程池管理
    ├─ 7.3 asyncio.Queue 生产者-消费者模式
    └─ 7.4 优雅关闭

第 8 章：异步编程模式总结
    ├─ 8.1 asyncio 核心概念回顾
    ├─ 8.2 项目中的异步模式
    ├─ 8.3 与 Kotlin/TS 异步的对比
    └─ 8.4 最佳实践与陷阱

第 9 章：架构设计总结
    ├─ 9.1 分层设计分析
    ├─ 9.2 模块职责边界
    ├─ 9.3 数据流与控制流分离
    └─ 9.4 扩展性思考
```

---

## 第三部分：各章节详细内容

### 第 1 章：环境准备与项目概览

**学习目标**：能够运行项目，了解整体结构

**内容要点**：
- 依赖安装（bitstring, aiohttp）
- 项目目录结构说明
- 运行示例下载
- 测试框架介绍

**关键文件**：`requirements.txt`, `Makefile`, 目录结构

**可运行命令**：
```bash
make init              # 安装依赖
make test              # 运行所有测试
python pieces.py -v tests/data/bootfloppy-utils.img.torrent  # 下载示例
```

---

### 第 2 章：.torrent 文件解析

**学习目标**：理解 torrent 文件格式和 info_hash 作用

**内容要点**：
- bencode 编码格式（字符串、整数、列表、字典）
- Torrent 类的属性和方法
- info_hash 为什么是 20 字节
- info_hash 在握手和 tracker 中的作用

**关键代码**：
- `pieces/bencoding.py` - 编解码实现
- `pieces/torrent.py` - Torrent 类

**对比思考**：
- bencode vs JSON：为什么 BitTorrent 不用 JSON？

---

### 第 3 章：Tracker 通信

**学习目标**：理解 tracker 如何发现 peers

**内容要点**：
- Tracker 的工作原理（HTTP GET 请求）
- announce 请求参数详解
- 响应格式（compact vs 正常格式）
- aiohttp 异步 HTTP 请求使用

**关键代码**：
- `pieces/tracker.py:Tracker.announce()`
- `pieces/tracker.py:TrackerResponse`

**核心概念**：
- Peer ID 格式（Azureus 风格）
- 事件类型（started, completed, stopped）

---

### 第 4 章：BitTorrent 协议消息

**学习目标**：理解协议消息的格式与编解码

**内容要点**：
- 握手协议（68 字节固定格式）
- 消息前缀长度前缀设计
- 各消息类型的 payload 结构
- 消息编解码实现

**关键代码**：
- `pieces/protocol.py:Handshake`
- `pieces/protocol.py:BitField, Request, Piece` 等消息类

**消息类型表**：

| 消息类型 | ID | Payload | 用途 |
|---------|----|---------|------|
| Choke   | 0  | 无      | 阻止对方请求数据 |
| Unchoke | 1  | 无      | 允许对方请求数据 |
| Interested | 2 | 无   | 告诉对方我想要数据 |
| BitField | 5 | 位图     | 声明自己有哪些 piece |
| Request  | 6 | index, begin, length | 请求 block |
| Piece    | 7 | index, begin, data | 发送 block 数据 |
| Have     | 4 | index   | 告知获得新 piece |

---

### 第 5 章：Peer 连接管理

**学习目标**：理解单个 peer 连接的完整生命周期

**内容要点**：
- PeerConnection 协程的工作流程
- 状态机（choked/unchoked, interested/not interested）
- 超时处理与重试机制
- 与 PieceManager 的回调交互

**关键代码**：
- `pieces/protocol.py:PeerConnection`
- `pieces/protocol.py:PeerStreamIterator`

**核心流程**：
```
获取 peer → TCP 连接 → 握手 → 交换 BitField
→ 发送 Interested → 等待 Unchoke → 请求/接收数据
```

---

### 第 6 章：Piece 管理与稀缺优先算法

**学习目标**：理解 piece 选择策略和数据完整性保证

**内容要点**：
- Piece/Block 数据结构设计
- 稀缺优先算法的原理与实现
- piece 三态转换
- SHA1 校验机制
- 同步写入磁盘的考虑

**关键代码**：
- `pieces/client.py:PieceManager`
- `pieces/client.py:Piece`, `pieces/client.py:Block`

**算法伪代码**：
```python
for each piece in missing_pieces:
    count = number_of_peers_that_have_this_piece
    select piece with minimum count  # 最稀缺的
```

**为什么用稀缺优先？**
- 避免热门 piece 没人提供
- 提高整体下载成功率
- 防止某些 piece 永远下载不到

---

### 第 7 章：客户端协调器

**学习目标**：理解如何协调所有组件

**内容要点**：
- TorrentClient 主循环设计
- 40 个协程池的创建与管理
- asyncio.Queue 生产者-消费者模式
- 优雅关闭（Ctrl+C 处理）

**关键代码**：
- `pieces/client.py:TorrentClient`

**并发模型**：
```
主协程 (TorrentClient.start)
    ├─ 定期调用 Tracker
    ├─ 创建 40 个 PeerConnection 协程
    └─ 管理生命周期
```

---

### 第 8 章：异步编程模式总结

**学习目标**：掌握项目中的 asyncio 模式

**内容要点**：
- asyncio 核心概念回顾
- 项目中的异步模式应用
- 与 Kotlin/TS 异步的对比
- 最佳实践与常见陷阱

**对比表格**：

| 特性 | Python asyncio | Kotlin Coroutines | TypeScript async/await |
|------|----------------|-------------------|------------------------|
| 关键字 | async/await | suspend | async/await |
| 调度器 | 事件循环 | 协程调度器 | 事件循环 |
| 阻塞调用 | 避免 | 避免 | 避免 |
| 并发创建 | asyncio.create_task | launch / async | Promise.all |

**项目中的模式**：
1. 协程池：40 个 PeerConnection
2. 队列通信：asyncio.Queue
3. 回调驱动：block_received
4. 超时处理：asyncio.wait_for

---

### 第 9 章：架构设计总结

**学习目标**：理解项目的架构设计思想

**内容要点**：
- 分层设计分析
- 模块职责边界
- 数据流与控制流分离
- 扩展性思考

**架构图**：

```
┌─────────────────────────────────────────┐
│           入口层 (CLI)                   │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         协调层 (TorrentClient)          │
│  - 生命周期管理                           │
│  - 协程池调度                             │
└─────┬───────────────────────┬───────────┘
      │                       │
┌─────▼────────┐    ┌────────▼──────────┐
│  业务层       │    │  连接层            │
│  - Torrent    │    │  - PeerConnection │
│  - Tracker    │    │  - 状态机          │
│  - PieceManager│   │  - 消息处理        │
└─────┬────────┘    └────────┬──────────┘
      │                       │
┌─────▼───────────────────────▼──────────┐
│  协议层                                │
│  - 消息类                              │
│  - 握手协议                            │
│  - PeerStreamIterator                  │
└─────┬───────────────────────┬───────────┘
      │                       │
┌─────▼────────┐    ┌────────▼──────────┐
│  基础层       │    │  数据结构          │
│  - bencoding │    │  - Piece          │
│  - aiohttp   │    │  - Block          │
└──────────────┘    └───────────────────┘
```

**设计原则**：
1. 单一职责：每个模块只做一件事
2. 依赖倒置：高层不依赖低层实现细节
3. 接口隔离：模块间通过接口交互
4. 开闭原则：易于扩展，无需修改

---

## 附录：快速参考

### 关键常量

| 常量 | 值 | 说明 |
|------|----|------|
| MAX_PEER_CONNECTIONS | 40 | 并发 peer 连接数 |
| REQUEST_SIZE | 2^14 (16KB) | Block 请求大小 |
| max_pending_time | 300 * 1000 (5分钟) | Block 请求超时 |

### 关键文件索引

| 模块 | 文件 | 主要类/函数 |
|------|------|-------------|
| 入口 | `pieces/cli.py` | `main()` |
| 客户端 | `pieces/client.py` | `TorrentClient`, `PieceManager` |
| 协议 | `pieces/protocol.py` | `PeerConnection`, `PeerStreamIterator`, 消息类 |
| Tracker | `pieces/tracker.py` | `Tracker`, `TrackerResponse` |
| Torrent | `pieces/torrent.py` | `Torrent` |
| 编解码 | `pieces/bencoding.py` | `Decoder`, `Encoder` |

---

**文档版本**：1.0
**创建日期**：2026-04-28
