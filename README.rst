======================================
bitstring module (MicroPython version)
======================================

**micropython-bitstring** is a stripped-down version of the Bitstring package by Scott Griffiths
that works with MicroPython. It defines a single class ``Bits`` for the creation
of binary strings. Binary strings created with this module are compatible
with the original Bitstring module.

Example::

    from ubitstring import Bits
    s = Bits(float=3.1415, length=32) + Bits(uint=15, length=4) + Bits(bool=True)
    assert len(s) == 32 + 4 + 1


The Bits class
-----------------------

The ``Bits`` class is a simplified version of the Bits_ class of the same name
of the original Bitstring package. The focus is on the *creation* of
binary strings, for instance in IoT devices.

.. _Bits: https://pythonhosted.org/bitstring/constbitarray.html

The ``auto`` and ``filename`` keyword arguments have been removed and only the
functionality shown in the example below is supported::

    a = Bits(int=-31111, length=32)
    b = Bits(int=-31111, length=32)

    assert a.len == 32

    assert a.int == -31111
    assert a.hex == 'ffff8679'
    assert a.bin == '11111111111111111000011001111001'
    assert a.bytes == b'\xff\xff\x86y'

    assert a.all(True, [1,2,3,4]) is True
    assert a.all(True, [30]) is False

    assert a.any(True, [0,30]) is True
    assert a.any(True, [29,30]) is False

    assert a.count(1) == 24
    assert a.count(0) == 8

    assert a.tobytes() == b'\xff\xff\x86y'
    assert a[-4:].bin == '1001'

    assert a == b

    c = a + b
    assert c.hex == 'ffff8679ffff8679'


----

The bitstring module has been released as open source under the MIT License.
Copyright (c) 2016 Scott Griffiths

For more information see the project's homepage on GitHub:
<https://github.com/scott-griffiths/bitstring>

The MicroPython version has been created by Markus Juenemann: 
<https://github.com/mjuenema/micropython-bitstring>
