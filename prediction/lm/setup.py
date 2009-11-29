from distutils.core import setup, Extension

module1 = Extension('lm',
                    sources = ['lm.cpp','lm_dynamic.cpp', 'lm_python.cpp'],
                    depends = ['lm.h', 'lm_dynamic.h'],
                    undef_macros = [])

setup (name = 'lm',
       version = '1.0',
       description = 'Dynamic N-gram Language Model',
       ext_modules = [module1])
