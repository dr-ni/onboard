/*
 * python-virtkey
 *
 * A python extension for emulating keypresses and getting keyboard geometry from the xserver.
 *
 * Uses ideas from Fontconfig, libvirtkeys.c, keysym2ucs.c and dasher. 
 *
 * Authored By Chris Jones  <cej105@soton.ac.uk>
 *
 * Copyright (C) 2006 Chris Jones
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the
 * Free Software Foundation, Inc., 59 Temple Place - Suite 330,
 * Boston, MA 02111-1307, USA.
 */

#include "python-virtkey.h"


/* constructor */
static PyObject * virtkey_NEW()
  	{ 
  	virtkey *object;
  	
  	//initialize python object and open display.
  	object = PyObject_NEW(virtkey, &virtkey_Type);
    if (object != NULL)
       
       object->displayString = getenv ("DISPLAY");
       if (!object->displayString) object->displayString = ":0.0";
       object->display = XOpenDisplay(object->displayString);
       if (!object->display) {
       		PyErr_SetString(virtkey_error, "failed initialize display :(");
       		return Py_None;
       	}
  	
  	
  	XModifierKeymap *modifiers;
  	int              mod_index;
 	int              mod_key;
  	KeyCode         *kp;
  	
  	XDisplayKeycodes(object->display, &object->min_keycode, &object->max_keycode);
  		
	object->keysyms = XGetKeyboardMapping(object->display, 
				    object->min_keycode, 
				    object->max_keycode - object->min_keycode + 1, 
				    &object->n_keysyms_per_keycode);
				    
	modifiers = XGetModifierMapping(object->display);
	
	kp = modifiers->modifiermap; 
	
	for (mod_index = 0; mod_index < 8; mod_index++)
    {
      object->modifier_table[mod_index] = 0;
      
      for (mod_key = 0; mod_key < modifiers->max_keypermod; mod_key++)
	{
	  int keycode = kp[mod_index * modifiers->max_keypermod + mod_key]; 
	  
	  if (keycode != 0)
	    {
	      object->modifier_table[mod_index] = keycode;
	      break;
	    }
	}
    }
  
  for (mod_index = Mod1MapIndex; mod_index <= Mod5MapIndex; mod_index++)
    {
      if (object->modifier_table[mod_index])
		{
		  KeySym ks = XKeycodeToKeysym(object->display, 
					       object->modifier_table[mod_index], 0);
		  
		  /* 
		   *  Note: ControlMapIndex is already defined by xlib
		   *        ShiftMapIndex*/
		   
		  
		  switch (ks)
		    {
		    case XK_Meta_R:
		    case XK_Meta_L:
		      object->meta_mod_index = mod_index;
		      break;
		      
		    case XK_Alt_R:
		    case XK_Alt_L:
		      object->alt_mod_index = mod_index;
		      break;
		      
		    case XK_Shift_R:
		    case XK_Shift_L:
		      object->shift_mod_index = mod_index;
		      break;
		    }
		}
    }
  
  	if (modifiers)
    XFreeModifiermap(modifiers);
	getKbd(object);	
  	return (PyObject *)object;
	
}

static void
virtkey_dealloc(PyObject * self)
  { PyMem_DEL(self);
  }

void getKbd(virtkey * cvirt){


	 // we could call XkbGetKeyboard only, but that's broken on XSun 
	  cvirt->kbd = XkbGetMap (cvirt->display, XkbAllComponentsMask, XkbUseCoreKbd); 
	  if (XkbGetGeometry (cvirt->display, cvirt->kbd) != Success) 
		  fprintf (stderr, "Error getting keyboard geometry info.\n");
	  if (XkbGetNames (cvirt->display, XkbAllNamesMask, cvirt->kbd) != Success) 
		  fprintf (stderr, "Error getting key name info.\n");
	 	
	return;
}

