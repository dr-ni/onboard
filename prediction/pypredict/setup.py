from distutils.core import setup, Extension

module1 = Extension('lm',
                    sources = ['lm.cpp',
                               'lm_dynamic.cpp',
                               'lm_merged.cpp',
                               'lm_python.cpp',
                               'pool_allocator.cpp'],
                    depends = ['lm.h',
                               'lm_dynamic.h',
                               'lm_dynamic_impl.h',
                               'lm_dynamic_kn.h',
                               'lm_merged.h'],
                    undef_macros = [])

setup (name = 'lm',
       version = '1.0',
       description = 'Dynamic N-gram Language Model',
       ext_modules = [module1])
