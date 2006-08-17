#ifndef PYTHONFAKEKEY_H_
#define PYTHONFAKEKEY_H_

#endif /*PYTHONFAKEKEY_H_*/





#include <Python.h>
#include <X11/keysym.h>
#include "ucs2keysym.h"
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>
#include <X11/XKBlib.h>
#include <X11/extensions/XKBgeom.h>

#define N_MODIFIER_INDEXES (Mod5MapIndex + 1)

/* Module globals */
static PyObject *virtkey_error = NULL;

/* type */
staticforward PyTypeObject virtkey_Type;

/* object */
typedef struct {
  PyObject_HEAD
  char* displayString;
  Display * display;
  
  
  int      min_keycode, max_keycode;
  int      n_keysyms_per_keycode;
  KeySym  *keysyms;
  int      held_keycode;
  int      held_state_flags;
  KeyCode  modifier_table[N_MODIFIER_INDEXES];
  int      shift_mod_index, alt_mod_index, meta_mod_index;
  
 
} virtkey;



static PyObject * virtkey_layout_get_sections(PyObject * self,PyObject *args);

static PyObject * virtkey_send_unicode(PyObject * self,PyObject *args, Bool press);
static PyObject * virtkey_send_keysym(PyObject * self,PyObject *args, Bool press);

static PyObject * virtkey_press_keysym(PyObject * self,PyObject *args);
static PyObject * virtkey_release_keysym(PyObject * self,PyObject *args);

static PyObject * virtkey_press_unicode(PyObject * self,PyObject *args);
static PyObject * virtkey_release_unicode(PyObject * self,PyObject *args);

static PyObject * virtkey_send(virtkey * cvirt, long out, Bool press);

static PyObject * virtkey_Repr(PyObject * self);

static PyObject * virtkey_new(PyObject * self, PyObject * args);

void change_locked_mods(int mask, Bool lock, virtkey * cvirt);


