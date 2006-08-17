/*
 * AT-SPI - Assistive Technology Service Provider Interface
 * (Gnome Accessibility Project; http://developer.gnome.org/projects/gap)
 *
 * Copyright 2001, 2002 Sun Microsystems Inc.,
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Library General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Library General Public License for more details.
 *
 * You should have received a copy of the GNU Library General Public
 * License along with this library; if not, write to the
 * Free Software Foundation, Inc., 59 Temple Place - Suite 330,
 * Boston, MA 02111-1307, USA.
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/XKBlib.h>
#include <X11/extensions/XKBgeom.h>

static	Display *display;

static void 
report_key_info (XkbDescPtr kbd, XkbKeyPtr key, int col, int *x, int *y, 
		 unsigned int mods)
{
  XkbGeometryPtr geom = kbd->geom;
  char name[XkbKeyNameLength+1];
  XkbKeyAliasPtr aliases = kbd->geom->key_aliases;
  int k, num_keycodes = kbd->max_key_code  - kbd->min_key_code;

  /* 
   * Above calculation is
   * WORKAROUND FOR BUG in XFree86's XKB implementation, 
   * which reports kbd->names->num_keys == 0! 
   * In fact, num_keys should be max_key_code-1, and the names->keys
   * array is indeed valid!
   *
   * [bug identified in XFree86 4.2.0]
   */

  strncpy (name, key->name.name, XkbKeyNameLength);
  name[XkbKeyNameLength] = '\0';
  *x += key->gap/10;

  fprintf (stdout, "\t\t\tKey %d (%s); ", 
	   col, name);
  for (k = 0; k < geom->num_key_aliases; ++k) 
    {
      if (!strncmp (name, aliases[k].real, XkbKeyNameLength))
	{ 
	  char alias[XkbKeyNameLength + 1];
	  snprintf (alias, XkbKeyNameLength, "%s",
		    aliases[k].alias);
	  alias[XkbKeyNameLength] = '\0';
	  fprintf (stdout, "aka %s; ", alias);
	}		  
    }
  aliases = kbd->names->key_aliases;
  for (k = 0; k < kbd->names->num_key_aliases; ++k) 
    {
      if (!strncmp (name, aliases[k].real, XkbKeyNameLength))
	{ 
	  char alias[XkbKeyNameLength + 1];
	  snprintf (alias, XkbKeyNameLength, "%s",
		    aliases[k].alias);
	  alias[XkbKeyNameLength] = '\0';
	  fprintf (stdout, "aka %s; ", alias);
	}		  
    }

  for (k = kbd->min_key_code; k < kbd->max_key_code; ++k) 
    {
      if (!strncmp (name, kbd->names->keys[k].name, XkbKeyNameLength))
	{ 
	  unsigned int mods_rtn;
	  int extra_rtn;
	  char symname[16];
	  KeySym keysym;
	  if (XkbTranslateKeyCode (kbd, (KeyCode) k, mods, 
				   &mods_rtn, &keysym))
	    {
	      int nchars =
		XkbTranslateKeySym (display, &keysym, 0, symname, 
				    15, &extra_rtn);
	      if (nchars) 
		{
		  symname[nchars] = '\0';
		  fprintf (stdout, "keycode %d; \"%s\" ", 
			   k, symname[0] ? symname : "<none>"); 	
		}
	      else
		fprintf (stdout, "keycode %d; [none] ", k); 	
	    }
	}		  
    }
  fprintf (stdout, "; %d,%d to %d,%d mm\n", 
	   (*x + geom->shapes[key->shape_ndx].bounds.x1/10),
	   *y + geom->shapes[key->shape_ndx].bounds.y1/10,
	   (*x + geom->shapes[key->shape_ndx].bounds.x2/10),
	   *y + geom->shapes[key->shape_ndx].bounds.y2/10);
  
  *x += geom->shapes[key->shape_ndx].bounds.x2/10;
}

static void
report_doodad_info (Display *display, XkbDescPtr kbd, XkbDoodadPtr doodad, 
		    int i, const char *typename)
{
  XkbGeometryPtr geom = kbd->geom;

  fprintf (stdout, "\t\tDoodad (%s) %d: (%s); %d,%d; ", 
	   typename,
	   i,
	   XGetAtomName (display, doodad->any.name),
	   doodad->any.top/10,
	   doodad->any.left/10);
  switch (doodad->any.type) 
    {
    case XkbOutlineDoodad:
    case XkbSolidDoodad:
      fprintf (stdout, "%d,%d\n",
	       geom->shapes[doodad->shape.shape_ndx].bounds.x2,
	       geom->shapes[doodad->shape.shape_ndx].bounds.y2);
      break;
    case XkbTextDoodad:
      fprintf (stdout, "%d,%d\n\t\t[%s] (color %s)\n\t\t[%s]\n",
	       doodad->text.left + doodad->text.width,
	       doodad->text.top + doodad->text.height,
	       doodad->text.text,
	       geom->colors[doodad->text.color_ndx].spec,
	       doodad->text.font);
      break;
    case XkbIndicatorDoodad:
      fprintf (stdout, "%d,%d [%s/%s]\n",
	       geom->shapes[doodad->indicator.shape_ndx].bounds.x2,
	       geom->shapes[doodad->indicator.shape_ndx].bounds.y2,
	       geom->colors[doodad->indicator.on_color_ndx].spec,
	       geom->colors[doodad->indicator.off_color_ndx].spec);
      break;
    case XkbLogoDoodad:
      fprintf (stdout, "%d,%d; \"%s\" (color %s)\n",
	       geom->shapes[doodad->logo.shape_ndx].bounds.x2,
	       geom->shapes[doodad->logo.shape_ndx].bounds.y2,
	       doodad->logo.logo_name,
	       geom->colors[doodad->logo.color_ndx].spec);
      break;
    }
}

