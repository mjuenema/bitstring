#
# Little script for testing micropython-bitstring
#


import bitstring

# Some variations of constructing a BitArray
bitstring.BitArray(hex='0x000001b3')
bitstring.BitArray(bin='0011 00')
bitstring.BitArray(int=32, length=7)
bitstring.BitArray(intbe=-32768, length=16)
bitstring.BitArray(float=10.3, length=32)
bitstring.BitArray(floatle=-273.15, length=64)
bitstring.BitArray(bytes=b'\x00\x01\x02\xff', length=28)
bitstring.BitArray(bool=True)

# Conversions
bitstring.BitArray(int=32, length=7).bin
bitstring.BitArray(int=32, length=7).tobytes()
bitstring.BitArray(bitstring.Bits(hex='0x000001b3'))

# Comparison
bitstring.BitArray(hex='0x000001b3') == bitstring.BitArray(hex='0x000001b3')

# Unary operation
~bitstring.BitArray(hex='0x000001b3')

# Slicing and joining
bitstring.BitArray(hex='0x000001b3')[5:10]
bitstring.BitArray(hex='0x000001b3') + bitstring.BitArray(int=32, length=7)
