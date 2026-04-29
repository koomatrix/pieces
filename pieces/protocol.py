#
# pieces - 一个实验性的 BitTorrent 客户端
#
# 版权所有 2016 markus.eliasson@gmail.com
#
# 根据 Apache 许可证 2.0 版授权
# 除非符合许可证规定，否则您不得使用此文件
# 您可以在以下网址获取许可证副本
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# 除非适用法律要求或书面同意，软件
# 根据许可证分发是基于"按原样"的基础，
# 不提供任何明示或暗示的保证或条件
# 请参阅许可证以了解具体的管理权限和
# 限制

import asyncio
import logging
import struct
from asyncio import Queue
from concurrent.futures import CancelledError

import bitstring

# 片段块的默认请求大小为 2^14 字节
#
# 注意：官方规范声明 2^15 是默认请求大小 - 但实际上所有实现都使用 2^14
#       有关此问题的更多详情，请参阅非官方规范
#
#       https://wiki.theory.org/BitTorrentSpecification
#
REQUEST_SIZE = 2**14


class ProtocolError(BaseException):
    pass


class PeerConnection:
    """
    用于下载和上传片段的对等连接

    对等连接将从给定队列中消费一个可用对等节点
    根据对等节点详细信息，PeerConnection 将尝试打开连接并执行 BitTorrent 握手

    成功握手后，PeerConnection 将处于*被阻塞*状态，不允许从远程对等节点请求任何数据
    发送感兴趣的消息后，PeerConnection 将等待被*解除阻塞*

    一旦远程对等节点解除对我们的阻塞，我们就可以开始请求片段
    PeerConnection 将继续请求片段，直到没有更多片段可请求，或远程对等节点断开连接

    如果与远程对等节点的连接断开，PeerConnection 将从队列中消费下一个可用对等节点并尝试连接
    """
    def __init__(self, queue: Queue, info_hash,
                 peer_id, piece_manager, on_block_cb=None):
        """
        构造 PeerConnection 并将其添加到 asyncio 事件循环

        使用 `stop` 中止此连接和任何后续连接尝试

        :param queue: 包含可用对等节点的异步队列
        :param info_hash: 元数据信息的 SHA1 哈希
        :param peer_id: 用于标识我们自己的对等节点 ID
        :param piece_manager: 负责确定请求哪些片段的管理器
        :param on_block_cb: 从远程对等节点接收到块时调用的回调函数
        """
        self.my_state = []
        self.peer_state = []
        self.queue = queue
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.remote_id = None
        self.writer = None
        self.reader = None
        self.piece_manager = piece_manager
        self.on_block_cb = on_block_cb
        self.future = asyncio.ensure_future(self._start())  # 启动此工作进程

    async def _start(self):
        while 'stopped' not in self.my_state:
            ip, port = await self.queue.get()
            logging.info('分配到对等节点：{ip}'.format(ip=ip))

            try:
                # TODO 由于某种原因，如果第一个连接断开（即第二次循环），
                # 打开新连接似乎不起作用
                self.reader, self.writer = await asyncio.open_connection(
                    ip, port)
                logging.info('已打开到对等节点的连接：{ip}'.format(ip=ip))

                # 我们有责任发起握手
                buffer = await self._handshake()

                # TODO 添加发送数据的支持
                # 发送 BitField 是可选的，当客户端没有任何片段时不需要
                # 因此我们不发送任何位字段消息

                # 连接的默认状态是对等节点不感兴趣且我们被阻塞
                self.my_state.append('choked')

                # 让对等节点知道我们对下载片段感兴趣
                await self._send_interested()
                self.my_state.append('interested')

                # 只要连接打开且传输数据，就开始将响应作为消息流读取
                async for message in PeerStreamIterator(self.reader, buffer):
                    if 'stopped' in self.my_state:
                        break
                    if type(message) is BitField:
                        self.piece_manager.add_peer(self.remote_id,
                                                    message.bitfield)
                    elif type(message) is Interested:
                        self.peer_state.append('interested')
                    elif type(message) is NotInterested:
                        if 'interested' in self.peer_state:
                            self.peer_state.remove('interested')
                    elif type(message) is Choke:
                        self.my_state.append('choked')
                    elif type(message) is Unchoke:
                        if 'choked' in self.my_state:
                            self.my_state.remove('choked')
                    elif type(message) is Have:
                        self.piece_manager.update_peer(self.remote_id,
                                                       message.index)
                    elif type(message) is KeepAlive:
                        pass
                    elif type(message) is Piece:
                        self.my_state.remove('pending_request')
                        self.on_block_cb(
                            peer_id=self.remote_id,
                            piece_index=message.index,
                            block_offset=message.begin,
                            data=message.block)
                    elif type(message) is Request:
                        # TODO 添加发送数据的支持
                        logging.info('忽略收到的 Request 消息')
                    elif type(message) is Cancel:
                        # TODO 添加发送数据的支持
                        logging.info('忽略收到的 Cancel 消息')

                    # 如果我们感兴趣，向远程对等节点发送块请求
                    if 'choked' not in self.my_state:
                        if 'interested' in self.my_state:
                            if 'pending_request' not in self.my_state:
                                self.my_state.append('pending_request')
                                await self._request_piece()

            except ProtocolError as e:
                logging.exception('协议错误')
            except (ConnectionRefusedError, TimeoutError):
                logging.warning('无法连接到对等节点')
            except (ConnectionResetError, CancelledError):
                logging.warning('连接已关闭')
            except Exception as e:
                logging.exception('发生错误')
                self.cancel()
                raise e
            self.cancel()

    def cancel(self):
        """
        向远程对等节点发送取消消息并关闭连接
        """
        logging.info('关闭对等节点 {id}'.format(id=self.remote_id))
        if not self.future.done():
            self.future.cancel()
        if self.writer:
            self.writer.close()

        self.queue.task_done()

    def stop(self):
        """
        停止此连接与当前对等节点的连接（如果存在）并停止连接任何新对等节点
        """
        # 将状态设置为停止并取消我们的 future 以跳出循环
        # 其余的清理工作最终将由循环调用 `cancel` 管理
        self.my_state.append('stopped')
        if not self.future.done():
            self.future.cancel()

    async def _request_piece(self):
        block = self.piece_manager.next_request(self.remote_id)
        if block:
            message = Request(block.piece, block.offset, block.length).encode()

            logging.debug('向对等节点 {peer} 请求片段 {piece} 的块 {block} '
                          '长度 {length} 字节'.format(
                            piece=block.piece,
                            block=block.offset,
                            length=block.length,
                            peer=self.remote_id))

            self.writer.write(message)
            await self.writer.drain()

    async def _handshake(self):
        """
        向远程对等节点发送初始握手并等待对等节点回复其握手
        """
        self.writer.write(Handshake(self.info_hash, self.peer_id).encode())
        await self.writer.drain()

        buf = b''
        tries = 1
        while len(buf) < Handshake.length and tries < 10:
            tries += 1
            buf = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)

        response = Handshake.decode(buf[:Handshake.length])
        if not response:
            raise ProtocolError('无法接收和解析握手')
        if not response.info_hash == self.info_hash:
            raise ProtocolError('握手使用的 info_hash 无效')

        # TODO：根据规范，我们应该验证从对等节点接收的 peer_id 与从 tracker 接收的 peer_id 是否匹配
        self.remote_id = response.peer_id
        logging.info('与对等节点的握手成功')

        # 我们需要返回剩余的缓冲区数据，因为我们可能读取了比握手消息大小更多的字节
        # 我们需要这些字节来解析下一条消息
        return buf[Handshake.length:]

    async def _send_interested(self):
        message = Interested()
        logging.debug('发送消息：{type}'.format(type=message))
        self.writer.write(message.encode())
        await self.writer.drain()


