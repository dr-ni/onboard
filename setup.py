#!/usr/bin/python
import glob
from distutils import version

try:
    import DistUtilsExtra.auto
except ImportError:
    import sys
    print >> sys.stderr, 'To build Onboard you need https://launchpad.net/python-distutils-extra'
    sys.exit(1)

current_ver = version.StrictVersion(DistUtilsExtra.auto.__version__)
required_ver = version.StrictVersion('2.12')
assert current_ver >= required_ver , 'needs DistUtilsExtra.auto >= 2.12'

DistUtilsExtra.auto.setup(
    name = 'onboard',
    version = '0.93.0',
    author = 'Chris Jones',
    author_email = 'chris.e.jones@gmail.com',
    maintainer = 'Ubuntu Core Developers',
    maintainer_email = 'ubuntu-devel-discuss@lists.ubuntu.com',
    url = 'http://launchpad.net/onboard/',
    license = 'gpl',
    description = 'Simple On-screen Keyboard',

    packages = ['Onboard'],

    data_files = [('share/gconf/schemas', glob.glob('data/*.schemas')),
                  ('share/onboard', glob.glob('AUTHORS')),
                  ('share/onboard', glob.glob('CHANGELOG')),
                  ('share/onboard', glob.glob('COPYING')),
                  ('share/onboard', glob.glob('NEWS')),
                  ('share/onboard', glob.glob('README')),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/*.svg')),
                  ('share/onboard/data', glob.glob('data/*.gif')),
                  ('share/onboard/data', glob.glob('data/*.ui*')),
                  ('share/onboard/docs', glob.glob('docs/*')),
                  ('share/onboard/layouts', glob.glob('layouts/*')),
                  ('share/onboard/scripts', glob.glob('scripts/*'))],

    scripts = ['onboard', 'onboard-settings'],
)

