#!/usr/bin/python
from distutils.core import setup
import glob
setup(
    name = 'onboard',
    author = 'Chris Jones',
    author_email = 'cej105@soton.ac.uk',
    maintainer = 'Ubuntu Core Developers',
    maintainer_email = 'ubuntu-devel-discuss@lists.ubuntu.com',
    url = 'http://launchpad.net/onboard/',
    license = 'gpl',
    description = 'Simple On-screen Keyboard',
    packages = ['Onboard'],
    data_files = [('share/applications', glob.glob('data/*.desktop')),
                  ('share/onboard/data', glob.glob('data/*.svg')),
                  ('share/onboard/data', glob.glob('data/*.glade*')),
                  ('share/onboard/layouts', glob.glob('layouts/*')),
                  ('share/onboard/scripts', glob.glob('scripts/*'))],
    scripts = ['onboard', 'onboard-settings']
)

