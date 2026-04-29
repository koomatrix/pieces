import sys
sys.path.insert(0, '.')
from pieces.tracker import _calculate_peer_id

import socket
from struct import unpack

def peerId生成():
    peer_id = _calculate_peer_id()
    print(f'Peer ID: {peer_id}')
    print(f'Peer ID 长度: {len(peer_id)} 字节')
    print(f'格式: -PC0001-<12位随机数字>')
    print()

    # 展示 peer_id 的结构
    prefix = peer_id[:8]
    random_part = peer_id[8:]
    print(f'前缀: {prefix}')
    print(f'随机部分: {random_part}')
    print(f'随机部分长度: {len(random_part)}')

def peer列表解析():

    sys.path.insert(0, '.')

    # 模拟 compact 格式的 peer 列表
    # 每个 peer 占 6 字节：4 字节 IP + 2 字节端口
    # 示例：3 个 peer
    compact_peers = b'\\x7f\\x00\\x00\\x01\\x1a\\xe1\\xc0\\xa8\\x01\\x01\\x1d\\xc8\\x0a\\x00\\x00\\x02\\x07\\xd0'
    print(f'Compact 格式数据 (原始): {compact_peers}')
    print(f'数据长度: {len(compact_peers)} 字节')
    print(f'Peer 数量: {len(compact_peers) // 6}')
    print()

    # 解析每个 peer
    peers = []
    for i in range(0, len(compact_peers), 6):
        peer_data = compact_peers[i:i + 6]
        ip_bytes = peer_data[:4]
        port_bytes = peer_data[4:6]

        # IP 解析
        ip = socket.inet_ntoa(ip_bytes)
        # 端口解析（大端序）
        port = unpack('>H', port_bytes)[0]

        peers.append((ip, port))
        print(f'Peer {i // 6 + 1}:')
        print(f'  IP (原始): {ip_bytes} -> {ip}')
        print(f'  端口 (原始): {port_bytes.hex()} -> {port}')
        print()

    print(f'解析结果: {peers}')

if __name__ == '__main__':
    peerId生成()
    peer列表解析()