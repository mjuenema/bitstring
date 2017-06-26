======================================
bitstring module (MicroPython version)
======================================

**micropython-bitstring** is a stripped-down version of the Bitstring package by Scott Griffiths
that works with MicroPython. It defines a single class Bits for the creation
of binary strings. Binary strings created with this module are compatible
with the original Bitstring module.

Example::

     from bitstring import Bits
     s = Bits(float=3.1415, length=32) + Bits(uint=15, length=4) + Bits(bool=True)
     assert len(s) == 32 + 4 + 1

Check ``docs/index.rst`` for details.

----

The bitstring module has been released as open source under the MIT License.
Copyright (c) 2016 Scott Griffiths

For more information see the project's homepage on GitHub:
<https://github.com/scott-griffiths/bitstring>

The MicroPython version has been patched together by Markus Juenemann: 
<https://github.com/mjuenema/micropython-bitstring>
