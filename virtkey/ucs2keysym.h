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

#ifndef UCS2KEYSYM_H_
#define UCS2KEYSYM_H_

#endif /*UCS2KEYSYM_H_*/
#include <X11/X.h>
#include <stdio.h>

KeySym ucs2keysym(long ucs);
