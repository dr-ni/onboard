/*
 * Copyright © 2011 Gerd Kohlberger
 *
 * Onboard is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * Onboard is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef __OSK_UTIL__
#define __OSK_UTIL__

#include <Python.h>

int __osk_util_register_type (PyObject *module);

enum
{
    PRIMARY_BUTTON   = 1,
    MIDDLE_BUTTON    = 2,
    SECONDARY_BUTTON = 3,
};

enum
{
    CLICK_TYPE_SINGLE = 3,
    CLICK_TYPE_DOUBLE = 2,
    CLICK_TYPE_DRAG   = 1,
};

#endif /* __OSK_UTIL__ */
