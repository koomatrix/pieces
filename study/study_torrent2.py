import sys
sys.path.insert(0, '.')
from pieces.bencoding import Decoder, Encoder

print('=== Bencode 编码格式 ===')
print()

# 展示各种类型的编码格式
print('类型 | 格式 | 示例 | 编码结果')
print('-----|------|------|--------')
print('整数 | i<数字>e | 42 | i42e')
print('字符串 | <长度>:<内容> | hello | 5:hello')
print('列表 | l<内容>e | [1,2] | li1ei2ee')
print('字典 | d<键值对>e | {a:1} | d1:ai1ee')
print()

# 实际编码示例
print('实际编码结果:')
print(f'  整数 42: {Encoder(42).encode()}')
print(f'  字符串 hello: {Encoder(b"hello").encode()}')
print(f'  列表 [1,2,3]: {Encoder([1,2,3]).encode()}')

# 字典示例
from collections import OrderedDict
d = OrderedDict([(b'a', 1)])
print(f'  字典 {{\"a\": 1}}: {Encoder(d).encode()}')