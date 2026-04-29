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

import argparse
import asyncio
import signal
import logging

from concurrent.futures import CancelledError

from pieces.torrent import Torrent
from pieces.client import TorrentClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('torrent',
                        help='要下载的 .torrent 文件')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='启用详细输出')

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    client = TorrentClient(Torrent(args.torrent))
    task = loop.create_task(client.start())

    def signal_handler(*_):
        logging.info('正在退出，请等待所有内容关闭...')
        client.stop()
        task.cancel()

    signal.signal(signal.SIGINT, signal_handler)

    try:
        loop.run_until_complete(task)
    except CancelledError:
        logging.warning('事件循环被取消')
