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
import math
import os
import time
from asyncio import Queue
from collections import namedtuple, defaultdict
from hashlib import sha1

from pieces.protocol import PeerConnection, REQUEST_SIZE
from pieces.tracker import Tracker

# 每个 TorrentClient 的最大对等连接数
MAX_PEER_CONNECTIONS = 40


class TorrentClient:
    """
    Torrent 客户端是本地对等节点，用于维护点对点连接以下载和上传给定 torrent 的片段

    启动后，客户端会定期向注册在 torrent 元数据中的 tracker 发起声明调用
    这些调用会返回一个对等节点列表，应该尝试与这些节点交换片段

    每个接收到的对等节点都保存在一个队列中，由 PeerConnection 对象池消费
    有一个固定数量的 PeerConnection 可以与对等节点建立连接
    由于我们没有创建昂贵的线程（或更糟糕的是进程）
    我们可以一次性创建它们，它们将等待队列中有对等节点可供消费
    """
    def __init__(self, torrent):
        self.tracker = Tracker(torrent)
        # 潜在对等节点列表是工作队列，由 PeerConnection 消费
        self.available_peers = Queue()
        # 对等节点列表是可能已连接到对等节点的工作进程列表
        # 否则它们正在等待从 `available_peers` 队列消费新的远程对等节点
        # 这些就是我们的工作进程！
        self.peers = []
        # PieceManager 实现了请求哪些片段的策略，
        # 以及将接收到的片段持久化到磁盘的逻辑
        self.piece_manager = PieceManager(torrent)
        self.abort = False

    async def start(self):
        """
        开始下载此客户端持有的 torrent

        这将导致连接到 tracker 以获取要通信的对等节点列表
        一旦 torrent 完全下载或下载被中止，此方法将完成
        """
        try:
            self.peers = [PeerConnection(self.available_peers,
                                         self.tracker.torrent.info_hash,
                                         self.tracker.peer_id,
                                         self.piece_manager,
                                         self._on_block_retrieved)
                          for _ in range(MAX_PEER_CONNECTIONS)]

            # 上次发起声明调用的时间（时间戳）
            previous = None
            # 声明调用之间的默认间隔（秒）
            interval = 30*60

            while True:
                if self.piece_manager.complete:
                    logging.info('Torrent 完全下载完成！')
                    break
                if self.abort:
                    logging.info('正在中止下载...')
                    break

                current = time.time()
                if (not previous) or (previous + interval < current):
                    response = await self.tracker.connect(
                        first=previous if previous else False,
                        uploaded=self.piece_manager.bytes_uploaded,
                        downloaded=self.piece_manager.bytes_downloaded)

                    if response:
                        previous = current
                        interval = response.interval
                        self._empty_queue()
                        for peer in response.peers:
                            self.available_peers.put_nowait(peer)
                else:
                    await asyncio.sleep(5)
        finally:
            self.stop()
            await self.tracker.close()

    def _empty_queue(self):
        while not self.available_peers.empty():
            self.available_peers.get_nowait()

    def stop(self):
        """
        停止下载或做种过程
        """
        self.abort = True
        for peer in self.peers:
            peer.stop()
        self.piece_manager.close()

    def _on_block_retrieved(self, peer_id, piece_index, block_offset, data):
        """
        当从对等节点检索到块时，由 `PeerConnection` 调用的回调函数

        :param peer_id: 检索到块的对等节点的 ID
        :param piece_index: 此块所属的片段索引
        :param block_offset: 块在其片段内的偏移量
        :param data: 检索到的二进制数据
        """
        self.piece_manager.block_received(
            peer_id=peer_id, piece_index=piece_index,
            block_offset=block_offset, data=data)


class Block:
    """
    块是片段的一部分，这是在节点之间请求和传输的内容

    块通常与 REQUEST_SIZE 大小相同，除了最后一个块可能（很可能）小于 REQUEST_SIZE
    """
    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, piece: int, offset: int, length: int):
        self.piece = piece
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.data = None


