from ubitstring import __version__

import sys
# Remove current dir from sys.path, otherwise setuptools will peek up our
# module instead of system's.
sys.path.pop(0)
from setuptools import setup
sys.path.append("..")

kwds = {'long_description': open('README.rst').read()}

if sys.version_info[0] < 2:
    raise Exception('This version of bitstring needs Python 3 or later.')

setup(name='micropython-bitstring',
      version=__version__,
      description="Very stripped down version of Scrott Griffith's Bitstring package.",
      author='Markus Juenemann',
      author_email='markus@juenemann.net',
      url='https://github.com/mjuenema/micropython-bitstring',
      download_url='https://pypi.python.org/pypi/micropython-bitstring/',
      license='The MIT License: http://www.opensource.org/licenses/mit-license.php',
      py_modules=['ubitstring'],
      platforms='all',
      classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: MicroPython',
        'Topic :: Software Development :: Libraries :: Python Modules'
      ],
      install_requires=['micropython-copy','micropython-re-pcre','micropython-binascii','micropython-os','micropython-struct','micropython-types'],
      **kwds
      )
