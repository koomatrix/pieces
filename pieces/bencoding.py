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

from collections import OrderedDict


# 表示整数的开始
TOKEN_INTEGER = b'i'

# 表示列表的开始
TOKEN_LIST = b'l'

# 表示字典的开始
TOKEN_DICT = b'd'

# 表示列表、字典和整数值的结束
TOKEN_END = b'e'

# 分隔字符串长度和字符串数据
TOKEN_STRING_SEPARATOR = b':'


class Decoder:
    """
    解码 bencode 编码的字节序列
    """
    def __init__(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError('参数 "data" 必须是 bytes 类型')
        self._data = data
        self._index = 0

    def decode(self):
        """
        解码 bencode 数据并返回对应的 Python 对象

        :return 表示 bencode 数据的 Python 对象
        """
        c = self._peek()
        if c is None:
            raise EOFError('意外的文件结束')
        elif c == TOKEN_INTEGER:
            self._consume()  # 消费标记
            return self._decode_int()
        elif c == TOKEN_LIST:
            self._consume()  # 消费标记
            return self._decode_list()
        elif c == TOKEN_DICT:
            self._consume()  # 消费标记
            return self._decode_dict()
        elif c == TOKEN_END:
            return None
        elif c in b'01234567899':
            return self._decode_string()
        else:
            raise RuntimeError('在位置 {0} 读取到无效的标记'.format(
                str(self._index)))

    def _peek(self):
        """
        返回 bencode 数据中的下一个字符，如果没有则返回 None
        """
        if self._index + 1 >= len(self._data):
            return None
        return self._data[self._index:self._index + 1]

    def _consume(self) -> bytes:
        """
        读取（并消费）数据中的下一个字符
        """
        self._index += 1

    def _read(self, length: int) -> bytes:
        """
        从数据中读取指定长度的字节并返回结果
        """
        if self._index + length > len(self._data):
            raise IndexError('无法从当前位置 {1} 读取 {0} 字节'
                             .format(str(length), str(self._index)))
        res = self._data[self._index:self._index+length]
        self._index += length
        return res

    def _read_until(self, token: bytes) -> bytes:
        """
        从 bencode 数据中读取直到找到给定标记，并返回读取的字符
        """
        try:
            occurrence = self._data.index(token, self._index)
            result = self._data[self._index:occurrence]
            self._index = occurrence + 1
            return result
        except ValueError:
            raise RuntimeError('无法找到标记 {0}'.format(
                str(token)))

    def _decode_int(self):
        return int(self._read_until(TOKEN_END))

    def _decode_list(self):
        res = []
        # 递归解码列表内容
        while self._data[self._index: self._index + 1] != TOKEN_END:
            res.append(self.decode())
        self._consume()  # 消费 END 标记
        return res

    def _decode_dict(self):
        res = OrderedDict()
        while self._data[self._index: self._index + 1] != TOKEN_END:
            key = self.decode()
            obj = self.decode()
            res[key] = obj
        self._consume()  # 消费 END 标记
        return res

    def _decode_string(self):
        bytes_to_read = int(self._read_until(TOKEN_STRING_SEPARATOR))
        data = self._read(bytes_to_read)
        return data


class Encoder:
    """
    将 Python 对象编码为 bencode 字节序列

    支持的 Python 类型：
        - str
        - int
        - list
        - dict
        - bytes

    任何其他类型都将被忽略
    """
    def __init__(self, data):
        self._data = data

    def encode(self) -> bytes:
        """
        将 Python 对象编码为 bencode 二进制字符串

        :return bencode 二进制数据
        """
        return self.encode_next(self._data)

    def encode_next(self, data):
        if type(data) == str:
            return self._encode_string(data)
        elif type(data) == int:
            return self._encode_int(data)
        elif type(data) == list:
            return self._encode_list(data)
        elif type(data) == dict or type(data) == OrderedDict:
            return self._encode_dict(data)
        elif type(data) == bytes:
            return self._encode_bytes(data)
        else:
            return None

    def _encode_int(self, value):
        return str.encode('i' + str(value) + 'e')

    def _encode_string(self, value: str):
        res = str(len(value)) + ':' + value
        return str.encode(res)

    def _encode_bytes(self, value: str):
        result = bytearray()
        result += str.encode(str(len(value)))
        result += b':'
        result += value
        return result

    def _encode_list(self, data):
        result = bytearray('l', 'utf-8')
        result += b''.join([self.encode_next(item) for item in data])
        result += b'e'
        return result

    def _encode_dict(self, data: dict) -> bytes:
        result = bytearray('d', 'utf-8')
        for k, v in data.items():
            key = self.encode_next(k)
            value = self.encode_next(v)
            if key and value:
                result += key
                result += value
            else:
                raise RuntimeError('无效的字典')
        result += b'e'
        return result