class PeerStreamIterator:
    """
    `PeerStreamIterator` 是一个异步迭代器，持续从给定的流读取器读取并尝试从字节流中解析有效的 BitTorrent 消息

    如果连接断开或出现问题，迭代器将通过引发 `StopAsyncIteration` 错误来中止，结束调用迭代
    """
    CHUNK_SIZE = 10*1024

    def __init__(self, reader, initial: bytes=None):
        self.reader = reader
        self.buffer = initial if initial else b''

    def __aiter__(self):
        return self

    async def __anext__(self):
        # 从套接字读取数据。当我们有足够的数据可以解析时，解析它并返回消息
        # 在此之前继续从流读取
        while True:
            try:
                data = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)
                if data:
                    self.buffer += data
                    message = self.parse()
                    if message:
                        return message
                else:
                    logging.debug('未从流读取到数据')
                    if self.buffer:
                        message = self.parse()
                        if message:
                            return message
                    raise StopAsyncIteration()
            except ConnectionResetError:
                logging.debug('对等节点关闭了连接')
                raise StopAsyncIteration()
            except CancelledError:
                raise StopAsyncIteration()
            except StopAsyncIteration as e:
                # 捕获以停止日志记录
                raise e
            except Exception:
                logging.exception('遍历流时出错！')
                raise StopAsyncIteration()
        raise StopAsyncIteration()

    def parse(self):
        """
        如果缓冲区中已读取足够的字节，尝试解析协议消息

        :return 解析的消息，如果无法解析任何消息则返回 None
        """
        # 每条消息的结构为：
        #     <长度前缀><消息 ID><负载>
        #
        # `长度前缀` 是一个四字节的大端值
        # `消息 ID` 是一个十进制字节
        # `负载` 是 `长度前缀` 的值
        #
        # 消息长度不是实际长度的一部分。因此在切片缓冲区时需要额外包含 4 个字节
        header_length = 4

        if len(self.buffer) > 4:  # 需要 4 个字节来识别消息
            message_length = struct.unpack('>I', self.buffer[0:4])[0]

            if message_length == 0:
                return KeepAlive()

            if len(self.buffer) >= message_length:
                message_id = struct.unpack('>b', self.buffer[4:5])[0]

                def _consume():
                    """消费读取缓冲区中的当前消息"""
                    self.buffer = self.buffer[header_length + message_length:]

                def _data():
                    """"从读取缓冲区中提取当前消息"""
                    return self.buffer[:header_length + message_length]

                if message_id is PeerMessage.BitField:
                    data = _data()
                    _consume()
                    return BitField.decode(data)
                elif message_id is PeerMessage.Interested:
                    _consume()
                    return Interested()
                elif message_id is PeerMessage.NotInterested:
                    _consume()
                    return NotInterested()
                elif message_id is PeerMessage.Choke:
                    _consume()
                    return Choke()
                elif message_id is PeerMessage.Unchoke:
                    _consume()
                    return Unchoke()
                elif message_id is PeerMessage.Have:
                    data = _data()
                    _consume()
                    return Have.decode(data)
                elif message_id is PeerMessage.Piece:
                    data = _data()
                    _consume()
                    return Piece.decode(data)
                elif message_id is PeerMessage.Request:
                    data = _data()
                    _consume()
                    return Request.decode(data)
                elif message_id is PeerMessage.Cancel:
                    data = _data()
                    _consume()
                    return Cancel.decode(data)
                else:
                    logging.info('不支持的消息！')
            else:
                logging.debug('缓冲区中没有足够的数据来解析')
        return None


