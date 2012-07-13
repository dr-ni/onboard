#!/usr/bin/python3

from __future__ import print_function

import os
import sys
import glob
import subprocess
from os.path import dirname, abspath, join, split
from distutils.core import Extension, Command
from distutils      import version
from contextlib import contextmanager

# Work around encoding error in python3-distutils-extra
# when building in pbuilder with LANG=C (LP# 1017468).
if sys.version_info.major == 3:
    import locale
    locale.getpreferredencoding = lambda: 'UTF-8'

try:
    # try python 3
    from subprocess import getstatusoutput
except:
    # python 2 fallback
    from commands import getstatusoutput

try:
    import DistUtilsExtra.auto
except ImportError:
    print('To build Onboard you need https://launchpad.net/python-distutils-extra', file=sys.stderr)
    sys.exit(1)

current_ver = version.StrictVersion(DistUtilsExtra.auto.__version__)
required_ver = version.StrictVersion('2.12')
assert current_ver >= required_ver , 'needs DistUtilsExtra.auto >= 2.12'

@contextmanager
def import_path(path):
    """ temporily change python import path """
    old_path = sys.path
    sys.path = [path] + sys.path
    yield
    sys.path = old_path


def pkgconfig(*packages, **kw):
    command = "pkg-config --libs --cflags %s" % ' '.join(packages)
    status, output = getstatusoutput(command)

    # print command and ouput to console to aid in debugging
    if "build" in sys.argv or \
       "build_ext" in sys.argv:
        print("setup.py: running pkg-config:", command)
        print("setup.py:", output)

    if status != 0:
        print('setup.py: pkg-config returned exit code %d' % status, file=sys.stderr)
        sys.exit(1)


    flag_map = {'-I': 'include_dirs', '-L': 'library_dirs', '-l': 'libraries'}
    for token in output.split():
        if token[:2] in flag_map:
            kw.setdefault(flag_map.get(token[:2]), []).append(token[2:])
        else:
            kw.setdefault('extra_link_args', []).append(token)
    for k, v in kw.items():
        kw[k] = list(set(v))
    return kw


# Make xgettext extract translatable strings from _format() calls too.
var = "XGETTEXT_ARGS"
os.environ[var] = os.environ.get(var, "") + " --keyword=_format"


##### private extension 'osk' #####

MODULE_NAME_OSK = 'Onboard.osk'

class Extension_osk(Extension):
    sources = ['osk_module.c',
               'osk_devices.c',
               'osk_util.c',
              ]

    depends = ['osk_module.h',
               'osk_devices.h',
               'osk_util.h',
              ]

    def __init__(self, root = ""):
        path = join(root, 'Onboard', 'osk')
        sources = [join(path, x) for x in self.sources]
        depends = [join(path, x) for x in self.depends]
        Extension.__init__(self,
                           MODULE_NAME_OSK,

                           # even MINOR numbers for stable versions
                           define_macros = [('MAJOR_VERSION', '0'),
                                            ('MINOR_VERSION', '2'),
                                            ('MICRO_VERSION', '0'),
                                            ('USE_LANGUAGE_CLASSIFIER', '1'),
                                           ],

                           sources = sources,
                           depends = depends,

                           **pkgconfig('gdk-3.0', 'x11', 'xi', 'xtst',
                                       'dconf', 'libexttextcat')
                          )

extension_osk = Extension_osk()


##### private extension lm #####

MODULE_NAME_LM = 'Onboard.pypredict.lm'

class Extension_lm(Extension):
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

    def __init__(self, root = "", module_root = ""):
        path = join(root, 'pypredict', 'lm')
        sources = [join(path, x) for x in self.sources]
        depends = [join(path, x) for x in self.depends]

        module_name = "pypredict.lm"
        if module_root:
            module_name = module_root + "." + module_name

        Extension.__init__(self,
                           module_name,
                           sources = sources,
                           depends = depends,
                           undef_macros = [],
                           library_dirs = [],
                           libraries = [],
                           #define_macros=[('NDEBUG', '1')],
                          )

extension_lm = Extension_lm("Onboard", "Onboard")


#### custom test command ####'

class TestCommand(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import nose
        if nose.run(argv=[__file__, "--with-doctest"]):
            sys.exit( 0 )
        else:
            sys.exit( 1 )


##### setup #####

DistUtilsExtra.auto.setup(
    name = 'onboard',
    version = '0.98.0',
    author = 'Chris Jones',
    author_email = 'chris.e.jones@gmail.com',
    maintainer = 'Ubuntu Core Developers',
    maintainer_email = 'ubuntu-devel-discuss@lists.ubuntu.com',
    url = 'http://launchpad.net/onboard/',
    license = 'gpl',
    description = 'Simple On-screen Keyboard',

    packages = ['Onboard', 'Onboard.pypredict'],

    data_files = [('share/glib-2.0/schemas', glob.glob('data/*.gschema.xml')),
                  ('share/GConf/gsettings', glob.glob('data/*.convert')),
                  ('share/onboard', glob.glob('AUTHORS')),
                  ('share/onboard', glob.glob('CHANGELOG')),
                  ('share/onboard', glob.glob('COPYING')),
                  ('share/onboard', glob.glob('NEWS')),
                  ('share/onboard', glob.glob('README')),
                  ('share/onboard', glob.glob('onboard-defaults.conf.example')),
                  ('share/icons/hicolor/scalable/apps', glob.glob('icons/hicolor/*')),
                  ('share/icons/ubuntu-mono-dark/status/22', glob.glob('icons/ubuntu-mono-dark/*')),
                  ('share/icons/ubuntu-mono-light/status/22', glob.glob('icons/ubuntu-mono-light/*')),
                  ('share/onboard/data', glob.glob('data/*.gif')),
                  ('share/onboard/docs', glob.glob('docs/*')),
                  ('share/onboard/layouts', glob.glob('layouts/*.*')),
                  ('share/onboard/layouts/images', glob.glob('layouts/images/*')),
                  ('share/onboard/themes', glob.glob('themes/*')),
                  ('share/onboard/scripts', glob.glob('scripts/*')),
                  ('/etc/xdg/autostart', glob.glob('data/onboard-autostart.desktop')),

                  ('share/onboard/models', glob.glob('models/*.lm')),
                  ('/usr/share/dbus-1/services', glob.glob('data/org.onboard-word-prediction.service')),
                 ],

    scripts = ['onboard', 'onboard-settings', 'onboard-word-predictiond'],

    # don't let distutils-extra import our files
    requires = [MODULE_NAME_OSK, MODULE_NAME_LM],

    ext_modules = [extension_osk, extension_lm],

    cmdclass = {'test': TestCommand},
)

# Link the extensions back to the project directory
# so Onboard can be run from source as usual, without --inplace.
# Remove this at any time if there is a better way.
if "build" in sys.argv or \
   "build_ext" in sys.argv:
    root = dirname(abspath(__file__))
    build_root = join(root, 'build', 'lib*{}.*'.format(sys.version_info.major))
    libs = [['Onboard', 'osk*.so'],
            ['Onboard/pypredict', 'lm*.so']]
    for path, pattern in libs:
        files = glob.glob(join(build_root, path, pattern))
        for file in files:
            dstfile = join(path, split(file)[1])
            print("symlinking {} to {}".format(file, dstfile))

            try: os.unlink(dstfile)
            except OSError: pass
            os.symlink(file, dstfile)

