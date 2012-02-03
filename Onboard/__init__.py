# -*- coding: utf-8 -*-

from __future__ import division, print_function, unicode_literals

try:
    from . import osk
except ImportError:
    # We might be running from source, so try again with 
    # the build directory in the path
    import sys, os, glob
    from os.path import dirname, abspath, join
    path = dirname(dirname(abspath(__file__)))
    pattern = join(path, 'build', 
                         'lib*{}.*'.format(sys.version_info.major),
                         'Onboard')
    paths = glob.glob(pattern)
    if paths:
        sys.path.append(paths[0])
    print("running from source; looking for osk in " + str(paths))

