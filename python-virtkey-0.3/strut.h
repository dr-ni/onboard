#include <gdk/gdk.h>
#include <gdk/gdkx.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>

static Atom
strut_atom_get (const char *atom_name);

void
set_wmspec_strut (GdkWindow *window,
			 int        left,
			 int        right,
			 int        top,
			 int        bottom);
