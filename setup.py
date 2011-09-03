#!/usr/bin/python

import glob
import commands

from distutils.core import Extension
from distutils      import version

try:
    import DistUtilsExtra.auto
except ImportError:
    import sys
    print >> sys.stderr, 'To build Onboard you need https://launchpad.net/python-distutils-extra'
    sys.exit(1)

current_ver = version.StrictVersion(DistUtilsExtra.auto.__version__)
required_ver = version.StrictVersion('2.12')
assert current_ver >= required_ver , 'needs DistUtilsExtra.auto >= 2.12'

def pkgconfig(*packages, **kw):
    flag_map = {'-I': 'include_dirs', '-L': 'library_dirs', '-l': 'libraries'}
    for token in commands.getoutput("pkg-config --libs --cflags %s" % ' '.join(packages)).split():
        if flag_map.has_key(token[:2]):
            kw.setdefault(flag_map.get(token[:2]), []).append(token[2:])
        else:
            kw.setdefault('extra_link_args', []).append(token)
    for k, v in kw.iteritems():
        kw[k] = list(set(v))
    return kw


##### private extension 'osk' #####

OSK_EXTENSION = 'Onboard.osk'

SOURCES = ['osk_module.c', 
           'osk_devices.c', 
           'osk_util.c',
          ]
SOURCES = ['Onboard/osk/' + x for x in SOURCES]

DEPENDS = ['osk_module.h', 
           'osk_devices.h', 
           'osk_util.h',
          ]

module = Extension(
    OSK_EXTENSION,

    # even MINOR numbers for stable versions
    define_macros = [('MAJOR_VERSION', '0'),
                     ('MINOR_VERSION', '2'),
                     ('MICRO_VERSION', '0')],

    sources = SOURCES,
    depends = DEPENDS,   # trigger rebuild on changes to these

    **pkgconfig('gdk-3.0', 'x11', 'xi', 'xtst')
)


##### setup #####

DistUtilsExtra.auto.setup(
    name = 'onboard',
    version = '0.96.0',
    author = 'Chris Jones',
    author_email = 'chris.e.jones@gmail.com',
    maintainer = 'Ubuntu Core Developers',
    maintainer_email = 'ubuntu-devel-discuss@lists.ubuntu.com',
    url = 'http://launchpad.net/onboard/',
    license = 'gpl',
    description = 'Simple On-screen Keyboard',

    packages = ['Onboard'],

    data_files = [('share/glib-2.0/schemas', glob.glob('data/*.gschema.xml')),
                  ('share/GConf/gsettings', glob.glob('data/*.convert')),
                  ('share/onboard', glob.glob('AUTHORS')),
                  ('share/onboard', glob.glob('CHANGELOG')),
                  ('share/onboard', glob.glob('COPYING')),
                  ('share/onboard', glob.glob('NEWS')),
                  ('share/onboard', glob.glob('README')),
                  ('share/onboard', glob.glob('onboard-defaults.conf.example')),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/*.svg')),
                  ('share/onboard/data', glob.glob('data/*.gif')),
                  ('share/onboard/docs', glob.glob('docs/*')),
                  ('share/onboard/layouts', glob.glob('layouts/*.*')),
                  ('share/onboard/layouts/images', glob.glob('layouts/images/*')),
                  ('share/onboard/themes', glob.glob('themes/*')),
                  ('share/onboard/scripts', glob.glob('scripts/*'))],

    scripts = ['onboard', 'onboard-settings'],

    requires = [OSK_EXTENSION],

    ext_modules = [module]
)