class Piece:
    """
    片段是 torrent 内容的一部分。除了 torrent 的最后一个片段外，每个片段的长度相同（最后一个片段可能更短）

    片段是在 torrent 元数据中定义的内容。然而，在节点之间共享数据时使用更小的单位
    这个更小的单位被非官方规范称为 `Block`（官方规范也使用 piece 来称呼这个，这有点令人困惑）
    """
    def __init__(self, index: int, blocks: [], hash_value):
        self.index = index
        self.blocks = blocks
        self.hash = hash_value

    def reset(self):
        """
        将所有块重置为 Missing 状态，无论当前状态如何
        """
        for block in self.blocks:
            block.status = Block.Missing

    def next_request(self) -> Block:
        """
        获取下一个要请求的块
        """
        missing = [b for b in self.blocks if b.status is Block.Missing]
        if missing:
            missing[0].status = Block.Pending
            return missing[0]
        return None

    def block_received(self, offset: int, data: bytes):
        """
        更新块信息，表示给定的块现在已接收

        :param offset: 块偏移量（在片段内）
        :param data: 块数据
        """
        matches = [b for b in self.blocks if b.offset == offset]
        block = matches[0] if matches else None
        if block:
            block.status = Block.Retrieved
            block.data = data
        else:
            logging.warning('尝试完成不存在的块 {offset}'
                            .format(offset=offset))

    def is_complete(self) -> bool:
        """
        检查此片段的所有块是否已检索（无论 SHA1 如何）

        :return: True 或 False
        """
        blocks = [b for b in self.blocks if b.status is not Block.Retrieved]
        return len(blocks) == 0

    def is_hash_matching(self):
        """
        检查所有接收到的块的 SHA1 哈希是否与 torrent 元信息中的片段哈希匹配

        :return: True 或 False
        """
        piece_hash = sha1(self.data).digest()
        return self.hash == piece_hash

    @property
    def data(self):
        """
        返回此片段的数据（按顺序连接所有块）

        注意：此方法不控制所有块是否有效甚至是否存在！
        """
        retrieved = sorted(self.blocks, key=lambda b: b.offset)
        blocks_data = [b.data for b in retrieved]
        return b''.join(blocks_data)

# 用于跟踪待处理请求的类型，可以重新发起请求
PendingRequest = namedtuple('PendingRequest', ['block', 'added'])


