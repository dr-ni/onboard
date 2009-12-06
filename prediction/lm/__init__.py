# We first need to detect if we're being called as part of the setup
# procedure itself in a reliable manner.
try:
    __LM_SETUP__
except NameError:
    __LM_SETUP__ = False


if __LM_SETUP__:
    import sys as _sys
    print >> _sys.stderr, 'Running from source directory.'
    del _sys
else:
    from lm import *

