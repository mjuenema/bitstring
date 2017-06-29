#!/usr/bin/env python
"""
This modules is a stripped-down version of the Bitstring package by Scott Griffiths
that works with MicroPython. It defines a single class Bits for the creation
of binary strings. Binary strings created with this module are compatible
with the original Bitstring module.

Example:

     from bitstring import Bits
     s = Bits(float=3.1415, length=32) + Bits(uint=15, length=4) + Bits(bool=True)
     assert len(s) == 32 + 4 + 1

Exceptions:

Error -- Module exception base class.
CreationError -- Error during creation.
InterpretError -- Inappropriate interpretation of binary data.
ByteAlignError -- Whole byte position or length needed.
ReadError -- Reading or peeking past the end of a bitstring.

https://github.com/mjuenema/micropython-bitstring
"""

__licence__ = """
The MIT License

MicroPython-Bitstring module:
Copyright (c) 2017 Markus Juenemann (markus@juenemann.net)

Original Bitstring package:
Copyright (c) 2006-2016 Scott Griffiths (dr.scottgriffiths@gmail.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

__version__ = "0.1.2"

__author__ = "Scott Griffiths, Markus Juenemann"

import sys
import ubinascii
import ustruct

byteorder = sys.byteorder

bytealigned = False
"""Determines whether a number of methods default to working only on byte boundaries."""

# Maximum number of digits to use in __str__ and __repr__.
MAX_CHARS = 250

class Error(Exception):
    """Base class for errors in the bitstring module."""

    def __init__(self, *params):
        self.msg = params[0] if params else ''
        self.params = params[1:]

    def __str__(self):
        if self.params:
            return self.msg.format(*self.params)
        return self.msg


class ReadError(IndexError):
    """Reading or peeking past the end of a bitstring."""

    def __init__(self, *params):
        self.msg = params[0] if params else ''
        self.params = params[1:]

    def __str__(self):
        if self.params:
            return self.msg.format(*self.params)
        return self.msg


class InterpretError(ValueError):
    """Inappropriate interpretation of binary data."""

    def __init__(self, *params):
        self.msg = params[0] if params else ''
        self.params = params[1:]

    def __str__(self):
        if self.params:
            return self.msg.format(*self.params)
        return self.msg


class ByteAlignError(Error):
    """Whole-byte position or length needed."""

    def __init__(self, *params):
        Error.__init__(self, *params)


class CreationError(ValueError):
    """Inappropriate argument during bitstring creation."""

    def __init__(self, *params):
        self.msg = params[0] if params else ''
        self.params = params[1:]

    def __str__(self):
        if self.params:
            return self.msg.format(*self.params)
        return self.msg


class ConstByteStore(object):
    """Stores raw bytes together with a bit offset and length.

    Used internally - not part of public interface.
    """

    __slots__ = ('offset', '_rawarray', 'bitlength')

    def __init__(self, data, bitlength=None, offset=None):
        """data is either a bytearray or a MmapByteArray"""
        self._rawarray = data
        if offset is None:
            offset = 0
        if bitlength is None:
            bitlength = 8 * len(data) - offset
        self.offset = offset
        self.bitlength = bitlength

    def getbit(self, pos):
        assert 0 <= pos < self.bitlength
        byte, bit = divmod(self.offset + pos, 8)
        return bool(self._rawarray[byte] & (128 >> bit))

    def getbyte(self, pos):
        """Direct access to byte data."""
        return self._rawarray[pos]

    def getbyteslice(self, start, end):
        """Direct access to byte data."""
        c = self._rawarray[start:end]
        return c

    @property
    def bytelength(self):
        if not self.bitlength:
            return 0
        sb = self.offset // 8
        eb = (self.offset + self.bitlength - 1) // 8
        return eb - sb + 1

    def __copy__(self):
        return ByteStore(self._rawarray[:], self.bitlength, self.offset)

    def _appendstore(self, store):
        """Join another store on to the end of this one."""
        if not store.bitlength:
            return
        # Set new array offset to the number of bits in the final byte of current array.
        store = offsetcopy(store, (self.offset + self.bitlength) % 8)
        if store.offset:
            # first do the byte with the join.
            # MicroPython's bytearray does not have a pop() method so we have
            # to work around that.
            popval = self._rawarray[-1]
            self._rawarray = self._rawarray[:-1]
            joinval = (popval & (255 ^ (255 >> store.offset)) |
                       (store.getbyte(0) & (255 >> store.offset)))
            self._rawarray.append(joinval)
            self._rawarray.extend(store._rawarray[1:])
        else:
            self._rawarray.extend(store._rawarray)
        self.bitlength += store.bitlength

    def _prependstore(self, store):
        """Join another store on to the start of this one."""
        if not store.bitlength:
            return
            # Set the offset of copy of store so that it's final byte
        # ends in a position that matches the offset of self,
        # then join self on to the end of it.
        store = offsetcopy(store, (self.offset - store.bitlength) % 8)
        assert (store.offset + store.bitlength) % 8 == self.offset % 8
        bit_offset = self.offset % 8
        if bit_offset:
            # first do the byte with the join.
            store.setbyte(-1, (store.getbyte(-1) & (255 ^ (255 >> bit_offset)) | \
                               (self._rawarray[self.byteoffset] & (255 >> bit_offset))))
            store._rawarray.extend(self._rawarray[self.byteoffset + 1: self.byteoffset + self.bytelength])
        else:
            store._rawarray.extend(self._rawarray[self.byteoffset: self.byteoffset + self.bytelength])
        self._rawarray = store._rawarray
        self.offset = store.offset
        self.bitlength += store.bitlength

    @property
    def byteoffset(self):
        return self.offset // 8

    @property
    def rawbytes(self):
        return self._rawarray


class ByteStore(ConstByteStore):
    """Adding mutating methods to ConstByteStore

    Used internally - not part of public interface.
    """
    __slots__ = ()

    def setbit(self, pos):
        assert 0 <= pos < self.bitlength
        byte, bit = divmod(self.offset + pos, 8)
        self._rawarray[byte] |= (128 >> bit)

    def unsetbit(self, pos):
        assert 0 <= pos < self.bitlength
        byte, bit = divmod(self.offset + pos, 8)
        self._rawarray[byte] &= ~(128 >> bit)

    def invertbit(self, pos):
        assert 0 <= pos < self.bitlength
        byte, bit = divmod(self.offset + pos, 8)
        self._rawarray[byte] ^= (128 >> bit)

    def setbyte(self, pos, value):
        self._rawarray[pos] = value

    def setbyteslice(self, start, end, value):
        self._rawarray[start:end] = value


def offsetcopy(s, newoffset):
    """Return a copy of a ByteStore with the newoffset.

    Not part of public interface.
    """
    assert 0 <= newoffset < 8
    if not s.bitlength:
        raise NotImplementedError
        #return copy.copy(s)
    else:
        if newoffset == s.offset % 8:
            return ByteStore(s.getbyteslice(s.byteoffset, s.byteoffset + s.bytelength), s.bitlength, newoffset)
        newdata = []
        d = s._rawarray
        assert newoffset != s.offset % 8
        if newoffset < s.offset % 8:
            # We need to shift everything left
            shiftleft = s.offset % 8 - newoffset
            # First deal with everything except for the final byte
            for x in range(s.byteoffset, s.byteoffset + s.bytelength - 1):
                newdata.append(((d[x] << shiftleft) & 0xff) +\
                               (d[x + 1] >> (8 - shiftleft)))
            bits_in_last_byte = (s.offset + s.bitlength) % 8
            if not bits_in_last_byte:
                bits_in_last_byte = 8
            if bits_in_last_byte > shiftleft:
                newdata.append((d[s.byteoffset + s.bytelength - 1] << shiftleft) & 0xff)
        else: # newoffset > s._offset % 8
            shiftright = newoffset - s.offset % 8
            newdata.append(s.getbyte(0) >> shiftright)
            for x in range(s.byteoffset + 1, s.byteoffset + s.bytelength):
                newdata.append(((d[x - 1] << (8 - shiftright)) & 0xff) +\
                               (d[x] >> shiftright))
            bits_in_last_byte = (s.offset + s.bitlength) % 8
            if not bits_in_last_byte:
                bits_in_last_byte = 8
            if bits_in_last_byte + shiftright > 8:
                newdata.append((d[s.byteoffset + s.bytelength - 1] << (8 - shiftright)) & 0xff)
        new_s = ByteStore(bytearray(newdata), s.bitlength, newoffset)
        assert new_s.offset == newoffset
        return new_s


def equal(a, b):
    """Return True if ByteStores a == b.

    Not part of public interface.
    """
    # We want to return False for inequality as soon as possible, which
    # means we get lots of special cases.
    # First the easy one - compare lengths:
    a_bitlength = a.bitlength
    b_bitlength = b.bitlength
    if a_bitlength != b_bitlength:
        return False
    if not a_bitlength:
        assert b_bitlength == 0
        return True
    # Make 'a' the one with the smaller offset
    if (a.offset % 8) > (b.offset % 8):
        a, b = b, a
    # and create some aliases
    a_bitoff = a.offset % 8
    b_bitoff = b.offset % 8
    a_byteoffset = a.byteoffset
    b_byteoffset = b.byteoffset
    a_bytelength = a.bytelength
    b_bytelength = b.bytelength
    da = a._rawarray
    db = b._rawarray

    # If they are pointing to the same data, they must be equal
    if da is db and a.offset == b.offset:
        return True

    if a_bitoff == b_bitoff:
        bits_spare_in_last_byte = 8 - (a_bitoff + a_bitlength) % 8
        if bits_spare_in_last_byte == 8:
            bits_spare_in_last_byte = 0
        # Special case for a, b contained in a single byte
        if a_bytelength == 1:
            a_val = ((da[a_byteoffset] << a_bitoff) & 0xff) >> (8 - a_bitlength)
            b_val = ((db[b_byteoffset] << b_bitoff) & 0xff) >> (8 - b_bitlength)
            return a_val == b_val
        # Otherwise check first byte
        if da[a_byteoffset] & (0xff >> a_bitoff) != db[b_byteoffset] & (0xff >> b_bitoff):
            return False
        # then everything up to the last
        b_a_offset = b_byteoffset - a_byteoffset
        for x in range(1 + a_byteoffset, a_byteoffset + a_bytelength - 1):
            if da[x] != db[b_a_offset + x]:
                return False
        # and finally the last byte
        return (da[a_byteoffset + a_bytelength - 1] >> bits_spare_in_last_byte ==
                db[b_byteoffset + b_bytelength - 1] >> bits_spare_in_last_byte)

    assert a_bitoff != b_bitoff
    # This is how much we need to shift a to the right to compare with b:
    shift = b_bitoff - a_bitoff
    # Special case for b only one byte long
    if b_bytelength == 1:
        assert a_bytelength == 1
        a_val = ((da[a_byteoffset] << a_bitoff) & 0xff) >> (8 - a_bitlength)
        b_val = ((db[b_byteoffset] << b_bitoff) & 0xff) >> (8 - b_bitlength)
        return a_val == b_val
    # Special case for a only one byte long
    if a_bytelength == 1:
        assert b_bytelength == 2
        a_val = ((da[a_byteoffset] << a_bitoff) & 0xff) >> (8 - a_bitlength)
        b_val = ((db[b_byteoffset] << 8) + db[b_byteoffset + 1]) << b_bitoff
        b_val &= 0xffff
        b_val >>= 16 - b_bitlength
        return a_val == b_val

    # Compare first byte of b with bits from first byte of a
    if (da[a_byteoffset] & (0xff >> a_bitoff)) >> shift != db[b_byteoffset] & (0xff >> b_bitoff):
        return False
    # Now compare every full byte of b with bits from 2 bytes of a
    for x in range(1, b_bytelength - 1):
        # Construct byte from 2 bytes in a to compare to byte in b
        b_val = db[b_byteoffset + x]
        a_val = ((da[a_byteoffset + x - 1] << 8) + da[a_byteoffset + x]) >> shift
        a_val &= 0xff
        if a_val != b_val:
            return False

    # Now check bits in final byte of b
    final_b_bits = (b.offset + b_bitlength) % 8
    if not final_b_bits:
        final_b_bits = 8
    b_val = db[b_byteoffset + b_bytelength - 1] >> (8 - final_b_bits)
    final_a_bits = (a.offset + a_bitlength) % 8
    if not final_a_bits:
        final_a_bits = 8
    if b.bytelength > a_bytelength:
        assert b_bytelength == a_bytelength + 1
        a_val = da[a_byteoffset + a_bytelength - 1] >> (8 - final_a_bits)
        a_val &= 0xff >> (8 - final_b_bits)
        return a_val == b_val
    assert a_bytelength == b_bytelength
    a_val = da[a_byteoffset + a_bytelength - 2] << 8
    a_val += da[a_byteoffset + a_bytelength - 1]
    a_val >>= (8 - final_a_bits)
    a_val &= 0xff >> (8 - final_b_bits)
    return a_val == b_val


# This creates a dictionary for every possible byte with the value being
# the key with its bits reversed.
BYTE_REVERSAL_DICT = dict()

# For Python 2.x/ 3.x coexistence
# Yes this is very very hacky.
try:
    xrange
    for i in range(256):
        BYTE_REVERSAL_DICT[i] = chr(int("{0:08b}".format(i)[:-1], 2))
except NameError:
    for i in range(256):
        BYTE_REVERSAL_DICT[i] = bytes([int("{0:08b}".format(i)[:-1], 2)])
    xrange = range
    basestring = str

# Python 2.x octals start with '0', in Python 3 it's '0o'
LEADING_OCT_CHARS = len(oct(1)) - 1

def tidy_input_string(s):
    """Return string made lowercase and with all whitespace removed."""
    s = ''.join(s.split()).lower()
    return s

INIT_NAMES = ('uint', 'int', 'ue', 'se', 'sie', 'uie', 'hex', 'oct', 'bin', 'bits',
              'uintbe', 'intbe', 'uintle', 'intle', 'uintne', 'intne',
              'float', 'floatbe', 'floatle', 'floatne', 'bytes', 'bool', 'pad')

# These replicate the struct.pack codes
# Big-endian
REPLACEMENTS_BE = {'b': 'intbe:8', 'B': 'uintbe:8',
                   'h': 'intbe:16', 'H': 'uintbe:16',
                   'l': 'intbe:32', 'L': 'uintbe:32',
                   'q': 'intbe:64', 'Q': 'uintbe:64',
                   'f': 'floatbe:32', 'd': 'floatbe:64'}
# Little-endian
REPLACEMENTS_LE = {'b': 'intle:8', 'B': 'uintle:8',
                   'h': 'intle:16', 'H': 'uintle:16',
                   'l': 'intle:32', 'L': 'uintle:32',
                   'q': 'intle:64', 'Q': 'uintle:64',
                   'f': 'floatle:32', 'd': 'floatle:64'}

# Size in bytes of all the pack codes.
PACK_CODE_SIZE = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'l': 4, 'L': 4,
                  'q': 8, 'Q': 8, 'f': 4, 'd': 8}

_tokenname_to_initialiser = {'hex': 'hex', '0x': 'hex', '0X': 'hex', 'oct': 'oct',
                             '0o': 'oct', '0O': 'oct', 'bin': 'bin', '0b': 'bin',
                             '0B': 'bin', 'bits': 'auto', 'bytes': 'bytes', 'pad': 'pad'}



# This converts a single octal digit to 3 bits.
OCT_TO_BITS = ['{0:03b}'.format(i) for i in xrange(8)]

# A dictionary of number of 1 bits contained in binary representation of any byte
BIT_COUNT = dict(zip(xrange(256), [bin(i).count('1') for i in xrange(256)]))


class Bits(object):
    """A container holding an immutable sequence of bits.

    Methods:

    all() -- Check if all specified bits are set to 1 or 0.
    any() -- Check if any of specified bits are set to 1 or 0.
    count() -- Count the number of bits set to 1 or 0.
    join() -- Join bitstrings together using current bitstring.
    split() -- Create generator of chunks split by a delimiter.
    tobytes() -- Return bitstring as bytes, padding if needed.

    Special methods:

    Also available are the operators [], ==, !=, +, *, ~, <<, >>, &, |, ^.

    Properties:

    bin -- The bitstring as a binary string.
    bool -- For single bit bitstrings, interpret as True or False.
    bytes -- The bitstring as a bytes object.
    float -- Interpret as a floating point number.
    floatbe -- Interpret as a big-endian floating point number.
    floatle -- Interpret as a little-endian floating point number.
    floatne -- Interpret as a native-endian floating point number.
    hex -- The bitstring as a hexadecimal string.
    int -- Interpret as a two's complement signed integer.
    intbe -- Interpret as a big-endian signed integer.
    intle -- Interpret as a little-endian signed integer.
    intne -- Interpret as a native-endian signed integer.
    len -- Length of the bitstring in bits.
    oct -- The bitstring as an octal string.
    se -- Interpret as a signed exponential-Golomb code.
    ue -- Interpret as an unsigned exponential-Golomb code.
    sie -- Interpret as a signed interleaved exponential-Golomb code.
    uie -- Interpret as an unsigned interleaved exponential-Golomb code.
    uint -- Interpret as a two's complement unsigned integer.
    uintbe -- Interpret as a big-endian unsigned integer.
    uintle -- Interpret as a little-endian unsigned integer.
    uintne -- Interpret as a native-endian unsigned integer.

    """

    __slots__ = ('_datastore')

    def __init__(self, length=None, offset=None, **kwargs):
        """Or initialise via **kwargs with one (and only one) of:

        bytes -- raw data as a string, for example read from a binary file.
        bin -- binary string representation, e.g. '0b001010'.
        hex -- hexadecimal string representation, e.g. '0x2ef'
        oct -- octal string representation, e.g. '0o777'.
        uint -- an unsigned integer.
        int -- a signed integer.
        float -- a floating point number.
        uintbe -- an unsigned big-endian whole byte integer.
        intbe -- a signed big-endian whole byte integer.
        floatbe - a big-endian floating point number.
        uintle -- an unsigned little-endian whole byte integer.
        intle -- a signed little-endian whole byte integer.
        floatle -- a little-endian floating point number.
        uintne -- an unsigned native-endian whole byte integer.
        intne -- a signed native-endian whole byte integer.
        floatne -- a native-endian floating point number.
        se -- a signed exponential-Golomb code.
        ue -- an unsigned exponential-Golomb code.
        sie -- a signed interleaved exponential-Golomb code.
        uie -- an unsigned interleaved exponential-Golomb code.
        bool -- a boolean (True or False).

        Other keyword arguments:
        length -- length of the bitstring in bits, if needed and appropriate.
                  It must be supplied for all integer and float initialisers.
        offset -- bit offset to the data. These offset bits are
                  ignored and this is mainly intended for use when
                  initialising using 'bytes' or 'filename'.

        The 'auto' initialiser has been removed!

        """

        self._initialise(length, offset, **kwargs)


    def _initialise(self, length, offset, **kwargs):
        if length is not None and length < 0:
            raise CreationError("bitstring length cannot be negative.")
        if offset is not None and offset < 0:
            raise CreationError("offset must be >= 0.")
        if not kwargs:
            # No initialisers, so initialise with nothing or zero bits
            if length is not None and length != 0:
                data = bytearray((length + 7) // 8)
                self._setbytes_unsafe(data, length, 0)
                return
            self._setbytes_unsafe(bytearray(0), 0, 0)
            return
        k, v = kwargs.popitem()
        try:
            init_without_length_or_offset[k](self, v)
            if length is not None or offset is not None:
                raise CreationError("Cannot use length or offset with this initialiser.")
        except KeyError:
            try:
                init_with_length_only[k](self, v, length)
                if offset is not None:
                    raise CreationError("Cannot use offset with this initialiser.")
            except KeyError:
                if offset is None:
                    offset = 0
                try:
                    init_with_length_and_offset[k](self, v, length, offset)
                except KeyError:
                    raise CreationError("Unrecognised keyword '{0}' used to initialise.", k)

    def __copy__(self):
        """Return a new copy of the Bits for the copy module."""
        # Note that if you want a new copy (different ID), use _copy instead.
        # The copy can return self as it's immutable.
        return self

    def __lt__(self, other):
        raise TypeError("unorderable type: {0}".format(type(self).__name__))

    def __gt__(self, other):
        raise TypeError("unorderable type: {0}".format(type(self).__name__))

    def __le__(self, other):
        raise TypeError("unorderable type: {0}".format(type(self).__name__))

    def __ge__(self, other):
        raise TypeError("unorderable type: {0}".format(type(self).__name__))

    def __add__(self, bs):
        """Concatenate bitstrings and return new bitstring.

        bs -- the bitstring to append.

        """
        assert isinstance(bs, Bits)

        if bs.len <= self.len:
            s = self._copy()
            s._append(bs)
        else:
            s = bs._copy()
            #s = self.__class__(s)
            s._prepend(self)
        return s

    def __radd__(self, bs):
        """Append current bitstring to bs and return new bitstring.

        bs -- the string for the 'auto' initialiser that will be appended to.

        """
        bs = self._converttobitstring(bs)
        return bs.__add__(self)

    def __getitem__(self, key):
        """Return a new bitstring representing a slice of the current bitstring.

        Indices are in units of the step parameter (default 1 bit).
        Stepping is used to specify the number of bits in each item.

        >>> print BitArray('0b00110')[1:4]
        '0b011'
        >>> print BitArray('0x00112233')[1:3:8]
        '0x1122'

        """
        length = self.len
        try:
            step = key.step if key.step is not None else 1
        except AttributeError:
            # single element
            if key < 0:
                key += length
            if not 0 <= key < length:
                raise IndexError("Slice index out of range.")
            # Single bit, return True or False
            return self._datastore.getbit(key)
        else:
            if step != 1:
                # convert to binary string and use string slicing
                bs = self.__class__()
                bs._setbin_unsafe(self._getbin().__getitem__(key))
                return bs
            start, stop = 0, length
            if key.start is not None:
                start = key.start
                if key.start < 0:
                    start += stop
            if key.stop is not None:
                stop = key.stop
                if key.stop < 0:
                    stop += length
            start = max(start, 0)
            stop = min(stop, length)
            if start < stop:
                return self._slice(start, stop)
            else:
                return self.__class__()

    def __len__(self):
        """Return the length of the bitstring in bits."""
        return self._getlength()

    def __str__(self):
        """Return approximate string representation of bitstring for printing.

        Short strings will be given wholly in hexadecimal or binary. Longer
        strings may be part hexadecimal and part binary. Very long strings will
        be truncated with '...'.

        """
        length = self.len
        if not length:
            return ''
        if length > MAX_CHARS * 4:
            # Too long for hex. Truncate...
            return ''.join(('0x', self._readhex(MAX_CHARS * 4, 0), '...'))
        # If it's quite short and we can't do hex then use bin
        if length < 32 and length % 4 != 0:
            return '0b' + self.bin
        # If we can use hex then do so
        if not length % 4:
            return '0x' + self.hex
        # Otherwise first we do as much as we can in hex
        # then add on 1, 2 or 3 bits on at the end
        bits_at_end = length % 4
        return ''.join(('0x', self._readhex(length - bits_at_end, 0),
                        ', ', '0b',
                        self._readbin(bits_at_end, length - bits_at_end)))

    def __repr__(self):
        """Return representation that could be used to recreate the bitstring.

        If the returned string is too long it will be truncated. See __str__().

        """
        length = self.len
        #if isinstance(self._datastore._rawarray, MmapByteArray):
        s = self.__str__()
        lengthstring = ''
        if s.endswith('...'):
            lengthstring = " # length={0}".format(length)
        return "{0}('{1}'){2}".format(self.__class__.__name__, s, lengthstring)

    def __eq__(self, bs):
        """Return True if two bitstrings have the same binary representation.

        >>> BitArray('0b1110') == '0xe'
        True

        """
        #try:
        #    bs = Bits(bs)
        #except TypeError:
        #    return False
        return equal(self._datastore, bs._datastore)

    def __ne__(self, bs):
        """Return False if two bitstrings have the same binary representation.

        >>> BitArray('0b111') == '0x7'
        False

        """
        return not self.__eq__(bs)

    def __hash__(self):
        """Return an integer hash of the object."""
        # We can't in general hash the whole bitstring (it could take hours!)
        # So instead take some bits from the start and end.
        if self.len <= 160:
            # Use the whole bitstring.
            shorter = self
        else:
            # Take 10 bytes from start and end
            shorter = self[:80] + self[-80:]
        h = 0
        for byte in shorter.tobytes():
            try:
                h = (h << 4) + ord(byte)
            except TypeError:
                # Python 3
                h = (h << 4) + byte
            g = h & 0xf0000000
            if g & (1 << 31):
                h ^= (g >> 24)
                h ^= g
        return h % 1442968193

    # This is only used in Python 2.x...
    def __nonzero__(self):
        """Return True if any bits are set to 1, otherwise return False."""
        return self.any(True)

    # ...whereas this is used in Python 3.x
    __bool__ = __nonzero__

    def _assertsanity(self):
        """Check internal self consistency as a debugging aid."""
        assert self.len >= 0
        assert 0 <= self._offset, "offset={0}".format(self._offset)
        assert (self.len + self._offset + 7) // 8 == self._datastore.bytelength + self._datastore.byteoffset
        return True


    def _clear(self):
        """Reset the bitstring to an empty state."""
        self._datastore = ByteStore(bytearray(0))


    def _setbytes_safe(self, data, length=None, offset=0):
        """Set the data from a string."""
        data = bytearray(data)
        if length is None:
            # Use to the end of the data
            length = len(data)*8 - offset
            self._datastore = ByteStore(data, length, offset)
        else:
            if length + offset > len(data) * 8:
                msg = "Not enough data present. Need {0} bits, have {1}."
                raise CreationError(msg, length + offset, len(data) * 8)
            if length == 0:
                self._datastore = ByteStore(bytearray(0))
            else:
                self._datastore = ByteStore(data, length, offset)

    def _setbytes_unsafe(self, data, length, offset):
        """Unchecked version of _setbytes_safe."""
        self._datastore = ByteStore(data[:], length, offset)
        assert self._assertsanity()

    def _readbytes(self, length, start):
        """Read bytes and return them. Note that length is in bits."""
        assert length % 8 == 0
        assert start + length <= self.len
        if not (start + self._offset) % 8:
            return bytes(self._datastore.getbyteslice((start + self._offset) // 8,
                                                      (start + self._offset + length) // 8))
        return self._slice(start, start + length).tobytes()

    def _getbytes(self):
        """Return the data as an ordinary string."""
        if self.len % 8:
            raise InterpretError("Cannot interpret as bytes unambiguously - "
                                 "not multiple of 8 bits.")
        return self._readbytes(self.len, 0)

    def _setuint(self, uint, length=None):
        """Reset the bitstring to have given unsigned int interpretation."""
        try:
            if length is None:
                # Use the whole length. Deliberately not using .len here.
                length = self._datastore.bitlength
        except AttributeError:
            # bitstring doesn't have a _datastore as it hasn't been created!
            pass
        # TODO: All this checking code should be hoisted out of here!
        if length is None or length == 0:
            raise CreationError("A non-zero length must be specified with a "
                                "uint initialiser.")
        if uint >= (1 << length):
            msg = "{0} is too large an unsigned integer for a bitstring of length {1}. "\
                  "The allowed range is [0, {2}]."
            raise CreationError(msg, uint, length, (1 << length) - 1)
        if uint < 0:
            raise CreationError("uint cannot be initialsed by a negative number.")
        s = hex(uint)[2:]
        s = s.rstrip('L')
        if len(s) & 1:
            s = '0' + s
        try:
            data = bytes([int(x) for x in ubinascii.unhexlify(s)])
        except AttributeError:
            # the Python 2.x way
            data = ubinascii.unhexlify(s)
        # Now add bytes as needed to get the right length.
        extrabytes = ((length + 7) // 8) - len(data)
        if extrabytes > 0:
            data = b'\x00' * extrabytes + data
        offset = 8 - (length % 8)
        if offset == 8:
            offset = 0
        self._setbytes_unsafe(bytearray(data), length, offset)

    def _readuint(self, length, start):
        """Read bits and interpret as an unsigned int."""
        if not length:
            raise InterpretError("Cannot interpret a zero length bitstring "
                                           "as an integer.")
        offset = self._offset
        startbyte = (start + offset) // 8
        endbyte = (start + offset + length - 1) // 8

        b = ubinascii.hexlify(bytes(self._datastore.getbyteslice(startbyte, endbyte + 1)))
        assert b
        i = int(b, 16)
        final_bits = 8 - ((start + offset + length) % 8)
        if final_bits != 8:
            i >>= final_bits
        i &= (1 << length) - 1
        return i

    def _getuint(self):
        """Return data as an unsigned int."""
        return self._readuint(self.len, 0)

    def _setint(self, int_, length=None):
        """Reset the bitstring to have given signed int interpretation."""
        # If no length given, and we've previously been given a length, use it.
        if length is None and hasattr(self, 'len') and self.len != 0:
            length = self.len
        if length is None or length == 0:
            raise CreationError("A non-zero length must be specified with an int initialiser.")
        if int_ >= (1 << (length - 1)) or int_ < -(1 << (length - 1)):
            raise CreationError("{0} is too large a signed integer for a bitstring of length {1}. "
                                "The allowed range is [{2}, {3}].", int_, length, -(1 << (length - 1)),
                                (1 << (length - 1)) - 1)
        if int_ >= 0:
            self._setuint(int_, length)
            return
        # TODO: We should decide whether to just use the _setuint, or to do the bit flipping,
        # based upon which will be quicker. If the -ive number is less than half the maximum
        # possible then it's probably quicker to do the bit flipping...

        # Do the 2's complement thing. Add one, set to minus number, then flip bits.
        int_ += 1
        self._setuint(-int_, length)
        self._invert_all()

    def _readint(self, length, start):
        """Read bits and interpret as a signed int"""
        ui = self._readuint(length, start)
        if not ui >> (length - 1):
            # Top bit not set, number is positive
            return ui
        # Top bit is set, so number is negative
        tmp = (~(ui - 1)) & ((1 << length) - 1)
        return -tmp

    def _getint(self):
        """Return data as a two's complement signed int."""
        return self._readint(self.len, 0)

    def _setuintbe(self, uintbe, length=None):
        """Set the bitstring to a big-endian unsigned int interpretation."""
        if length is not None and length % 8 != 0:
            raise CreationError("Big-endian integers must be whole-byte. "
                                "Length = {0} bits.", length)
        self._setuint(uintbe, length)

    def _readuintbe(self, length, start):
        """Read bits and interpret as a big-endian unsigned int."""
        if length % 8:
            raise InterpretError("Big-endian integers must be whole-byte. "
                                 "Length = {0} bits.", length)
        return self._readuint(length, start)

    def _getuintbe(self):
        """Return data as a big-endian two's complement unsigned int."""
        return self._readuintbe(self.len, 0)

    def _setintbe(self, intbe, length=None):
        """Set bitstring to a big-endian signed int interpretation."""
        if length is not None and length % 8 != 0:
            raise CreationError("Big-endian integers must be whole-byte. "
                                "Length = {0} bits.", length)
        self._setint(intbe, length)

    def _readintbe(self, length, start):
        """Read bits and interpret as a big-endian signed int."""
        if length % 8:
            raise InterpretError("Big-endian integers must be whole-byte. "
                                 "Length = {0} bits.", length)
        return self._readint(length, start)

    def _getintbe(self):
        """Return data as a big-endian two's complement signed int."""
        return self._readintbe(self.len, 0)

    def _setuintle(self, uintle, length=None):
        if length is not None and length % 8 != 0:
            raise CreationError("Little-endian integers must be whole-byte. "
                                "Length = {0} bits.", length)
        self._setuint(uintle, length)
        self._reversebytes(0, self.len)

    def _readuintle(self, length, start):
        """Read bits and interpret as a little-endian unsigned int."""
        if length % 8:
            raise InterpretError("Little-endian integers must be whole-byte. "
                                 "Length = {0} bits.", length)
        assert start + length <= self.len
        absolute_pos = start + self._offset
        startbyte, offset = divmod(absolute_pos, 8)
        val = 0
        if not offset:
            endbyte = (absolute_pos + length - 1) // 8
            chunksize = 4 # for 'L' format
            while endbyte - chunksize + 1 >= startbyte:
                val <<= 8 * chunksize
                val += ustruct.unpack('<L', bytes(self._datastore.getbyteslice(endbyte + 1 - chunksize, endbyte + 1)))[0]
                endbyte -= chunksize
            for b in xrange(endbyte, startbyte - 1, -1):
                val <<= 8
                val += self._datastore.getbyte(b)
        else:
            data = self._slice(start, start + length)
            assert data.len % 8 == 0
            data._reversebytes(0, self.len)
            for b in bytearray(data.bytes):
                val <<= 8
                val += b
        return val

    def _getuintle(self):
        return self._readuintle(self.len, 0)

    def _setintle(self, intle, length=None):
        if length is not None and length % 8 != 0:
            raise CreationError("Little-endian integers must be whole-byte. "
                                "Length = {0} bits.", length)
        self._setint(intle, length)
        self._reversebytes(0, self.len)

    def _readintle(self, length, start):
        """Read bits and interpret as a little-endian signed int."""
        ui = self._readuintle(length, start)
        if not ui >> (length - 1):
            # Top bit not set, number is positive
            return ui
        # Top bit is set, so number is negative
        tmp = (~(ui - 1)) & ((1 << length) - 1)
        return -tmp

    def _getintle(self):
        return self._readintle(self.len, 0)

    def _setfloat(self, f, length=None):
        # If no length given, and we've previously been given a length, use it.
        if length is None and hasattr(self, 'len') and self.len != 0:
            length = self.len
        if length is None or length == 0:
            raise CreationError("A non-zero length must be specified with a "
                                "float initialiser.")
        if length == 32:
            b = ustruct.pack('>f', f)
        elif length == 64:
            b = ustruct.pack('>d', f)
        else:
            raise CreationError("floats can only be 32 or 64 bits long, "
                                "not {0} bits", length)
        self._setbytes_unsafe(bytearray(b), length, 0)

    def _readfloat(self, length, start):
        """Read bits and interpret as a float."""
        if not (start + self._offset) % 8:
            startbyte = (start + self._offset) // 8
            if length == 32:
                f, = ustruct.unpack('>f', bytes(self._datastore.getbyteslice(startbyte, startbyte + 4)))
            elif length == 64:
                f, = ustruct.unpack('>d', bytes(self._datastore.getbyteslice(startbyte, startbyte + 8)))
        else:
            if length == 32:
                f, = ustruct.unpack('>f', self._readbytes(32, start))
            elif length == 64:
                f, = ustruct.unpack('>d', self._readbytes(64, start))
        try:
            return f
        except NameError:
            raise InterpretError("floats can only be 32 or 64 bits long, not {0} bits", length)

    def _getfloat(self):
        """Interpret the whole bitstring as a float."""
        return self._readfloat(self.len, 0)

    def _setfloatle(self, f, length=None):
        # If no length given, and we've previously been given a length, use it.
        if length is None and hasattr(self, 'len') and self.len != 0:
            length = self.len
        if length is None or length == 0:
            raise CreationError("A non-zero length must be specified with a "
                                "float initialiser.")
        if length == 32:
            b = ustruct.pack('<f', f)
        elif length == 64:
            b = ustruct.pack('<d', f)
        else:
            raise CreationError("floats can only be 32 or 64 bits long, "
                                "not {0} bits", length)
        self._setbytes_unsafe(bytearray(b), length, 0)

    def _readfloatle(self, length, start):
        """Read bits and interpret as a little-endian float."""
        startbyte, offset = divmod(start + self._offset, 8)
        if not offset:
            if length == 32:
                f, = ustruct.unpack('<f', bytes(self._datastore.getbyteslice(startbyte, startbyte + 4)))
            elif length == 64:
                f, = ustruct.unpack('<d', bytes(self._datastore.getbyteslice(startbyte, startbyte + 8)))
        else:
            if length == 32:
                f, = ustruct.unpack('<f', self._readbytes(32, start))
            elif length == 64:
                f, = ustruct.unpack('<d', self._readbytes(64, start))
        try:
            return f
        except NameError:
            raise InterpretError("floats can only be 32 or 64 bits long, "
                                 "not {0} bits", length)

    def _getfloatle(self):
        """Interpret the whole bitstring as a little-endian float."""
        return self._readfloatle(self.len, 0)

    def _setue(self, i):
        """Initialise bitstring with unsigned exponential-Golomb code for integer i.

        Raises CreationError if i < 0.

        """
        if i < 0:
            raise CreationError("Cannot use negative initialiser for unsigned "
                                "exponential-Golomb.")
        if not i:
            self._setbin_unsafe('1')
            return
        tmp = i + 1
        leadingzeros = -1
        while tmp > 0:
            tmp >>= 1
            leadingzeros += 1
        remainingpart = i + 1 - (1 << leadingzeros)
        binstring = '0' * leadingzeros + '1' + Bits(uint=remainingpart,
                                                             length=leadingzeros).bin
        self._setbin_unsafe(binstring)

    def _readue(self, pos):
        """Return interpretation of next bits as unsigned exponential-Golomb code.

        Raises ReadError if the end of the bitstring is encountered while
        reading the code.

        """
        oldpos = pos
        try:
            while not self[pos]:
                pos += 1
        except IndexError:
            raise ReadError("Read off end of bitstring trying to read code.")
        leadingzeros = pos - oldpos
        codenum = (1 << leadingzeros) - 1
        if leadingzeros > 0:
            if pos + leadingzeros + 1 > self.len:
                raise ReadError("Read off end of bitstring trying to read code.")
            codenum += self._readuint(leadingzeros, pos + 1)
            pos += leadingzeros + 1
        else:
            assert codenum == 0
            pos += 1
        return codenum, pos

    def _getue(self):
        """Return data as unsigned exponential-Golomb code.

        Raises InterpretError if bitstring is not a single exponential-Golomb code.

        """
        try:
            value, newpos = self._readue(0)
            if value is None or newpos != self.len:
                raise ReadError
        except ReadError:
            raise InterpretError("Bitstring is not a single exponential-Golomb code.")
        return value

    def _setse(self, i):
        """Initialise bitstring with signed exponential-Golomb code for integer i."""
        if i > 0:
            u = (i * 2) - 1
        else:
            u = -2 * i
        self._setue(u)

    def _getse(self):
        """Return data as signed exponential-Golomb code.

        Raises InterpretError if bitstring is not a single exponential-Golomb code.

        """
        try:
            value, newpos = self._readse(0)
            if value is None or newpos != self.len:
                raise ReadError
        except ReadError:
            raise InterpretError("Bitstring is not a single exponential-Golomb code.")
        return value

    def _readse(self, pos):
        """Return interpretation of next bits as a signed exponential-Golomb code.

        Advances position to after the read code.

        Raises ReadError if the end of the bitstring is encountered while
        reading the code.

        """
        codenum, pos = self._readue(pos)
        m = (codenum + 1) // 2
        if not codenum % 2:
            return -m, pos
        else:
            return m, pos

    def _setuie(self, i):
        """Initialise bitstring with unsigned interleaved exponential-Golomb code for integer i.

        Raises CreationError if i < 0.

        """
        if i < 0:
            raise CreationError("Cannot use negative initialiser for unsigned "
                                "interleaved exponential-Golomb.")
        self._setbin_unsafe('1' if i == 0 else '0' + '0'.join(bin(i + 1)[3:]) + '1')

    def _readuie(self, pos):
        """Return interpretation of next bits as unsigned interleaved exponential-Golomb code.

        Raises ReadError if the end of the bitstring is encountered while
        reading the code.

        """
        try:
            codenum = 1
            while not self[pos]:
                pos += 1
                codenum <<= 1
                codenum += self[pos]
                pos += 1
            pos += 1
        except IndexError:
            raise ReadError("Read off end of bitstring trying to read code.")
        codenum -= 1
        return codenum, pos

    def _getuie(self):
        """Return data as unsigned interleaved exponential-Golomb code.

        Raises InterpretError if bitstring is not a single exponential-Golomb code.

        """
        try:
            value, newpos = self._readuie(0)
            if value is None or newpos != self.len:
                raise ReadError
        except ReadError:
            raise InterpretError("Bitstring is not a single interleaved exponential-Golomb code.")
        return value

    def _setsie(self, i):
        """Initialise bitstring with signed interleaved exponential-Golomb code for integer i."""
        if not i:
            self._setbin_unsafe('1')
        else:
            self._setuie(abs(i))
            self._append(Bits([i < 0]))

    def _getsie(self):
        """Return data as signed interleaved exponential-Golomb code.

        Raises InterpretError if bitstring is not a single exponential-Golomb code.

        """
        try:
            value, newpos = self._readsie(0)
            if value is None or newpos != self.len:
                raise ReadError
        except ReadError:
            raise InterpretError("Bitstring is not a single interleaved exponential-Golomb code.")
        return value

    def _readsie(self, pos):
        """Return interpretation of next bits as a signed interleaved exponential-Golomb code.

        Advances position to after the read code.

        Raises ReadError if the end of the bitstring is encountered while
        reading the code.

        """
        codenum, pos = self._readuie(pos)
        if not codenum:
            return 0, pos
        try:
            if self[pos]:
                return -codenum, pos + 1
            else:
                return codenum, pos + 1
        except IndexError:
            raise ReadError("Read off end of bitstring trying to read code.")

    def _setbool(self, value):
        # We deliberately don't want to have implicit conversions to bool here.
        # If we did then it would be difficult to deal with the 'False' string.
        if value in (1, 'True'):
            self._setbytes_unsafe(bytearray(b'\x80'), 1, 0)
        elif value in (0, 'False'):
            self._setbytes_unsafe(bytearray(b'\x00'), 1, 0)
        else:
            raise CreationError('Cannot initialise boolean with {0}.', value)

    def _getbool(self):
        if self.length != 1:
            msg = "For a bool interpretation a bitstring must be 1 bit long, not {0} bits."
            raise InterpretError(msg, self.length)
        return self[0]

    def _readbool(self, pos):
        return self[pos], pos + 1

    def _setbin_safe(self, binstring):
        """Reset the bitstring to the value given in binstring."""
        binstring = tidy_input_string(binstring)
        # remove any 0b if present
        binstring = binstring.replace('0b', '')
        self._setbin_unsafe(binstring)

    def _setbin_unsafe(self, binstring):
        """Same as _setbin_safe, but input isn't sanity checked. binstring mustn't start with '0b'."""
        length = len(binstring)
        # pad with zeros up to byte boundary if needed
        boundary = ((length + 7) // 8) * 8
        padded_binstring = binstring + '0' * (boundary - length)\
                           if len(binstring) < boundary else binstring
        try:
            bytelist = [int(padded_binstring[x:x + 8], 2)
                        for x in xrange(0, len(padded_binstring), 8)]
        except ValueError:
            raise CreationError("Invalid character in bin initialiser {0}.", binstring)
        self._setbytes_unsafe(bytearray(bytelist), length, 0)

    def _readbin(self, length, start):
        """Read bits and interpret as a binary string."""
        if not length:
            return ''
        # Get the byte slice containing our bit slice
        startbyte, startoffset = divmod(start + self._offset, 8)
        endbyte = (start + self._offset + length - 1) // 8
        b = self._datastore.getbyteslice(startbyte, endbyte + 1)
        # Convert to a string of '0' and '1's (via a hex string an and int!)
        try:
            c = "{:0{}b}".format(int(ubinascii.hexlify(b), 16), 8*len(b))
        except TypeError:
            # Hack to get Python 2.6 working
            c = "{0:0{1}b}".format(int(ubinascii.hexlify(str(b)), 16), 8*len(b))
        # Finally chop off any extra bits.
        return c[startoffset:startoffset + length]

    def _getbin(self):
        """Return interpretation as a binary string."""
        return self._readbin(self.len, 0)

    def _setoct(self, octstring):
        """Reset the bitstring to have the value given in octstring."""
        octstring = tidy_input_string(octstring)
        # remove any 0o if present
        octstring = octstring.replace('0o', '')
        binlist = []
        for i in octstring:
            try:
                if not 0 <= int(i) < 8:
                    raise ValueError
                binlist.append(OCT_TO_BITS[int(i)])
            except ValueError:
                raise CreationError("Invalid symbol '{0}' in oct initialiser.", i)
        self._setbin_unsafe(''.join(binlist))

    def _readoct(self, length, start):
        """Read bits and interpret as an octal string."""
        if length % 3:
            raise InterpretError("Cannot convert to octal unambiguously - "
                                 "not multiple of 3 bits.")
        if not length:
            return ''
        # Get main octal bit by converting from int.
        # Strip starting 0 or 0o depending on Python version.
        end = oct(self._readuint(length, start))[LEADING_OCT_CHARS:]
        if end.endswith('L'):
            end = end[:-1]
        middle = '0' * (length // 3 - len(end))
        return middle + end

    def _getoct(self):
        """Return interpretation as an octal string."""
        return self._readoct(self.len, 0)

    def _sethex(self, hexstring):
        """Reset the bitstring to have the value given in hexstring."""
        hexstring = tidy_input_string(hexstring)
        # remove any 0x if present
        hexstring = hexstring.replace('0x', '')
        length = len(hexstring)
        if length % 2:
            hexstring += '0'
        try:
            try:
#                data = bytearray.fromhex(hexstring)
                data = bytearray([int(x) for x in ubinascii.unhexlify(hexstring)])
            except TypeError:
                raise NotImplementedError('Python 2.x is not supported')
                # Python 2.6 needs a unicode string (a bug). 2.7 and 3.x work fine.
                data = bytearray.fromhex(unicode(hexstring))
        except ValueError:
            raise CreationError("Invalid symbol in hex initialiser.")
        self._setbytes_unsafe(data, length * 4, 0)

    def _readhex(self, length, start):
        """Read bits and interpret as a hex string."""
        if length % 4:
            raise InterpretError("Cannot convert to hex unambiguously - "
                                           "not multiple of 4 bits.")
        if not length:
            return ''
        s = self._slice(start, start + length).tobytes()
        try:
            s = s.hex() # Available in Python 3.5
        except AttributeError:
            # This monstrosity is the only thing I could get to work for both 2.6 and 3.1.
            # TODO: Is utf-8 really what we mean here?
            s = str(ubinascii.hexlify(s).decode('utf-8'))
        # If there's one nibble too many then cut it off
        return s[:-1] if (length // 4) % 2 else s

    def _gethex(self):
        """Return the hexadecimal representation as a string prefixed with '0x'.

        Raises an InterpretError if the bitstring's length is not a multiple of 4.

        """
        return self._readhex(self.len, 0)

    def _getoffset(self):
        return self._datastore.offset

    def _getlength(self):
        """Return the length of the bitstring in bits."""
        return self._datastore.bitlength

    def _ensureinmemory(self):
        """Ensure the data is held in memory, not in a file."""
        self._setbytes_unsafe(self._datastore.getbyteslice(0, self._datastore.bytelength),
                              self.len, self._offset)

    @classmethod
    def _converttobitstring(cls, bs, offset=0):
        """Convert bs to a bitstring and return it.

        offset gives the suggested bit offset of first significant
        bit, to optimise append etc.

        """
        if isinstance(bs, Bits):
            return bs

        if isinstance(bs, basestring):
            b = cls()
            try:
                _, tokens = tokenparser(bs)
            except ValueError as e:
                raise CreationError(*e.args)
            if tokens:
                b._append(Bits._init_with_token(*tokens[0]))
                b._datastore = offsetcopy(b._datastore, offset)
                for token in tokens[1:]:
                    b._append(Bits._init_with_token(*token))
            assert b._assertsanity()
            assert b.len == 0 or b._offset == offset
            return b

        return cls(bs)

    def _copy(self):
        """Create and return a new copy of the Bits (always in memory)."""
        s_copy = self.__class__()
        s_copy._setbytes_unsafe(self._datastore.getbyteslice(0, self._datastore.bytelength),
                                self.len, self._offset)
        return s_copy

    def _slice(self, start, end):
        """Used internally to get a slice, without error checking."""
        if end == start:
            return self.__class__()
        offset = self._offset
        startbyte, newoffset = divmod(start + offset, 8)
        endbyte = (end + offset - 1) // 8
        bs = self.__class__()
        bs._setbytes_unsafe(self._datastore.getbyteslice(startbyte, endbyte + 1), end - start, newoffset)
        return bs


    def _append(self, bs):
        """Append a bitstring to the current bitstring."""
        self._datastore._appendstore(bs._datastore)

    def _prepend(self, bs):
        """Prepend a bitstring to the current bitstring."""
        self._datastore._prependstore(bs._datastore)

    def _reverse(self):
        """Reverse all bits in-place."""
        # Reverse the contents of each byte
        n = [BYTE_REVERSAL_DICT[b] for b in self._datastore.rawbytes]
        # Then reverse the order of the bytes
        n.reverse()
        # The new offset is the number of bits that were unused at the end.
        newoffset = 8 - (self._offset + self.len) % 8
        if newoffset == 8:
            newoffset = 0
        self._setbytes_unsafe(bytearray().join(n), self.length, newoffset)

    def _truncatestart(self, bits):
        """Truncate bits from the start of the bitstring."""
        assert 0 <= bits <= self.len
        if not bits:
            return
        if bits == self.len:
            self._clear()
            return
        bytepos, offset = divmod(self._offset + bits, 8)
        self._setbytes_unsafe(self._datastore.getbyteslice(bytepos, self._datastore.bytelength), self.len - bits,
                              offset)
        assert self._assertsanity()

    def _truncateend(self, bits):
        """Truncate bits from the end of the bitstring."""
        assert 0 <= bits <= self.len
        if not bits:
            return
        if bits == self.len:
            self._clear()
            return
        newlength_in_bytes = (self._offset + self.len - bits + 7) // 8
        self._setbytes_unsafe(self._datastore.getbyteslice(0, newlength_in_bytes), self.len - bits,
                              self._offset)
        assert self._assertsanity()

    def _insert(self, bs, pos):
        """Insert bs at pos."""
        assert 0 <= pos <= self.len
        if pos > self.len // 2:
            # Inserting nearer end, so cut off end.
            end = self._slice(pos, self.len)
            self._truncateend(self.len - pos)
            self._append(bs)
            self._append(end)
        else:
            # Inserting nearer start, so cut off start.
            start = self._slice(0, pos)
            self._truncatestart(pos)
            self._prepend(bs)
            self._prepend(start)
        try:
            self._pos = pos + bs.len
        except AttributeError:
            pass
        assert self._assertsanity()

    def _overwrite(self, bs, pos):
        """Overwrite with bs at pos."""
        assert 0 <= pos < self.len
        if bs is self:
            # Just overwriting with self, so do nothing.
            assert pos == 0
            return
        firstbytepos = (self._offset + pos) // 8
        lastbytepos = (self._offset + pos + bs.len - 1) // 8
        bytepos, bitoffset = divmod(self._offset + pos, 8)
        if firstbytepos == lastbytepos:
            mask = ((1 << bs.len) - 1) << (8 - bs.len - bitoffset)
            self._datastore.setbyte(bytepos, self._datastore.getbyte(bytepos) & (~mask))
            d = offsetcopy(bs._datastore, bitoffset)
            self._datastore.setbyte(bytepos, self._datastore.getbyte(bytepos) | (d.getbyte(0) & mask))
        else:
            # Do first byte
            mask = (1 << (8 - bitoffset)) - 1
            self._datastore.setbyte(bytepos, self._datastore.getbyte(bytepos) & (~mask))
            d = offsetcopy(bs._datastore, bitoffset)
            self._datastore.setbyte(bytepos, self._datastore.getbyte(bytepos) | (d.getbyte(0) & mask))
            # Now do all the full bytes
            self._datastore.setbyteslice(firstbytepos + 1, lastbytepos, d.getbyteslice(1, lastbytepos - firstbytepos))
            # and finally the last byte
            bitsleft = (self._offset + pos + bs.len) % 8
            if not bitsleft:
                bitsleft = 8
            mask = (1 << (8 - bitsleft)) - 1
            self._datastore.setbyte(lastbytepos, self._datastore.getbyte(lastbytepos) & mask)
            self._datastore.setbyte(lastbytepos,
                                    self._datastore.getbyte(lastbytepos) | (d.getbyte(d.bytelength - 1) & ~mask))
        assert self._assertsanity()

    def _delete(self, bits, pos):
        """Delete bits at pos."""
        assert 0 <= pos <= self.len
        assert pos + bits <= self.len
        if not pos:
            # Cutting bits off at the start.
            self._truncatestart(bits)
            return
        if pos + bits == self.len:
            # Cutting bits off at the end.
            self._truncateend(bits)
            return
        if pos > self.len - pos - bits:
            # More bits before cut point than after it, so do bit shifting
            # on the final bits.
            end = self._slice(pos + bits, self.len)
            assert self.len - pos > 0
            self._truncateend(self.len - pos)
            self._append(end)
            return
        # More bits after the cut point than before it.
        start = self._slice(0, pos)
        self._truncatestart(pos + bits)
        self._prepend(start)
        return

    def _reversebytes(self, start, end):
        """Reverse bytes in-place."""
        # Make the start occur on a byte boundary
        # TODO: We could be cleverer here to avoid changing the offset.
        newoffset = 8 - (start % 8)
        if newoffset == 8:
            newoffset = 0
        self._datastore = offsetcopy(self._datastore, newoffset)
        # Now just reverse the byte data
        toreverse = bytearray(self._datastore.getbyteslice((newoffset + start) // 8, (newoffset + end) // 8))
        toreverse.reverse()
        self._datastore.setbyteslice((newoffset + start) // 8, (newoffset + end) // 8, toreverse)

    def _set(self, pos):
        """Set bit at pos to 1."""
        assert 0 <= pos < self.len
        self._datastore.setbit(pos)

    def _unset(self, pos):
        """Set bit at pos to 0."""
        assert 0 <= pos < self.len
        self._datastore.unsetbit(pos)

    def _invert(self, pos):
        """Flip bit at pos 1<->0."""
        assert 0 <= pos < self.len
        self._datastore.invertbit(pos)

    def _invert_all(self):
        """Invert every bit."""
        set = self._datastore.setbyte
        get = self._datastore.getbyte
        for p in xrange(self._datastore.byteoffset, self._datastore.byteoffset + self._datastore.bytelength):
            set(p, 256 + ~get(p))

    def _ilshift(self, n):
        """Shift bits by n to the left in place. Return self."""
        assert 0 < n <= self.len
        self._append(Bits(n))
        self._truncatestart(n)
        return self

    def _irshift(self, n):
        """Shift bits by n to the right in place. Return self."""
        assert 0 < n <= self.len
        self._prepend(Bits(n))
        self._truncateend(n)
        return self

    def _imul(self, n):
        """Concatenate n copies of self in place. Return self."""
        assert n >= 0
        if not n:
            self._clear()
            return self
        m = 1
        old_len = self.len
        while m * 2 < n:
            self._append(self)
            m *= 2
        self._append(self[0:(n - m) * old_len])
        return self

    def _inplace_logical_helper(self, bs, f):
        """Helper function containing most of the __ior__, __iand__, __ixor__ code."""
        # Give the two bitstrings the same offset (modulo 8)
        self_byteoffset, self_bitoffset = divmod(self._offset, 8)
        bs_byteoffset, bs_bitoffset = divmod(bs._offset, 8)
        if bs_bitoffset != self_bitoffset:
            if not self_bitoffset:
                bs._datastore = offsetcopy(bs._datastore, 0)
            else:
                self._datastore = offsetcopy(self._datastore, bs_bitoffset)
        a = self._datastore.rawbytes
        b = bs._datastore.rawbytes
        for i in xrange(len(a)):
            a[i] = f(a[i + self_byteoffset], b[i + bs_byteoffset])
        return self

    def _readbits(self, length, start):
        """Read some bits from the bitstring and return newly constructed bitstring."""
        return self._slice(start, start + length)

    def _validate_slice(self, start, end):
        """Validate start and end and return them as positive bit positions."""
        if start is None:
            start = 0
        elif start < 0:
            start += self.len
        if end is None:
            end = self.len
        elif end < 0:
            end += self.len
        if not 0 <= end <= self.len:
            raise ValueError("end is not a valid position in the bitstring.")
        if not 0 <= start <= self.len:
            raise ValueError("start is not a valid position in the bitstring.")
        if end < start:
            raise ValueError("end must not be less than start.")
        return start, end



    def _findbytes(self, bytes_, start, end, bytealigned):
        """Quicker version of find when everything's whole byte
        and byte aligned.

        """
        assert self._datastore.offset == 0
        assert bytealigned is True
        # Extract data bytes from bitstring to be found.
        bytepos = (start + 7) // 8
        found = False
        p = bytepos
        finalpos = end // 8
        increment = max(1024, len(bytes_) * 10)
        buffersize = increment + len(bytes_)
        while p < finalpos:
            # Read in file or from memory in overlapping chunks and search the chunks.
            buf = bytearray(self._datastore.getbyteslice(p, min(p + buffersize, finalpos)))
            pos = buf.find(bytes_)
            if pos != -1:
                found = True
                p += pos
                break
            p += increment
        if not found:
            return ()
        return (p * 8,)

    def _findregex(self, reg_ex, start, end, bytealigned):
        """Find first occurrence of a compiled regular expression.

        Note that this doesn't support arbitrary regexes, in particular they
        must match a known length.

        """
        p = start
        length = len(reg_ex.pattern)
        # We grab overlapping chunks of the binary representation and
        # do an ordinary string search within that.
        increment = max(4096, length * 10)
        buffersize = increment + length
        while p < end:
            buf = self._readbin(min(buffersize, end - p), p)
            # Test using regular expressions...
            m = reg_ex.search(buf)
            if m:
                pos = m.start()
            # pos = buf.find(targetbin)
            # if pos != -1:
                # if bytealigned then we only accept byte aligned positions.
                if not bytealigned or (p + pos) % 8 == 0:
                    return (p + pos,)
                if bytealigned:
                    # Advance to just beyond the non-byte-aligned match and try again...
                    p += pos + 1
                    continue
            p += increment
            # Not found, return empty tuple
        return ()


    def tobytes(self):
        """Return the bitstring as bytes, padding with zero bits if needed.

        Up to seven zero bits will be added at the end to byte align.

        """
        d = offsetcopy(self._datastore, 0).rawbytes
        # Need to ensure that unused bits at end are set to zero
        unusedbits = 8 - self.len % 8
        if unusedbits != 8:
            d[-1] &= (0xff << unusedbits)
        return bytes(d)


    def all(self, value, pos=None):
        """Return True if one or many bits are all set to value.

        value -- If value is True then checks for bits set to 1, otherwise
                 checks for bits set to 0.
        pos -- An iterable of bit positions. Negative numbers are treated in
               the same way as slice indices. Defaults to the whole bitstring.

        """
        value = bool(value)
        length = self.len
        if pos is None:
            pos = xrange(self.len)
        for p in pos:
            if p < 0:
                p += length
            if not 0 <= p < length:
                raise IndexError("Bit position {0} out of range.".format(p))
            if not self._datastore.getbit(p) is value:
                return False
        return True

    def any(self, value, pos=None):
        """Return True if any of one or many bits are set to value.

        value -- If value is True then checks for bits set to 1, otherwise
                 checks for bits set to 0.
        pos -- An iterable of bit positions. Negative numbers are treated in
               the same way as slice indices. Defaults to the whole bitstring.

        """
        value = bool(value)
        length = self.len
        if pos is None:
            pos = xrange(self.len)
        for p in pos:
            if p < 0:
                p += length
            if not 0 <= p < length:
                raise IndexError("Bit position {0} out of range.".format(p))
            if self._datastore.getbit(p) is value:
                return True
        return False

    def count(self, value):
        """Return count of total number of either zero or one bits.

        value -- If True then bits set to 1 are counted, otherwise bits set
                 to 0 are counted.

        >>> Bits('0xef').count(1)
        7

        """
        if not self.len:
            return 0
        # count the number of 1s (from which it's easy to work out the 0s).
        # Don't count the final byte yet.
        count = sum(BIT_COUNT[self._datastore.getbyte(i)] for i in xrange(self._datastore.bytelength - 1))
        # adjust for bits at start that aren't part of the bitstring
        if self._offset:
            count -= BIT_COUNT[self._datastore.getbyte(0) >> (8 - self._offset)]
        # and count the last 1 - 8 bits at the end.
        endbits = self._datastore.bytelength * 8 - (self._offset + self.len)
        count += BIT_COUNT[self._datastore.getbyte(self._datastore.bytelength - 1) >> endbits]
        return count if value else self.len - count

    # Create native-endian functions as aliases depending on the byteorder
    if byteorder == 'little':
        _setfloatne = _setfloatle
        _readfloatne = _readfloatle
        _getfloatne = _getfloatle
        _setuintne = _setuintle
        _readuintne = _readuintle
        _getuintne = _getuintle
        _setintne = _setintle
        _readintne = _readintle
        _getintne = _getintle
    else:
        _setfloatne = _setfloat
        _readfloatne = _readfloat
        _getfloatne = _getfloat
        _setuintne = _setuintbe
        _readuintne = _readuintbe
        _getuintne = _getuintbe
        _setintne = _setintbe
        _readintne = _readintbe
        _getintne = _getintbe

    _offset = property(_getoffset)

    len = property(_getlength,
                   doc="""The length of the bitstring in bits. Read only.
                      """)
    length = property(_getlength,
                      doc="""The length of the bitstring in bits. Read only.
                      """)
    bool = property(_getbool,
                    doc="""The bitstring as a bool (True or False). Read only.
                    """)
    hex = property(_gethex,
                   doc="""The bitstring as a hexadecimal string. Read only.
                   """)
    bin = property(_getbin,
                   doc="""The bitstring as a binary string. Read only.
                   """)
    oct = property(_getoct,
                   doc="""The bitstring as an octal string. Read only.
                   """)
    bytes = property(_getbytes,
                     doc="""The bitstring as a bytes object. Read only.
                      """)
    int = property(_getint,
                   doc="""The bitstring as a two's complement signed int. Read only.
                      """)
    uint = property(_getuint,
                    doc="""The bitstring as a two's complement unsigned int. Read only.
                      """)
    float = property(_getfloat,
                     doc="""The bitstring as a floating point number. Read only.
                      """)
    intbe = property(_getintbe,
                     doc="""The bitstring as a two's complement big-endian signed int. Read only.
                      """)
    uintbe = property(_getuintbe,
                      doc="""The bitstring as a two's complement big-endian unsigned int. Read only.
                      """)
    floatbe = property(_getfloat,
                       doc="""The bitstring as a big-endian floating point number. Read only.
                      """)
    intle = property(_getintle,
                     doc="""The bitstring as a two's complement little-endian signed int. Read only.
                      """)
    uintle = property(_getuintle,
                      doc="""The bitstring as a two's complement little-endian unsigned int. Read only.
                      """)
    floatle = property(_getfloatle,
                       doc="""The bitstring as a little-endian floating point number. Read only.
                      """)
    intne = property(_getintne,
                     doc="""The bitstring as a two's complement native-endian signed int. Read only.
                      """)
    uintne = property(_getuintne,
                      doc="""The bitstring as a two's complement native-endian unsigned int. Read only.
                      """)
    floatne = property(_getfloatne,
                       doc="""The bitstring as a native-endian floating point number. Read only.
                      """)
    ue = property(_getue,
                  doc="""The bitstring as an unsigned exponential-Golomb code. Read only.
                      """)
    se = property(_getse,
                  doc="""The bitstring as a signed exponential-Golomb code. Read only.
                      """)
    uie = property(_getuie,
                   doc="""The bitstring as an unsigned interleaved exponential-Golomb code. Read only.
                      """)
    sie = property(_getsie,
                   doc="""The bitstring as a signed interleaved exponential-Golomb code. Read only.
                      """)


# Dictionary that maps token names to the function that reads them.
name_to_read = {'uint': Bits._readuint,
                'uintle': Bits._readuintle,
                'uintbe': Bits._readuintbe,
                'uintne': Bits._readuintne,
                'int': Bits._readint,
                'intle': Bits._readintle,
                'intbe': Bits._readintbe,
                'intne': Bits._readintne,
                'float': Bits._readfloat,
                'floatbe': Bits._readfloat, # floatbe is a synonym for float
                'floatle': Bits._readfloatle,
                'floatne': Bits._readfloatne,
                'hex': Bits._readhex,
                'oct': Bits._readoct,
                'bin': Bits._readbin,
                'bits': Bits._readbits,
                'bytes': Bits._readbytes,
                'ue': Bits._readue,
                'se': Bits._readse,
                'uie': Bits._readuie,
                'sie': Bits._readsie,
                'bool': Bits._readbool,
                }

# Dictionaries for mapping init keywords with init functions.
init_with_length_and_offset = {'bytes': Bits._setbytes_safe,
                               }

init_with_length_only = {'uint': Bits._setuint,
                         'int': Bits._setint,
                         'float': Bits._setfloat,
                         'uintbe': Bits._setuintbe,
                         'intbe': Bits._setintbe,
                         'floatbe': Bits._setfloat,
                         'uintle': Bits._setuintle,
                         'intle': Bits._setintle,
                         'floatle': Bits._setfloatle,
                         'uintne': Bits._setuintne,
                         'intne': Bits._setintne,
                         'floatne': Bits._setfloatne,
                         }

init_without_length_or_offset = {'bin': Bits._setbin_safe,
                                 'hex': Bits._sethex,
                                 'oct': Bits._setoct,
                                 'ue': Bits._setue,
                                 'se': Bits._setse,
                                 'uie': Bits._setuie,
                                 'sie': Bits._setsie,
                                 'bool': Bits._setbool,
                                 }

__all__ = ['Bits', 'Error', 'ReadError',
           'InterpretError', 'ByteAlignError', 'CreationError', 'bytealigned']
