try:
    import osk
except ImportError:
    # We might be running from source, so try again with 
    # the build directory in the path
    import sys, os, glob
    from os.path import dirname, abspath, join
    path = dirname(dirname(abspath(__file__)))
    paths = glob.glob(join(path, 'build', 'lib*', 'Onboard'))
    if paths:
        sys.path.append(paths[0])
    print "running from source; looking for osk in " + str(paths)