class PeerMessage:
    """
    两个对等节点之间的消息

    协议中所有剩余的消息格式如下：
        <长度前缀><消息 ID><负载>

    - 长度前缀是一个四字节的大端值
    - 消息 ID 是一个单字节十进制值
    - 负载取决于消息

    注意：握手消息的格式与其他消息不同

    阅读更多：
        https://wiki.theory.org/BitTorrentSpecification#Messages

    BitTorrent 对所有消息都使用大端序（网络字节顺序），这在 Python `struct` 模块的所有 pack/unpack 调用中声明为第一个字符 '>'
    """
    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    Handshake = None  # 握手实际上不属于消息
    KeepAlive = None  # 根据规范，Keep-alive 没有 ID

    def encode(self) -> bytes:
        """
        将此对象实例编码为表示整条消息的原始字节（准备传输）
        """
        pass

    @classmethod
    def decode(cls, data: bytes):
        """
        将给定的 BitTorrent 消息解码为实现类型的实例
        """
        pass


class Handshake(PeerMessage):
    """
    握手消息是从远程对等节点发送然后接收的第一条消息

    该消息在此版本的 BitTorrent 协议中始终为 68 字节长

    消息格式：
        <pstrlen><pstr><reserved><info_hash><peer_id>

    在 BitTorrent 协议 1.0 版中：
        pstrlen = 19
        pstr = "BitTorrent protocol"

    因此长度为：
        49 + len(pstr) = 68 字节长
    """
    length = 49 + 19

    def __init__(self, info_hash: bytes, peer_id: bytes):
        """
        构造握手消息

        :param info_hash: info 字典的 SHA1 哈希
        :param peer_id: 唯一的对等节点 ID
        """
        if isinstance(info_hash, str):
            info_hash = info_hash.encode('utf-8')
        if isinstance(peer_id, str):
            peer_id = peer_id.encode('utf-8')
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self) -> bytes:
        """
        将此对象实例编码为表示整条消息的原始字节（准备传输）
        """
        return struct.pack(
            '>B19s8x20s20s',
            19,                         # 单字节 (B)
            b'BitTorrent protocol',     # 字符串 19s
                                        # 保留 8x（填充字节，无值）
            self.info_hash,             # 字符串 20s
            self.peer_id)               # 字符串 20s

    @classmethod
    def decode(cls, data: bytes):
        """
        将给定的 BitTorrent 消息解码为握手消息，如果不是有效消息则返回 None
        """
        logging.debug('解码长度为 {length} 的握手'.format(
            length=len(data)))
        if len(data) < (49 + 19):
            return None
        parts = struct.unpack('>B19s8x20s20s', data)
        return cls(info_hash=parts[2], peer_id=parts[3])

    def __str__(self):
        return 'Handshake'


class KeepAlive(PeerMessage):
    """
    Keep-Alive 消息没有负载，长度设置为零

    消息格式：
        <len=0000>
    """
    def __str__(self):
        return 'KeepAlive'


