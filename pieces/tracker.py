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
import aiohttp
import random
import logging
import socket
from struct import unpack
from urllib.parse import urlencode

from . import bencoding


class TrackerResponse:
    """
    成功连接到 tracker 的声明 URL 后，来自 tracker 的响应

    即使从网络角度来看连接成功，tracker 也可能返回错误（在 `failure` 属性中说明）
    """

    def __init__(self, response: dict):
        self.response = response

    @property
    def failure(self):
        """
        如果此响应是失败的响应，这是 tracker 请求失败的原因的错误消息

        如果没有发生错误，这将返回 None
        """
        if b'failure reason' in self.response:
            return self.response[b'failure reason'].decode('utf-8')
        return None

    @property
    def interval(self) -> int:
        """
        客户端在发送定期请求到 tracker 之间应等待的间隔（秒）
        """
        return self.response.get(b'interval', 0)

    @property
    def complete(self) -> int:
        """
        拥有完整文件的对等节点数量，即种子（seeders）
        """
        return self.response.get(b'complete', 0)

    @property
    def incomplete(self) -> int:
        """
        非种子对等节点数量，即"吸血者"（leechers）
        """
        return self.response.get(b'incomplete', 0)

    @property
    def peers(self):
        """
        每个对等节点的元组列表，结构为 (ip, port)
        """
        # BitTorrent 规范指定了两种类型的响应。一种是 peers 字段是字典列表，
        # 另一种是所有 peers 都编码在一个字符串中
        peers = self.response[b'peers']
        if type(peers) == list:
            logging.debug('Tracker 返回字典模型的对等节点')
            # 字典格式：每个 peer 是 {'ip': x.x.x.x, 'port': xxxx}
            return [(peer[b'ip'].decode('utf-8'), peer[b'port'])
                    for peer in peers]
        else:
            logging.debug('Tracker 返回二进制模型的对等节点')

            # 将字符串分割成长度为 6 字节的片段，其中前 4 个字符是 IP，最后 2 个是 TCP 端口
            peers = [peers[i:i+6] for i in range(0, len(peers), 6)]

            # 将编码的地址转换为元组列表
            return [(socket.inet_ntoa(p[:4]), _decode_port(p[4:]))
                    for p in peers]

    def __str__(self):
        return "不完整：{incomplete}\n" \
               "完整：{complete}\n" \
               "间隔：{interval}\n" \
               "对等节点：{peers}\n".format(
                   incomplete=self.incomplete,
                   complete=self.complete,
                   interval=self.interval,
                   peers=", ".join([x for (x, _) in self.peers]))


class Tracker:
    """
    表示与给定 Torrent 的 tracker 的连接，该 Torrent 处于下载或做种状态
    """

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = _calculate_peer_id()
        self.http_client = None

    async def connect(self,
                      first: bool = None,
                      uploaded: int = 0,
                      downloaded: int = 0):
        """
        向 tracker 发起声明调用以更新我们的统计信息，并获取可连接的对等节点列表

        如果调用成功，调用此函数的结果将更新对等节点列表

        :param first: 这是否是第一次声明调用
        :param uploaded: 上传的总字节数
        :param downloaded: 下载的总字节数
        """
        # 延迟初始化 ClientSession（需要在事件循环运行后）
        if self.http_client is None:
            connector = aiohttp.TCPConnector(ssl=False)
            self.http_client = aiohttp.ClientSession(connector=connector)

        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'port': 6889,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'left': self.torrent.total_size - downloaded,
            'compact': 1}
        if first:
            params['event'] = 'started'

        url = self.torrent.announce + '?' + urlencode(params)
        logging.info('连接到 tracker：' + url)

        async with self.http_client.get(url) as response:
            if not response.status == 200:
                raise ConnectionError('无法连接到 tracker：状态码 {}'.format(response.status))
            data = await response.read()
            self.raise_for_error(data)
            return TrackerResponse(bencoding.Decoder(data).decode())

    async def close(self):
        if self.http_client is not None:
            await self.http_client.close()

    def raise_for_error(self, tracker_response):
        """
        一个（hacky）修复，用于检测 tracker 的错误，即使响应的状态码为 200
        """
        try:
            # 包含错误的 tracker 响应将只有 utf-8 消息
            # 参见：https://wiki.theory.org/index.php/BitTorrentSpecification#Tracker_Response
            message = tracker_response.decode("utf-8")
            if "failure" in message:
                raise ConnectionError('无法连接到 tracker：{}'.format(message))

        # 成功的 tracker 响应将包含非 unicode 数据，因此忽略此异常是安全的
        except UnicodeDecodeError:
            pass

    def _construct_tracker_parameters(self):
        """
        构造向 tracker 发起声明调用时使用的 URL 参数
        """
        return {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'port': 6889,
            # TODO 与 tracker 通信时更新统计信息
            'uploaded': 0,
            'downloaded': 0,
            'left': 0,
            'compact': 1}


def _calculate_peer_id():
    """
    计算并返回唯一的对等节点 ID

    `peer id` 是一个 20 字节长的标识符。此实现使用 Azureus 风格的 `-PC1000-<随机字符>`
˙
    阅读更多：
        https://wiki.theory.org/BitTorrentSpecification#peer_id
    """
    return '-PC0001-' + ''.join(
        [str(random.randint(0, 9)) for _ in range(12)])


def _decode_port(port):
    """
    将 32 位打包二进制端口号转换为整数
    """
    # 从 C 风格的大端序编码的无符号短整型转换
    return unpack(">H", port)[0]
