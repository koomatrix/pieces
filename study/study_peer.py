
import sys


# 模拟 PeerConnection 的状态转换
class PeerConnectionDemo:
    def __init__(self):
        self.my_state = []
        self.peer_state = []

    def add_state(self, state):
        self.my_state.append(state)
        print(f'  我的状态: {self.my_state}')

    def transition(self, event):
        print(f'事件: {event}')

        if event == '连接建立':
            self.add_state('choked')  # 默认被阻塞

        elif event == '发送 Interested':
            self.add_state('interested')

        elif event == '收到 Unchoke':
            if 'choked' in self.my_state:
                self.my_state.remove('choked')
                print(f'  我的状态: {self.my_state} (解除阻塞)')

        elif event == '收到 Choke':
            if 'choked' not in self.my_state:
                self.my_state.append('choked')
                print(f'  我的状态: {self.my_state} (被阻塞)')

        elif event == '发送 Request':
            self.add_state('pending_request')

        elif event == '收到 Piece':
            if 'pending_request' in self.my_state:
                self.my_state.remove('pending_request')
                print(f'  我的状态: {self.my_state} (请求完成)')
        print()

def 生命周期演示():

    print('=== PeerConnection 生命周期演示 ===')
    print()

    # 演示完整流程
    conn = PeerConnectionDemo()

    print('步骤 1: 连接到 Peer')
    conn.transition('连接建立')

    print('步骤 2: 发送 Interested')
    conn.transition('发送 Interested')

    print('步骤 3: 等待 Unchoke (被阻塞中)...')
    # 模拟等待...

    print('步骤 4: 收到 Unchoke')
    conn.transition('收到 Unchoke')

    print('步骤 5: 发送 Request')
    conn.transition('发送 Request')

    print('步骤 6: 收到 Piece 数据')
    conn.transition('收到 Piece')

    print('步骤 7: 继续请求 (循环)')
    conn.transition('发送 Request')

def 状态机规则总结():
    print('=== 状态机规则总结 ===')
    print()

    # 定义状态转换规则
    rules = {
        '初始状态': ['连接建立 → choked'],
        'choked': ['发送 Interested → interested', '收到 Unchoke → 移除 choked'],
        'interested': ['收到 Choke → 添加 choked', '收到 Unchoke → 移除 choked'],
        'unchoked': ['收到 Choke → 添加 choked'],
        'pending_request': ['发送 Request → 添加 pending_request', '收到 Piece → 移除 pending_request']
    }

    for state, transitions in rules.items():
        print(f'{state}:')
        for t in transitions:
            print(f'  • {t}')
        print()

    print('=== 状态组合说明 ===')
    print()

    state_combinations = {
        'choked + interested': '已发送 Interested，但被阻塞，等待 Unchoke',
        'interested': '已发送 Interested，收到 Unchoke，可以请求数据',
        'interested + pending_request': '已发送 Request，等待 Piece 数据',
        'choked + interested + pending_request': '异常状态（不应存在）',
        'stopped': '连接已停止，不再请求新 peer'
    }

    for combo, desc in state_combinations.items():
        print(f'{combo:45} → {desc}')

