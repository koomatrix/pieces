from hashlib import sha1
from pieces.bencoding import Decoder, Encoder
from pieces.torrent import Torrent


def parse_torrent_file(filepath: str):
    """解析真实的 torrent 文件"""
    with open(filepath, 'rb') as f:
        data = f.read()

    # 解码 bencode 数据
    decoder = Decoder(data)
    meta_info = decoder.decode()
    print(meta_info)
    # 提取关键信息
    info = meta_info[b'info']
    print(f"文件名: {info[b'name'].decode('utf-8')}")
    print(f"Tracker: {meta_info[b'announce'].decode('utf-8')}")
    print(f"Piece 长度: {info[b'piece length']}")

    return meta_info

def parse_torrent_file2(filepath: str):
    torrent = Torrent(filepath)
    print(torrent)
    return torrent

def calculate_info_hash(meta_info: dict) -> bytes:
    """
    计算 torrent 的 info_hash
    info_hash = SHA1(bencode(info_dict))
    """
    info = meta_info[b'info']
    # 将 info 字典重新编码为 bencode
    info_bencoded = Encoder(info).encode()
    # 计算 SHA1
    return sha1(info_bencoded).digest()
# 使用
# meta = parse_torrent_file("example.torrent")

def decode_multiple(data: bytes) -> list:
    """
    从字节流中解码多个 bencode 对象

    示例:
    b'5:helloi42e' -> [b'hello', 42]
    """
    # 你的代码
    result = []
    while data:
        c = bytes([data[0]])
        if c == b'i':
            data = data[1:]
            end_index = data.find(b'e')
            num = data[0:end_index]
            data = data[end_index:]
            result.append(int(num))
        elif c in b'0123456789':
            colon_index = data.find(b':')
            length = int(data[0:colon_index])
            start_index = colon_index + 1
            end_index = start_index + length
            string_data = data[start_index:end_index]
            data = data[end_index:]
            result.append(string_data)
        elif c == b'e':
            data = data[1:]

    print(result)
    pass


def generate_magnet_link(torrent: Torrent) -> str:
    """
    生成 Magnet URI (BEP 9)
    magnet:?xt=urn:btih:<info_hash>&dn=<name>&tr=<tracker>
    """
    from urllib.parse import quote

    xt = f"urn:btih:{torrent.info_hash.hex()}"
    dn = quote(torrent.output_name)
    tr = quote(torrent.announce)

    return f"magnet:?xt={xt}&dn={dn}&tr={tr}"


def verify_download(torrent: Torrent, file_path: str) -> bool:
    """
    验证已下载文件是否完整且正确
    """
    with open(file_path, 'rb') as f:
        for i, expected_hash in enumerate(torrent.pieces):
            piece_data = f.read(torrent.get_piece_size(i))
            actual_hash = sha1(piece_data).digest()

            if actual_hash != expected_hash:
                print(f"Piece {i} 校验失败!")
                return False

    print("所有分块校验通过!")
    return True


# 示例输出
# magnet:?xt=urn:btih:d54fe8...&dn=ubuntu-16.04-desktop-amd64.iso&tr=http%3A%2F%2Ftorrent.ubuntu.com...


# 测试
# assert decode_multiple(b'5:helloi42e') == [b'hello', 42]
# assert decode_multiple(b'li1ei2ee3:fooe') == [[1, 2], b'foo']


if __name__ == '__main__':
    # meta = parse_torrent_file("data/ubuntu-16.04.1-server-amd64.iso.torrent")

    # decode_multiple(b'5:helloi42e')

    torrent = parse_torrent_file2("../tests/data/ubuntu-16.04-desktop-amd64.iso.torrent")
    link = generate_magnet_link(torrent)
    print(link)