class BitField(PeerMessage):
    """
    BitField 是一个可变长度的消息，其中负载是一个位数组，表示对等节点拥有的（1）或不拥有的（0）所有片段

    消息格式：
        <len=0001+X><id=5><bitfield>
    """
    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data)

    def encode(self) -> bytes:
        """
        将此对象实例编码为表示整条消息的原始字节（准备传输）
        """
        bits_length = len(self.bitfield)
        return struct.pack('>Ib' + str(bits_length) + 's',
                           1 + bits_length,
                           PeerMessage.BitField,
                           self.bitfield)

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack('>I', data[:4])[0]
        logging.debug('解码长度为 {length} 的 BitField'.format(
            length=message_length))

        parts = struct.unpack('>Ib' + str(message_length - 1) + 's', data)
        return cls(parts[2])

    def __str__(self):
        return 'BitField'


class Interested(PeerMessage):
    """
    感兴趣的消息是固定长度的，除了消息标识符外没有负载。用于相互通知对下载片段感兴趣

    消息格式：
        <len=0001><id=2>
    """

    def encode(self) -> bytes:
        """
        将此对象实例编码为表示整条消息的原始字节（准备传输）
        """
        return struct.pack('>Ib',
                           1,  # 消息长度
                           PeerMessage.Interested)

    def __str__(self):
        return 'Interested'


class NotInterested(PeerMessage):
    """
    不感兴趣的消息是固定长度的，除了消息标识符外没有负载。用于相互通知对下载片段不感兴趣

    消息格式：
        <len=0001><id=3>
    """
    def __str__(self):
        return 'NotInterested'


class Choke(PeerMessage):
    """
    阻塞消息用于告诉另一个对等节点停止发送请求消息，直到解除阻塞

    消息格式：
        <len=0001><id=0>
    """
    def __str__(self):
        return 'Choke'


class Unchoke(PeerMessage):
    """
    解除对对岸对等节点的阻塞，使该对等节点能够开始从远程对等节点请求片段

    消息格式：
        <len=0001><id=1>
    """
    def __str__(self):
        return 'Unchoke'


class Have(PeerMessage):
    """
    表示远程对等节点成功下载的片段。片段是 torrent 片段的从零开始的索引
    """
    def __init__(self, index: int):
        self.index = index

    def encode(self):
        return struct.pack('>IbI',
                           5,  # 消息长度
                           PeerMessage.Have,
                           self.index)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('解码长度为 {length} 的 Have'.format(
            length=len(data)))
        index = struct.unpack('>IbI', data)[2]
        return cls(index)

    def __str__(self):
        return 'Have'


class Request(PeerMessage):
    """
    用于请求片段的块（即部分片段）的消息

    每个块的请求大小为 2^14 字节，除了最后一个块可能更小（因为不是所有片段都能被请求大小整除）

    消息格式：
        <len=0013><id=6><index><begin><length>
    """
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        """
        构造 Request 消息

        :param index: 从零开始的片段索引
        :param begin: 片段内的从零开始的偏移量
        :param length: 请求的数据长度（默认 2^14）
        """
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerMessage.Request,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('解码长度为 {length} 的 Request'.format(
            length=len(data)))
        # 元组（消息长度、id、索引、开始、长度）
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Request'


class Piece(PeerMessage):
    """
    块是元信息中提到的片段的一部分。官方规范也将它们称为片段 - 这相当令人困惑
    非官方规范将它们称为块

    所以这个类被命名为 `Piece` 以匹配规范中的消息，但实际上，它代表一个 `Block`（在规范中不存在）

    消息格式：
        <length prefix><message ID><index><begin><block>
    """
    # 没有块数据的 Piece 消息长度
    length = 9

    def __init__(self, index: int, begin: int, block: bytes):
        """
        构造 Piece 消息

        :param index: 从零开始的片段索引
        :param begin: 片段内的从零开始的偏移量
        :param block: 块数据
        """
        self.index = index
        self.begin = begin
        self.block = block

    def encode(self):
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's',
                           message_length,
                           PeerMessage.Piece,
                           self.index,
                           self.begin,
                           self.block)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('解码长度为 {length} 的 Piece'.format(
            length=len(data)))
        length = struct.unpack('>I', data[:4])[0]
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's',
                              data[:length+4])
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Piece'


class Cancel(PeerMessage):
    """
    取消消息用于取消先前请求的块（事实上，除了 id 之外，该消息与 Request 消息相同）

    消息格式：
         <len=0013><id=8><index><begin><length>
    """
    def __init__(self, index, begin, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerMessage.Cancel,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('解码长度为 {length} 的 Cancel'.format(
            length=len(data)))
        # 元组（消息长度、id、索引、开始、长度）
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Cancel'
