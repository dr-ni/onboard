#!/usr/bin/env python

import os
import glob
import sys
from distutils.core import setup, Extension

try:
    import DistUtilsExtra.auto
except ImportError:
    print >> sys.stderr, 'To build project_name you need https://launchpad.net/python-distutils-extra'
    sys.exit(1)
assert DistUtilsExtra.auto.__version__ >= '2.18', 'needs DistUtilsExtra.auto >= 2.18'


join = os.path.join

path = join('pypredict', 'lm')
sources = ['lm.cpp',
          'lm_dynamic.cpp',
          'lm_merged.cpp',
          'lm_python.cpp',
          'pool_allocator.cpp']
depends = ['lm.h',
          'lm_dynamic.h',
          'lm_dynamic_impl.h',
          'lm_dynamic_kn.h',
          'lm_dynamic_cached.h',
          'lm_merged.h']
sources = [join(path, x) for x in sources]

lm = Extension('_lm',
               #define_macros=[('NDEBUG', '1')], 
               sources,
               depends,             
               undef_macros = [],
               library_dirs = [],
               libraries = [],
              )
              
setup(name='locubus',
      version='0.5',
      description='Word Prediction D-Bus Service',
      author='marmuta',
      author_email='marmvta@gmail.com',
      license = 'gpl',
      url='http://launchpad.net/locubus',
      ext_package='pypredict.lm',
      ext_modules = [lm],
      packages=['pypredict', 'pypredict.lm'],
      data_files = [('share/locubus/models', glob.glob('models/*.lm'))],
      scripts = ['locubus'],
     )

