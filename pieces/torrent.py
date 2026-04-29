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

from hashlib import sha1
from collections import namedtuple
from typing import Optional, List

from . import bencoding

# 表示 torrent 中的文件（即要写入磁盘的文件）
TorrentFile = namedtuple('TorrentFile', ['name', 'length'])


class Torrent:
    """
    表示 .torrent 文件中保存的 torrent 元数据。它基本上是带有实用函数的 bencode 数据的包装器

    此类不包含下载过程中的任何会话状态
    """
    def __init__(self, filename):
        self.filename = filename
        self.files = []

        with open(self.filename, 'rb') as f:
            meta_info = f.read()
            self.meta_info = bencoding.Decoder(meta_info).decode()
            info = bencoding.Encoder(self.meta_info[b'info']).encode()
            self.info_hash = sha1(info).digest()
            self._identify_files()

    def _identify_files(self):
        """
        识别此 torrent 中包含的文件
        """
        if self.multi_file:
            # TODO 添加对多文件 torrent 的支持
            raise RuntimeError('不支持多文件 torrent！')
        self.files.append(
            TorrentFile(
                self.meta_info[b'info'][b'name'].decode('utf-8'),
                self.meta_info[b'info'][b'length']))

    @property
    def announce(self) -> str:
        """
        tracker 的声明 URL
        """
        return self.meta_info[b'announce'].decode('utf-8')

    @property
    def announce_list(self) -> Optional[List[List[str]]]:
        """
        备用 Tracker 列表（BEP 12）
        返回嵌套列表，如 [['http://tracker1'], ['http://tracker2', 'http://tracker3']]
        """
        if b'announce-list' not in self.meta_info:
            return None
        return [
            [tier.decode('utf-8') for tier in tracker_list]
            for tracker_list in self.meta_info[b'announce-list']
        ]

    @property
    def multi_file(self) -> bool:
        """
        此 torrent 是否包含多个文件？
        """
        # 如果 info 字典包含 files 元素，则它是多文件 torrent
        return b'files' in self.meta_info[b'info']

    @property
    def piece_length(self) -> int:
        """
        获取每个片段的长度（字节）
        """
        return self.meta_info[b'info'][b'piece length']

    @property
    def total_size(self) -> int:
        """
        此 torrent 中所有文件的总大小（字节）。对于单文件 torrent，这是唯一的文件；
        对于多文件 torrent，这是所有文件的总和

        :return: 此 torrent 数据的总大小（字节）
        """
        if self.multi_file:
            raise RuntimeError('不支持多文件 torrent！')
        return self.files[0].length

    @property
    def pieces(self):
        # info pieces 是一个表示所有片段 SHA1 哈希的字符串（每个 20 字节长）
        # 读取该数据并将其切片成实际的片段
        data = self.meta_info[b'info'][b'pieces']
        pieces = []
        offset = 0
        length = len(data)

        while offset < length:
            pieces.append(data[offset:offset + 20])
            offset += 20
        return pieces

    @property
    def output_file(self):
        return self.meta_info[b'info'][b'name'].decode('utf-8')

    @property
    def num_pieces(self) -> int:
        """总分块数"""
        return len(self.pieces)

    @property
    def output_name(self) -> str:
        """输出文件名/目录名"""
        return self.meta_info[b'info'][b'name'].decode('utf-8')

    @property
    def creation_date(self) -> Optional[int]:
        """创建时间戳（Unix timestamp）"""
        return self.meta_info.get(b'creation date')

    @property
    def created_by(self) -> Optional[str]:
        """创建工具信息"""
        val = self.meta_info.get(b'created by')
        return val.decode('utf-8') if val else None

    @property
    def comment(self) -> Optional[str]:
        """注释"""
        val = self.meta_info.get(b'comment')
        return val.decode('utf-8') if val else None

    def get_piece_size(self, piece_index: int) -> int:
        """
        获取指定分块的实际大小
        注意：最后一个分块可能小于 piece_length
        """
        if piece_index == self.num_pieces - 1:
            # 最后一个分块
            return self.total_size % self.piece_length or self.piece_length
        return self.piece_length

    def validate_piece(self, piece_index: int, data: bytes) -> bool:
        """
        验证分块数据是否匹配哈希
        """
        if piece_index < 0 or piece_index >= self.num_pieces:
            return False
        expected_hash = self.pieces[piece_index]
        actual_hash = sha1(data).digest()
        return expected_hash == actual_hash

    # def __str__(self):
    #     return '文件名：{0}\n' \
    #            '文件长度：{1}\n' \
    #            '声明 URL：{2}\n' \
    #            '哈希：{3}'.format(self.meta_info[b'info'][b'name'],
    #                               self.meta_info[b'info'][b'length'],
    #                               self.meta_info[b'announce'],
    #                               self.info_hash)

    def __str__(self) -> str:
        lines = [
            f"{'=' * 50}",
            f"Torrent: {self.output_name}",
            f"{'=' * 50}",
            f"Tracker: {self.announce}",
            f"Info Hash: {self.info_hash.hex()}",
            f"Piece Length: {self.piece_length:,} bytes ({self.piece_length / 1024 / 1024:.2f} MB)",
            f"Total Size: {self.total_size:,} bytes ({self.total_size / 1024 / 1024 / 1024:.2f} GB)",
            f"Pieces: {self.num_pieces}",
            f"Files: {len(self.files)}",
            f"Multi-file: {self.multi_file}",
        ]

        if self.comment:
            lines.append(f"Comment: {self.comment}")
        if self.created_by:
            lines.append(f"Created by: {self.created_by}")

        if len(self.files) <= 5:
            lines.append("File List:")
            for f in self.files:
                lines.append(f"  - {f.name} ({f.length:,} bytes)")
        else:
            lines.append(f"File List: ({len(self.files)} files, showing first 3)")
            for f in self.files[:3]:
                lines.append(f"  - {f.name} ({f.length:,} bytes)")
            lines.append(f"  ... and {len(self.files) - 3} more")

        lines.append(f"{'=' * 50}")
        return '\n'.join(lines)
