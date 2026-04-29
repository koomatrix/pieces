import sys
import struct
sys.path.insert(0, '.')

print('=== 握手协议示例 ===')
print()

# 模拟 info_hash 和 peer_id
info_hash = b'4344503b7e797ebf31582327a5baae35b11bda01'[:20]
peer_id = b'-PC0001-123456789012'[:20]

# 编码握手
handshake = struct.pack('>B19s8x20s20s',
    19,                         # pstrlen
    b'BitTorrent protocol',     # pstr
                                # 8字节保留
    info_hash,                  # 20字节
    peer_id)                    # 20字节

print(f'握手消息长度: {len(handshake)} 字节')
print(f'原始数据 (hex): {handshake.hex()[:80]}...')
print()

# 解码握手
parts = struct.unpack('>B19s8x20s20s', handshake)
print(f'解码结果:')
print(f'  pstrlen: {parts[0]}')
print(f'  pstr: {parts[1]}')
print(f'  info_hash: {parts[2].hex()}')
print(f'  peer_id: {parts[3].decode()}')


print('=== 常见消息格式示例 ===')
print()

# 消息类型定义
class MsgType:
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8



# 1. KeepAlive (长度为0)
keep_alive = struct.pack('>I', 0)
print(f'KeepAlive: {keep_alive.hex()} (4字节)')
print(f'  解析: 长度={struct.unpack(">I", keep_alive)[0]}')
print()

# 2. Interested (无payload)
interested = struct.pack('>Ib', 1, MsgType.INTERESTED)
print(f'Interested: {interested.hex()} (5字节)')
length, msg_id = struct.unpack('>Ib', interested)
print(f'  解析: 长度={length}, ID={msg_id} (Interested)')
print()

# 3. Unchoke (无payload)
unchoke = struct.pack('>Ib', 1, MsgType.UNCHOKE)
print(f'Unchoke: {unchoke.hex()} (5字节)')
length, msg_id = struct.unpack('>Ib', unchoke)
print(f'  解析: 长度={length}, ID={msg_id} (Unchoke)')
print()

# 4. Request (有payload)
request = struct.pack('>IbIII',
    13,              # 消息长度 (1+4+4+4)
    MsgType.REQUEST, # ID=6
    0,               # piece index
    0,               # offset (begin)
    16384)           # length (2^14 = 16KB)
print(f'Request: {request.hex()} (17字节)')
length, msg_id, index, begin, length_val = struct.unpack('>IbIII', request)
print(f'  解析: 长度={length}, ID={msg_id} (Request)')
print(f'    piece={index}, offset={begin}, length={length_val}')
print()

# 5. Have (有payload)
have = struct.pack('>IbI', 5, MsgType.HAVE, 123)
print(f'Have: {have.hex()} (9字节)')
length, msg_id, piece_index = struct.unpack('>IbI', have)
print(f'  解析: 长度={length}, ID={msg_id} (Have)')
print(f'    piece index={piece_index}')





print('=== Piece 消息示例 ===')
print()

# Piece 消息包含实际数据
piece_index = 10
offset = 0
block_data = b'A' * 100  # 100字节的示例数据

# 编码
message_length = 9 + len(block_data)  # 4(长度前缀) + 1(ID) + 4(index) + 4(offset) + block_data
piece_msg = struct.pack('>IbII' + str(len(block_data)) + 's',
    message_length,
    7,  # PIECE message ID
    piece_index,
    offset,
    block_data)

print(f'Piece 消息长度: {len(piece_msg)} 字节')
print(f'原始数据 (前40字节): {piece_msg.hex()[:80]}')
print()

# 解码
length = struct.unpack('>I', piece_msg[:4])[0]
msg_id = struct.unpack('>b', piece_msg[4:5])[0]
index = struct.unpack('>I', piece_msg[5:9])[0]
begin = struct.unpack('>I', piece_msg[9:13])[0]
data = piece_msg[13:]

print(f'解码结果:')
print(f'  消息长度: {length}')
print(f'  消息 ID: {msg_id} (Piece)')
print(f'  Piece 索引: {index}')
print(f'  偏移量: {begin}')
print(f'  数据长度: {len(data)} 字节')
print(f'  数据内容: {data[:20]}...')
print()

print('=== BitField 示例 ===')
print()

# BitField: 假设有 8 个 pieces，peer 拥有 piece 0, 3, 5, 7
# 二进制: 10101010 -> 十六进制: AA
bitfield_data = b'\\xaa'

# 编码
msg_length = 1 + len(bitfield_data)
bitfield_msg = struct.pack('>Ib' + str(len(bitfield_data)) + 's',
    msg_length,
    5,  # BITFIELD message ID
    bitfield_data)

print(f'BitField 消息: {bitfield_msg.hex()}')
length, msg_id, bits = struct.unpack('>Ib1s', bitfield_msg)
print(f'  解码: 长度={length}, ID={msg_id} (BitField)')
print(f'  BitField 数据 (hex): {bits.hex()}')
print(f'  BitField 数据 (binary): {bits[0]:08b}')
print(f'  拥有的 pieces: {[i for i in range(8) if (bits[0] >> (7-i)) & 1]}')