class PieceManager:
    """
    PieceManager 负责跟踪连接的对等节点可用的所有片段，
    以及我们可供其他对等节点使用的片段

    在此实现中，选择请求哪个片段的策略尽可能简单
    """
    def __init__(self, torrent):
        self.torrent = torrent
        self.peers = {}
        self.pending_blocks = []
        self.missing_pieces = []
        self.ongoing_pieces = []
        self.have_pieces = []
        self.max_pending_time = 300 * 1000  # 5 分钟
        self.missing_pieces = self._initiate_pieces()
        self.total_pieces = len(torrent.pieces)
        self.fd = os.open(self.torrent.output_file,  os.O_RDWR | os.O_CREAT)

    def _initiate_pieces(self) -> [Piece]:
        """
        根据此 torrent 的片段数量和请求大小，预先构建片段和块列表
        """
        torrent = self.torrent
        pieces = []
        total_pieces = len(torrent.pieces)
        std_piece_blocks = math.ceil(torrent.piece_length / REQUEST_SIZE)

        for index, hash_value in enumerate(torrent.pieces):
            # 每个片段的块数可以使用请求大小作为片段长度的除数来计算
            # 然而，最后一个片段的块数可能比"常规"片段少，
            # 而且最后一个块可能比其他块小
            if index < (total_pieces - 1):
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(std_piece_blocks)]
            else:
                last_length = torrent.total_size % torrent.piece_length
                num_blocks = math.ceil(last_length / REQUEST_SIZE)
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(num_blocks)]

                if last_length % REQUEST_SIZE > 0:
                    # 最后一个片段的最后一个块可能比普通请求大小小
                    last_block = blocks[-1]
                    last_block.length = last_length % REQUEST_SIZE
                    blocks[-1] = last_block
            pieces.append(Piece(index, blocks, hash_value))
        return pieces

    def close(self):
        """
        关闭 PieceManager 使用的任何资源（如打开的文件）
        """
        if self.fd:
            os.close(self.fd)
            self.fd = None

    @property
    def complete(self):
        """
        检查此 torrent 的所有片段是否已下载

        :return: 如果所有片段完全下载则返回 True，否则返回 False
        """
        return len(self.have_pieces) == self.total_pieces

    @property
    def bytes_downloaded(self) -> int:
        """
        获取已下载的字节数

        此方法只计算完整的、已验证的片段，而不是单个块
        """
        return len(self.have_pieces) * self.torrent.piece_length

    @property
    def bytes_uploaded(self) -> int:
        # TODO 添加发送数据的支持
        return 0

    def add_peer(self, peer_id, bitfield):
        """
        添加对等节点和表示对等节点拥有的片段的位字段
        """
        self.peers[peer_id] = bitfield

    def update_peer(self, peer_id, index: int):
        """
        更新对等节点拥有哪些片段的信息（反映 Have 消息）
        """
        if peer_id in self.peers:
            self.peers[peer_id][index] = 1

    def remove_peer(self, peer_id):
        """
        尝试删除先前添加的对等节点（例如，当对等节点连接断开时使用）
        """
        if peer_id in self.peers:
            del self.peers[peer_id]

    def next_request(self, peer_id) -> Block:
        """
        获取应该从给定对等节点请求的下一个块

        如果没有更多块可检索，或者此对等节点没有任何缺失的片段，则返回 None
        """
        # 实现的请求哪个片段的算法很简单
        # 这应该优先替换为"最稀有片段优先"算法的实现
        #
        # 该算法尝试按顺序下载片段，并会尝试完成已开始的片段，然后再开始新的片段
        #
        # 1. 检查任何待处理的块，看是否有任何请求应该因超时而重新发起
        # 2. 检查正在进行的片段以获取下一个要请求的块
        # 3. 检查此对等节点是否有任何尚未开始的缺失片段
        if peer_id not in self.peers:
            return None

        block = self._expired_requests(peer_id)
        if not block:
            block = self._next_ongoing(peer_id)
            if not block:
                block = self._get_rarest_piece(peer_id).next_request()
        return block

    def block_received(self, peer_id, piece_index, block_offset, data):
        """
        当块成功被对等节点检索到时，必须调用此方法

        一旦检索到完整的片段，就会进行 SHA1 哈希检查。如果检查失败，
        所有片段块都会被放回缺失状态以便重新获取。如果哈希成功，
        部分片段会被写入磁盘，片段被标记为 Have
        """
        logging.debug('收到片段 {piece_index} 的块 {block_offset} '
                      '来自对等节点 {peer_id}: '.format(block_offset=block_offset,
                                                     piece_index=piece_index,
                                                     peer_id=peer_id))

        # 从待处理请求中移除
        for index, request in enumerate(self.pending_blocks):
            if request.block.piece == piece_index and \
               request.block.offset == block_offset:
                del self.pending_blocks[index]
                break

        pieces = [p for p in self.ongoing_pieces if p.index == piece_index]
        piece = pieces[0] if pieces else None
        if piece:
            piece.block_received(block_offset, data)
            if piece.is_complete():
                if piece.is_hash_matching():
                    self._write(piece)
                    self.ongoing_pieces.remove(piece)
                    self.have_pieces.append(piece)
                    complete = (self.total_pieces -
                                len(self.missing_pieces) -
                                len(self.ongoing_pieces))
                    logging.info(
                        '{complete} / {total} 个片段已下载 {per:.3f} %'
                        .format(complete=complete,
                                total=self.total_pieces,
                                per=(complete/self.total_pieces)*100))
                else:
                    logging.info('丢弃损坏的片段 {index}'
                                 .format(index=piece.index))
                    piece.reset()
        else:
            logging.warning('尝试更新不在进行中的片段！')

    def _expired_requests(self, peer_id) -> Block:
        """
        遍历先前请求的块，如果有任何块在请求状态中停留的时间超过 `MAX_PENDING_TIME`，
        则返回该块以重新请求

        如果没有待处理的块，则返回 None
        """
        current = int(round(time.time() * 1000))
        for request in self.pending_blocks:
            if self.peers[peer_id][request.block.piece]:
                if request.added + self.max_pending_time < current:
                    logging.info('重新请求片段 {piece} 的块 {block}'.format(
                                    block=request.block.offset,
                                    piece=request.block.piece))
                    # 重置过期计时器
                    request.added = current
                    return request.block
        return None

    def _next_ongoing(self, peer_id) -> Block:
        """
        遍历正在进行的片段并返回下一个要请求的块，如果没有块可请求则返回 None
        """
        for piece in self.ongoing_pieces:
            if self.peers[peer_id][piece.index]:
                # 此片段中还有块可请求吗？
                block = piece.next_request()
                if block:
                    self.pending_blocks.append(
                        PendingRequest(block, int(round(time.time() * 1000))))
                    return block
        return None

    def _get_rarest_piece(self, peer_id):
        """
        给定当前缺失片段列表，首先获取最稀有的片段
        （即其相邻对等节点中最少拥有的片段）
        """
        piece_count = defaultdict(int)
        for piece in self.missing_pieces:
            if not self.peers[peer_id][piece.index]:
                continue
            for p in self.peers:
                if self.peers[p][piece.index]:
                    piece_count[piece] += 1

        rarest_piece = min(piece_count, key=lambda p: piece_count[p])
        self.missing_pieces.remove(rarest_piece)
        self.ongoing_pieces.append(rarest_piece)
        return rarest_piece

    def _next_missing(self, peer_id) -> Block:
        """
        遍历缺失的片段并返回下一个要请求的块，如果没有块可请求则返回 None

        这将把片段状态从缺失更改为进行中 - 因此下次调用此函数时不会继续该片段的块，
        而是获取下一个缺失的片段
        """
        for index, piece in enumerate(self.missing_pieces):
            if self.peers[peer_id][piece.index]:
                # 将此片段从缺失移动到进行中
                piece = self.missing_pieces.pop(index)
                self.ongoing_pieces.append(piece)
                # 缺失的片段没有任何先前请求的块（否则它就是进行中的）
                return piece.next_request()
        return None

    def _write(self, piece):
        """
        将给定的片段写入磁盘
        """
        pos = piece.index * self.torrent.piece_length
        os.lseek(self.fd, pos, os.SEEK_SET)
        os.write(self.fd, piece.data)