def 关键代码片段解析():
    print('=== PeerConnection 关键代码片段解析 ===')
    print()
    # 1. 协程的启动
    print('1. 协程启动 (protocol.py:78)')
    print('  代码: self.future = asyncio.ensure_future(self._start())')
    print('  作用: 创建并立即启动一个后台协程')
    print('  类比: Kotlin 中的 launch {}, TS 中的 Promise')
    print()

    # 2. 从队列获取 peer
    print('2. 从队列获取 peer (protocol.py:82)')
    print('  代码: ip, port = await self.queue.get()')
    print('  作用: 从 asyncio.Queue 阻塞地获取下一个 peer')
    print('  类比: Kotlin 中的 Channel.receive(), TS 中的 queue.dequeue()')
    print()

    # 3. TCP 连接
    print('3. 建立 TCP 连接 (protocol.py:88-89)')
    print('  代码: self.reader, self.writer = await asyncio.open_connection(ip, port)')
    print('  作用: 异步建立 TCP 连接')
    print('  类比: Kotlin 中的 Socket().connect(), TS 中的 net.connect()')
    print()

    # 4. 握手
    print('4. 握手协议 (protocol.py:93)')
    print('  代码: buffer = await self._handshake()')
    print('  作用: 发送握手消息并等待响应')
    print('  返回: 剩余缓冲区数据（可能包含下一条消息）')
    print()

    # 5. 消息流迭代
    print('5. 消息流迭代 (protocol.py:107)')
    print('  代码: async for message in PeerStreamIterator(self.reader, buffer):')
    print('  作用: 使用异步迭代器逐个接收消息')
    print('  类比: Kotlin 中的 flow {}, TS 中的 async for')
    print()

    # 6. 发送数据
    print('6. 发送数据 (protocol.py:195-196)')
    print('  代码: self.writer.write(message); await self.writer.drain()')
    print('  作用: 写入数据并等待发送完成')
    print('  类比: Kotlin 中的 writeAndFlush(), TS 中的 write() + await')
    print()

    # 7. 回调通知
    print('7. 数据接收回调 (protocol.py:130-134)')
    print('  代码: self.on_block_cb(peer_id=..., piece_index=..., block_offset=..., data=...)')
    print('  作用: 将接收到的 block 传递给 PieceManager 处理')
    print('  设计: 回调模式，解耦连接管理和数据处理')

def 错误处理与重试机制():
    print('=== 错误处理与重试机制 ===')
    print()

    error_handling = {
        'ProtocolError': {
            '代码位置': 'protocol.py:149-150',
            '处理方式': 'logging.exception(\'协议错误\')',
            '后续动作': '调用 cancel()，继续循环获取下一个 peer',
            '触发场景': '握手失败、info_hash 不匹配等'
        },
        'ConnectionRefusedError': {
            '代码位置': 'protocol.py:151-152',
            '处理方式': 'logging.warning(\'无法连接到对等节点\')',
            '后续动作': '调用 cancel()，继续循环获取下一个 peer',
            '触发场景': 'Peer 拒绝连接（端口未开放）'
        },
        'TimeoutError': {
            '代码位置': 'protocol.py:151-152',
            '处理方式': 'logging.warning(\'无法连接到对等节点\')',
            '后续动作': '调用 cancel()，继续循环获取下一个 peer',
            '触发场景': '连接超时'
        },
        'ConnectionResetError': {
            '代码位置': 'protocol.py:153-154',
            '处理方式': 'logging.warning(\'连接已关闭\')',
            '后续动作': '调用 cancel()，继续循环获取下一个 peer',
            '触发场景': 'Peer 主动断开连接'
        },
        'CancelledError': {
            '代码位置': 'protocol.py:153-154',
            '处理方式': 'logging.warning(\'连接已关闭\')',
            '后续动作': '正常退出循环',
            '触发场景': '调用 stop() 方法'
        }
    }

    for error_type, info in error_handling.items():
        print(f'{error_type}:')
        for key, value in info.items():
            print(f'  {key}: {value}')
        print()

    print('=== 重试机制总结 ===')
    print()
    print('PeerConnection 的重试机制：')
    print('  1. 所有错误都会调用 cancel() 清理当前连接')
    print('  2. 然后继续 while 循环，从队列获取下一个 peer')
    print('  3. 除非是 stopped 状态或遇到未捕获的异常')
    print('  4. 这保证了 40 个协程持续工作，不会因为单次连接失败而停止')

if __name__ == '__main__':

    # sys.path.insert(0, '.')
    生命周期演示()
    状态机规则总结()
    关键代码片段解析()
    错误处理与重试机制()