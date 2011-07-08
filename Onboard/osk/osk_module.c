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

#include "osk_module.h"
#include "osk_devices.h"
#include "osk_util.h"

#include <gdk/gdk.h>

static PyMethodDef osk_methods[] = {
    { NULL, NULL, 0, NULL }
};

PyObject *
__osk_exception_get_object (void)
{
    static PyObject *error = NULL;

    if (error == NULL)
        error = PyErr_NewException ("osk.error", NULL, NULL);

    return error;
}

PyMODINIT_FUNC
initosk (void)
{
    PyObject *module;
    PyObject *error;

    module = Py_InitModule3 ("osk", osk_methods, "osk utility module");
    if (module == NULL)
    {
        fprintf (stderr, "Error: Failed to initialize the \"osk\" module.\n");
        return;
    }

    error = __osk_exception_get_object ();
    Py_INCREF (error);
    PyModule_AddObject (module, "error", error);

    gdk_init (NULL, NULL);

    if (__osk_devices_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"Devices\" type.\n");

    if (__osk_util_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"Util\" type.\n");
}
