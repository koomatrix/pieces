import struct

def 基础示例():
    print('=== struct.unpack 基础示例 ===')
    print()

    # 1. 解析 4 字节无符号整数（大端序）
    data = b'\x00\x00\x10\x00'
    result = struct.unpack('>I', data)[0]
    print(f'数据: {data.hex()}')
    print(f'解析结果 (大端序 unsigned int): {result}')
    print()

    # 2. 解析多个值
    data = b'\x01\x02\x03\x04\x05\x06\x07\x08'
    values = struct.unpack('>HHHH', data)
    print(f'数据: {data.hex()}')
    print(f'解析结果 (4个短整型): {values}')
    print()

    # 3. 混合类型解析
    data = b'\x00\x00\x10\x00\x01\x00\x41\x00'
    result = struct.unpack('>IHxB', data)
    print(f'数据: {data.hex()}')
    print(f'解析结果: int={result[0]}, short={result[1]}, char byte={result[2]:02x}')
    print()

    # 4. 解析字符串（固定长度）
    data = b'helloworld'
    result = struct.unpack('>5s5s', data)
    print(f'数据: {data}')
    print(f'解析结果: {result[0].decode()}, {result[1].decode()}')

def 协议消息示例():
    print()
    print('=== BitTorrent 协议消息示例 ===')
    print()

    # 1. KeepAlive 消息
    keep_alive = b'\x00\x00\x00\x00'
    length = struct.unpack('>I', keep_alive)[0]
    print(f'KeepAlive: {keep_alive.hex()}')
    print(f'  解析: 长度={length}')
    print()

    # 2. Interested 消息
    interested = b'\x00\x00\x00\x01\x02'
    length, msg_id = struct.unpack('>Ib', interested)
    print(f'Interested: {interested.hex()}')
    print(f'  解析: 长度={length}, ID={msg_id}')
    print()

    # 3. Request 消息
    # 格式: <length=13><id=6><index><begin><length>
    request = b'\x00\x00\x00\x0d\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x40\x00'
    length, msg_id, index, begin, block_len = struct.unpack('>IbIII', request)
    print(f'Request: {request.hex()}')
    print(f'  解析: 长度={length}, ID={msg_id}')
    print(f'    piece={index}, offset={begin}, length={block_len}')
    print()

    # 4. 握手消息
    # 格式: <pstrlen=19><pstr=BitTorrent protocol><reserved=8字节><info_hash=20字节><peer_id=20字节>
    handshake = struct.pack('>B19s8x20s20s',
        19,
        b'BitTorrent protocol',
        b'01234567890123456789',
        b'-PC0001-123456789012')
    print(f'握手消息长度: {len(handshake)} 字节')
    print(f'握手消息 (hex): {handshake.hex()}')

    # 解码握手
    parts = struct.unpack('>B19s8x20s20s', handshake)
    print(f'  解码: pstrlen={parts[0]}, pstr={parts[1]}, info_hash={parts[2].hex()}, peer_id={parts[3].decode()}')

def 动态格式字符串示例():
    print()
    print('=== 动态格式字符串示例 ===')
    print()

    piece_index = 5
    offset = 16384
    block_data = b'X' * 100

    # 编码
    format_string = '>IbII' + str(len(block_data)) + 's'
    print(f'动态格式字符串: {format_string}')

    message_length = 9 + len(block_data)
    piece_msg = struct.pack(format_string,
                            message_length,
                            7,  # PIECE ID
                            piece_index,
                            offset,
                            block_data)

    print(f'Piece 消息长度: {len(piece_msg)} 字节')
    print()

    # 解码：正确的方式是先读取长度，再读取整个消息
    length = struct.unpack('>I', piece_msg[:4])[0]
    print(f'消息长度前缀: {length}')

    # 然后读取整个消息（包含长度前缀）
    dynamic_format = '>IbII' + str(length - 9) + 's'
    msg_length, msg_id, index, begin, data = struct.unpack(dynamic_format, piece_msg[:4 + length])

    print(f'解码结果:')
    print(f'  消息长度: {msg_length}')
    print(f'  消息 ID: {msg_id} (Piece)')
    print(f'  Piece 索引: {index}')
    print(f'  偏移量: {begin}')
    print(f'  数据长度: {len(data)}')

if __name__ == '__main__':
    基础示例()
    协议消息示例()
    动态格式字符串示例()