static void
report_type_info (Display *display, XkbKeyTypePtr key_type)
{
  int i;
  fprintf (stderr, "key type %s\n",   
	   XGetAtomName (display, key_type->name));
  for (i=0; i < key_type->map_count; ++i) 
    {
      fprintf (stderr, "map entry %d: level %d [%s]; ", i, 
	       key_type->map[i].level,
	       XGetAtomName (display, 
			     key_type->level_names[key_type->map[i].level]));
      fprintf (stderr, "modifiers: %x; ",
	       key_type->map[i].mods.mask);
      fprintf (stderr, "preserve: %x\n",
	       (key_type->preserve) ? key_type->preserve[i].mask : 0);
    }  
}


int main (int argc, char **argv)
{
  XEvent xev;
  XkbDescPtr kbd;
  XkbGeometryPtr geom;
  int ir, xkb_base_event_type, reason_return;
  char *display_name = getenv ("DISPLAY");
  int i, j, k, row, col;
  unsigned int mods = 0;
  
  if (!display_name) display_name = ":0.0";
  
  display = XkbOpenDisplay (display_name,
			    &xkb_base_event_type,
			    &ir, NULL, NULL, &reason_return);
  if (!display)
    {
      fprintf (stderr, "Could not connect to display! (%d)\n",
	       reason_return);
      exit (-1);
    }

  if (argc > 1) mods = atoi (argv[1]);
  
  /* we could call XkbGetKeyboard only, but that's broken on XSun */
  kbd = XkbGetMap (display, XkbAllComponentsMask, XkbUseCoreKbd); 
  if (XkbGetGeometry (display, kbd) != Success) 
	  fprintf (stderr, "Error getting keyboard geometry info.\n");
  if (XkbGetNames (display, XkbAllNamesMask, kbd) != Success) 
	  fprintf (stderr, "Error getting key name info.\n");

  geom = kbd->geom;

  fprintf (stdout, "keyboard %s\n\t[keycodes %s, symbols %s, physical symbols %s]\n",
	   XGetAtomName (display, geom->name),
	   XGetAtomName (display, kbd->names->keycodes),
	   XGetAtomName (display, kbd->names->symbols),
	   XGetAtomName (display, kbd->names->phys_symbols));
  fprintf (stdout, "overall dimensions %d by %d mm\n", 
	   geom->width_mm/10, geom->height_mm/10);
  fprintf (stdout, "label font : \t%s\n", geom->label_font);
  fprintf (stdout, "label color : \t%s\n", geom->label_color->spec);
  fprintf (stdout, "base color : \t%s\n", geom->base_color->spec);

  for (i = 0; i < geom->num_sections; ++i) 
    {
      XkbSectionPtr section = &geom->sections[i];
      fprintf (stdout, "\tSection %d: (%s)\n", i,
	       XGetAtomName (display, section->name));
      for (row = 0; row < section->num_rows; ++row)
	{
	  XkbRowPtr rowp = &section->rows[row];
	  int x = rowp->left/10, y = rowp->top/10;
	  fprintf (stdout, "\t\tRow %d; at %d,%d mm; %d keys\n",
		   row,
		   rowp->left/10,
		   rowp->top/10,
		   rowp->num_keys);
	  for (col = 0; col < rowp->num_keys; ++col) 
	    {
	      report_key_info (kbd, &rowp->keys[col], col, &x, &y, mods);
	    }
	}
      for (j = 0; j < section->num_overlays; ++j) 
	{
	  XkbOverlayPtr overlay = &section->overlays[j];
	  fprintf (stdout, "\t\tOverlay %s, \'under\' section %s\n", 
		   XGetAtomName (display, overlay->name),
		   XGetAtomName (display, overlay->section_under->name));
	  for (row = 0; row < overlay->num_rows; ++row)
	    {
	      XkbOverlayRowPtr rowp = &overlay->rows[row];
	      fprintf (stdout, "\t\t\tOverlay row %d, %d,%d \n",
		       row,
		       overlay->section_under->rows[rowp->row_under].left,
		       overlay->section_under->rows[rowp->row_under].top);
	    }
	}
      for (j = 0; j < section->num_doodads; ++j) 
	{
	  report_doodad_info (display, kbd, &section->doodads[j], j, "section");
	}
    }
  for (i = 0; i < geom->num_doodads; ++i) 
    {
      report_doodad_info (display, kbd, &geom->doodads[i], i, "toplevel");
    }

  if (kbd->map && kbd->map->types) 
    for (i = 0; i < kbd->map->num_types; ++i)
      {
	report_type_info (display, &kbd->map->types[i]);
      }

  XkbFreeKeyboard (kbd, XkbAllComponentsMask, True);

  return 0;
}