long keysym2keycode(virtkey * cvirt, KeySym keysym, int * flags){
  static int modifiedkey;
  KeyCode    code = 0;
 
 if ((code = XKeysymToKeycode(cvirt->display, keysym)) != 0)
    {
 
      if (XKeycodeToKeysym(cvirt->display, code, 0) != keysym)
	{
	
	  if (XKeycodeToKeysym(cvirt->display, code, 1) == keysym)
	    *flags |= 1; 	//can get at it via shift 
	  else
	    code = 0; // urg, some other modifier do it the heavy way
	}
    }
	     	        

  if (!code)
    {
      int index;

      // Change one of the last 10 keysyms to our converted utf8,
      // remapping the x keyboard on the fly. 
      //
      // This make assumption the last 10 arn't already used.
      // TODO: probably safer to check for this. 
      

      modifiedkey = (modifiedkey+1) % 10;

      // Point at the end of keysyms, modifier 0 

      index = (cvirt->max_keycode - cvirt->min_keycode - modifiedkey - 1) * cvirt->n_keysyms_per_keycode;

      cvirt->keysyms[index] = keysym;
      
      XChangeKeyboardMapping(cvirt->display, 
			     cvirt->min_keycode, 
			     cvirt->n_keysyms_per_keycode, 
			     cvirt->keysyms, 
			     (cvirt->max_keycode-cvirt->min_keycode));

      XSync(cvirt->display, False);
	
      // From dasher src;
      // There's no way whatsoever that this could ever possibly
      // be guaranteed to work (ever), but it does.
          
      code = cvirt->max_keycode - modifiedkey - 1;

      // The below is lightly safer;
      //
      //  code = XKeysymToKeycode(fk->display, keysym);
      //
      // but this appears to break in that the new mapping is not immediatly 
      // put to work. It would seem a MappingNotify event is needed so
      // Xlib can do some changes internally ? ( xlib is doing something 
      // related to above ? )
      // 
      // Probably better to try and grab the mapping notify *here* ?
       
  
    }
    return code;
}



static  
PyObject * report_key_info (virtkey * cvirt, XkbKeyPtr key, int col, int *x, int *y, 
		 unsigned int mods)
{
  PyObject * keyObject = PyDict_New();
  
  PyDict_SetItemString(keyObject,"name", PyString_FromStringAndSize(key->name.name,XkbKeyNameLength));
  
  XkbGeometryPtr geom = cvirt->kbd->geom;
  char name[XkbKeyNameLength+1];
  XkbKeyAliasPtr aliases = cvirt->kbd->geom->key_aliases;
  int k,m, num_keycodes = cvirt->kbd->max_key_code  - cvirt->kbd->min_key_code;

  
   // Above calculation is
   // WORKAROUND FOR BUG in XFree86's XKB implementation, 
   // which reports kbd->names->num_keys == 0! 
   // In fact, num_keys should be max_key_code-1, and the names->keys
   // array is indeed valid!
   //
   // [bug identified in XFree86 4.2.0]
   

  strncpy (name, key->name.name, XkbKeyNameLength);
  name[XkbKeyNameLength] = '\0';
  *x += key->gap/10;

  
  
  for (k = cvirt->kbd->min_key_code; k < cvirt->kbd->max_key_code; ++k) 
    {
      if (!strncmp (name, cvirt->kbd->names->keys[k].name, XkbKeyNameLength))
	{ 
	  unsigned int mods_rtn;
	  int extra_rtn;
	  char symname[16];
	  KeySym keysym;
	  PyObject * labels = PyTuple_New(5);
	  int mod = 0;
	  int mods[] = {0,1,2,128,129};
	  for(m = 0; m < 5; ++m)
	  {
		  if (XkbTranslateKeyCode (cvirt->kbd, (KeyCode) k, mods[m], 
					   &mods_rtn, &keysym))
		    {
		      
		      int nchars =
			XkbTranslateKeySym (cvirt->display, &keysym, 0, symname, 
					    15, &extra_rtn);
		      if (nchars) 
			{
			  symname[nchars] = '\0';
			  if (symname){
			  	PyTuple_SetItem(labels,m, PyString_FromString(symname)); 
			  }
			 }
		      else 
			{
			  PyTuple_SetItem(labels,m, PyString_FromString(""));
			} 	
			 	
		    }
		    if (m == 0){
		       
		       PyObject * x1 = PyInt_FromLong(*x + geom->shapes[key->shape_ndx].bounds.x1/10);
		       PyObject * y1 = PyInt_FromLong(*y + geom->shapes[key->shape_ndx].bounds.y1/10);
		       PyObject * x2 = PyInt_FromLong(geom->shapes[key->shape_ndx].bounds.x2/10- geom->shapes[key->shape_ndx].bounds.x1/10);
		       PyObject * y2 = PyInt_FromLong(geom->shapes[key->shape_ndx].bounds.y2/10 - geom->shapes[key->shape_ndx].bounds.y1/10);
		        
		        
		       PyObject * shape = PyTuple_Pack(4, x1,
	    									  y1,
	      									  x2,
						      	   			  y2);
	   		
	   		Py_DECREF(x1);
	   		Py_DECREF(y1);
	   		Py_DECREF(x2);
	   		Py_DECREF(y2);
	   			
	   		*x += geom->shapes[key->shape_ndx].bounds.x2/10;
		        
		        PyDict_SetItemString(keyObject,"shape",shape);
		        					
		        Py_DECREF(shape);
		  	PyDict_SetItemString(keyObject,"keysym", PyInt_FromLong(keysym));
		  	mod = 1;
		     }
	}
       PyDict_SetItemString(keyObject,"labels", labels);
       Py_DECREF(labels);
      }		   
    }
    
    return keyObject;
}

