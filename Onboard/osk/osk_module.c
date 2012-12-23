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
#include "osk_dconf.h"
#include "osk_struts.h"

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

#if PY_MAJOR_VERSION >= 3
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "osk",                /* m_name */
        "osk utility module", /* m_doc */
        -1,                   /* m_size */
        osk_methods,          /* m_methods */
        NULL,                 /* m_reload */
        NULL,                 /* m_traverse */
        NULL,                 /* m_clear */
        NULL,                 /* m_free */
    };
#endif

static PyObject *
moduleinit (void)
{
    PyObject *module;
    PyObject *error;

    #if PY_MAJOR_VERSION >= 3
        module = PyModule_Create(&moduledef);
    #else
        module = Py_InitModule("osk", osk_methods);
    #endif
    if (module == NULL)
    {
        fprintf (stderr, "Error: Failed to initialize the \"osk\" module.\n");
        return NULL;
    }

    error = __osk_exception_get_object ();
    Py_INCREF (error);
    PyModule_AddObject (module, "error", error);

    gdk_init (NULL, NULL);

    if (__osk_devices_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"Devices\" type.\n");

    if (__osk_device_event_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"DeviceEvent\" type.\n");

    if (__osk_util_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"Util\" type.\n");

    if (__osk_dconf_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"DConf\" type.\n");

    if (__osk_struts_register_type (module) < 0)
        fprintf (stderr, "Error: Failed to register \"Struts\" type.\n");

    return module;
}

#if PY_MAJOR_VERSION < 3
    PyMODINIT_FUNC
    initosk(void)
    {
        moduleinit();
    }
#else
    PyMODINIT_FUNC
    PyInit_osk(void)
    {
        return moduleinit();
    }
#endif

