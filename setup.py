#!/usr/bin/python
from distutils.core import setup
import glob
setup(
    name = 'onboard',
    version = '0.92ubuntu1',
    author = 'Chris Jones',
    author_email = 'cej105@soton.ac.uk',
    maintainer = 'Ubuntu Core Developers',
    maintainer_email = 'ubuntu-devel-discuss@lists.ubuntu.com',
    url = 'http://launchpad.net/onboard/',
    license = 'gpl',
    description = 'Simple On-screen Keyboard',
    packages = ['Onboard'],
    data_files = [('share/gconf/schemas', glob.glob('data/*.schemas')),
                  ('share/applications', glob.glob('data/*.desktop')),
                  ('share/onboard', glob.glob('AUTHORS')),
                  ('share/onboard', glob.glob('CHANGELOG')),
                  ('share/onboard', glob.glob('COPYING')),
                  ('share/onboard', glob.glob('NEWS')),
                  ('share/onboard', glob.glob('README')),
                  ('share/onboard/data', glob.glob('data/*.svg')),
                  ('share/onboard/data', glob.glob('data/*.gif')),
                  ('share/onboard/data', glob.glob('data/*.glade*')),
                  ('share/onboard/docs', glob.glob('docs/*')),
                  ('share/onboard/layouts', glob.glob('layouts/*')),
                  ('share/onboard/scripts', glob.glob('scripts/*'))],
    scripts = ['onboard', 'onboard-settings']
)