static PyObject * reload_kbd(PyObject * self, PyObject *args)
{
	virtkey * cvirt  = (virtkey *)self;
	XkbFreeKeyboard (cvirt->kbd, XkbAllComponentsMask, True);
	getKbd(cvirt);
}

static PyObject * virtkey_layout_get_section_info(PyObject * self,PyObject *args)
{
  char * requestedSection;
  if (PyArg_ParseTuple(args, "s", &requestedSection)){
	  
	  XkbGeometryPtr geom;
	  virtkey * cvirt  = (virtkey *)self;
	  
	  char * sectionString;
	  
	  PyObject * returnTuple;
	  
	  int i;
	  
	  geom = cvirt->kbd->geom;

	  
	  for (i = 0; i < geom->num_sections; ++i) 
	    {
	        XkbSectionPtr section = &geom->sections[i];
	        sectionString = XGetAtomName (cvirt->display, section->name);
		if (!strcmp(sectionString,requestedSection))
		{
			PyObject *  width = PyInt_FromLong(section->width/10);
			PyObject *  height = PyInt_FromLong(section->height/10);
			
			
			//Increfs width, height
			returnTuple = PyTuple_Pack(2,
				width,
				height);
			
			Py_DECREF(width);
			Py_DECREF(height);
			
		}
		free(sectionString);
	    }
	    
	    
	    
	    if (returnTuple)
	    	return returnTuple;
	    
	    Py_INCREF(Py_None);
	    return Py_None;
  }
}


static PyObject * virtkey_layout_get_keys(PyObject * self,PyObject *args)
{
  char * requestedSection;
  if (PyArg_ParseTuple(args, "s", &requestedSection)){
	  
	  XkbGeometryPtr geom;
	  
	  virtkey * cvirt  = (virtkey *)self;
	  
	  int i, row, col;
	  unsigned int mods = 0;
	  
	  geom = cvirt->kbd->geom;

	  char * sectionString;
	  
	  PyObject * rowTuple;
	  
	  for (i = 0; i < geom->num_sections; ++i) 
	    {
	        XkbSectionPtr section = &geom->sections[i];
	        sectionString = XGetAtomName (cvirt->display, section->name);
		if (!strcmp(sectionString,requestedSection))
		      {
		      rowTuple = PyTuple_New(section->num_rows);
		      for (row = 0; row < section->num_rows; ++row)
			{
			  XkbRowPtr rowp = &section->rows[row];
			  int x = rowp->left/10, y = rowp->top/10;

			  PyObject * keyTuple = PyTuple_New(rowp->num_keys);
			  
			  for (col = 0; col < rowp->num_keys; ++col) 
			    {
			      PyObject * key = report_key_info (cvirt, &rowp->keys[col], col, &x, &y, mods);
			      PyTuple_SET_ITEM(keyTuple,col,key);
			    }
			  PyTuple_SET_ITEM(rowTuple, row,keyTuple);
			}
		      }
		 free(sectionString);
		 }
	  
	   if (rowTuple){
	  	return rowTuple;
	  }
	  }
	 
   	return Py_None;
}


static PyObject * virtkey_layout_get_sections(PyObject * self,PyObject *args)
{
  
  XkbGeometryPtr geom;

  int i;
  
  virtkey * cvirt  = (virtkey *)self;  
  geom = cvirt->kbd->geom;
  
  char * sectionString;
  
  PyObject * sectionTuple = PyTuple_New(geom->num_sections);
  
  for (i = 0; i < geom->num_sections; ++i) 
    {
      XkbSectionPtr section = &geom->sections[i];
      sectionString = XGetAtomName (cvirt->display, section->name);
      PyTuple_SetItem(sectionTuple, i, PyString_FromString(sectionString));
      free(sectionString);
    }
  
  return sectionTuple;
}

static PyObject * virtkey_send(virtkey * cvirt, long out, Bool press){
	
	if (out != 0)
	{
		XTestFakeKeyEvent(cvirt->display, out, 
		press, CurrentTime);
		XSync(cvirt->display, False);
	}else PyErr_SetString(virtkey_error, "failed to get keycode");
	
	return Py_None;
} 

static PyObject * virtkey_send_unicode(PyObject * self,PyObject *args, Bool press){
	virtkey * cvirt  = (virtkey *)self;
	long in = 0;
	long  out = 0;
	int flags = 0;
	if ((PyArg_ParseTuple(args, "i", &in))){//find unicode arg in args tuple.
		out = keysym2keycode(cvirt, ucs2keysym(in), &flags);	
	}
	if (flags)
		change_locked_mods(flags,press,cvirt);
	return virtkey_send(cvirt, out, press);
}

static PyObject * virtkey_send_keysym(PyObject * self,PyObject *args, Bool press){
	virtkey * cvirt  = (virtkey *)self;
	long in = 0;
	long  out = 0;
	int flags = 0;
	if ((PyArg_ParseTuple(args, "i", &in))){//find keysym arg in args tuple.
		
		out = keysym2keycode(cvirt, in, &flags);
	}
	
	if (flags)
		change_locked_mods(flags,press,cvirt);
	return virtkey_send(cvirt, out, press);
}


static PyObject * virtkey_latch_mod(PyObject * self,PyObject *args)
{
	int mask = 0;
	
	virtkey * cvirt  = (virtkey *)self;
	
	if ((PyArg_ParseTuple(args, "i", &mask))){//find mask arg in args tuple.
		XkbLatchModifiers(cvirt->display, XkbUseCoreKbd, mask, mask);
		XSync(cvirt->display, False); //Otherwise it waits until next keypress
	}
	return Py_None;

}

void change_locked_mods(int mask, Bool lock, virtkey * cvirt){
	
	if (lock){
		XkbLockModifiers(cvirt->display, XkbUseCoreKbd, mask, mask);
	}
	else{
		XkbLockModifiers(cvirt->display, XkbUseCoreKbd, mask, 0);
	}
	XSync(cvirt->display, False);
}


static PyObject * virtkey_lock_mod(PyObject * self,PyObject *args)
{	
	int mask = 0;
	
	virtkey * cvirt  = (virtkey *)self;
	
	if ((PyArg_ParseTuple(args, "i", &mask))){//find mask arg in args tuple.
		change_locked_mods(mask, True, cvirt);
	}
	return Py_None;
	      
}

static PyObject * virtkey_unlatch_mod(PyObject * self,PyObject *args)
{
	int mask = 0;
	
	virtkey * cvirt  = (virtkey *)self;

	if ((PyArg_ParseTuple(args, "i", &mask))){//find mask arg in args tuple.
		XkbLatchModifiers(cvirt->display, XkbUseCoreKbd, mask, 0);
		XSync(cvirt->display, False);
	}
	return Py_None;
	
}

static PyObject * virtkey_unlock_mod(PyObject * self,PyObject *args)
{	
	int mask = 0;
	
	virtkey * cvirt  = (virtkey *)self;

	if ((PyArg_ParseTuple(args, "i", &mask))){//find mask arg in args tuple.
		change_locked_mods(mask, False, cvirt);
	}
	return Py_None;
	
}



static PyObject * virtkey_press_keysym(PyObject * self,PyObject *args)
{
	return virtkey_send_keysym(self, args, True);
	
}

static PyObject * virtkey_release_keysym(PyObject * self,PyObject *args)
{
	return virtkey_send_keysym(self, args, False);
	
}

static PyObject * virtkey_press_unicode(PyObject * self,PyObject *args)
{
	return virtkey_send_unicode(self, args, True);
	
}

static PyObject * virtkey_release_unicode(PyObject * self,PyObject *args)
{
	return virtkey_send_unicode(self, args, False);
		
}


/* Method table */
static PyMethodDef virtkey_methods[] = {
  {"press_unicode", virtkey_press_unicode, METH_VARARGS},
  {"release_unicode", virtkey_release_unicode, METH_VARARGS},
  {"press_keysym", virtkey_press_keysym, METH_VARARGS},
  {"release_keysym", virtkey_release_keysym, METH_VARARGS},
  {"latch_mod", virtkey_latch_mod, METH_VARARGS},
  {"lock_mod", virtkey_lock_mod, METH_VARARGS},
  {"unlatch_mod", virtkey_unlatch_mod, METH_VARARGS},
  {"unlock_mod", virtkey_unlock_mod, METH_VARARGS},
  {"layout_get_sections", virtkey_layout_get_sections, METH_VARARGS},
  {"layout_get_keys", virtkey_layout_get_keys, METH_VARARGS},
  {"layout_get_section_size", virtkey_layout_get_section_info, METH_VARARGS},
  {NULL, NULL},
};

/* Callback routines */

static PyObject *
virtkey_GetAttr(PyObject * self,char * attrname)
  {
    return Py_FindMethod(virtkey_methods, self, attrname);
  }

static PyObject * virtkey_Repr(PyObject * self)
  {     return PyString_FromString("I am a virtkey object");
  }

/* Type definition */
/* remember the forward declaration above, this is the real definition */
static PyTypeObject virtkey_Type = {
  PyObject_HEAD_INIT(&PyType_Type)
  0,
  "virtkey",
  sizeof(virtkey),
  0,
  (destructor)virtkey_dealloc,
  0,
  (getattrfunc)virtkey_GetAttr,
  0,
  0,
  (reprfunc)virtkey_Repr,
  /* the rest are NULLs */
};

/* Python constructor */

static PyObject * virtkey_new(PyObject * self, PyObject * args)
  { PyObject *result = NULL;
   // char* value; 
	//return Py_None;
    //if (PyArg_ParseTuple(args, "|s", &value))
      result = virtkey_NEW();
    return result;
  }

/* Module functions */

static PyMethodDef methods[] = {
  {"virtkey", virtkey_new, METH_VARARGS},
  {NULL, NULL},
};

/* Module init function */

void initvirtkey()
  { PyObject *m, *d;

    m = Py_InitModule("virtkey", methods);
    d = PyModule_GetDict(m);

    /* initialize module variables/constants */

#if PYTHON_API_VERSION >= 1007
    virtkey_error = PyErr_NewException("virtkey.error", NULL, NULL);
#else
    virtkey_error = Py_BuildValue("s", "virtkey.error");
#endif
    PyDict_SetItemString(d, "error", virtkey_error);
  }


