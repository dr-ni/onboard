/*
 * Copyright © 2012 marmuta
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
#include "osk_text_classifier.h"


#include <gdk/gdkx.h>

#ifdef USE_LANGUAGE_CLASSIFIER
#include <libexttextcat/textcat.h>
#endif

typedef struct {
    PyObject_HEAD

    #ifdef USE_LANGUAGE_CLASSIFIER
    void* textcat_handle;
    #endif
} OskTextClassifier;

OSK_REGISTER_TYPE (OskTextClassifier, osk_text_classifier, "TextClassifier")

static int
osk_text_classifier_init (OskTextClassifier *tc, PyObject *args, PyObject *kwds)
{
    #ifdef USE_LANGUAGE_CLASSIFIER
    tc->textcat_handle = NULL;
    #endif
    return 0;
}

static void
osk_text_classifier_dealloc (OskTextClassifier *tc)
{
    #ifdef USE_LANGUAGE_CLASSIFIER
    if (tc->textcat_handle)
        textcat_Done(tc->textcat_handle);
    #endif

    OSK_FINISH_DEALLOC (tc);
}

static PyObject *
osk_text_classifier_has_language_classifier (PyObject *self)
{
    #ifdef USE_LANGUAGE_CLASSIFIER
    return PyBool_FromLong(1);
    #else
    return PyBool_FromLong(0);
    #endif
}

static PyObject *
osk_text_classifier_init_exttextcat (PyObject *self, PyObject *args)
{
    Bool success = False;
    char* conf_file;
    char* fingerprint_path;

    if (!PyArg_ParseTuple (args, "eses:init",
                           NULL, &conf_file, NULL, &fingerprint_path))
        return NULL;

    #ifdef USE_LANGUAGE_CLASSIFIER
    OskTextClassifier *tc = (OskTextClassifier*) self;

    if (tc->textcat_handle)
        textcat_Done(tc->textcat_handle);

    tc->textcat_handle = special_textcat_Init(conf_file, fingerprint_path);

    success = tc->textcat_handle != NULL;
    #endif

    PyMem_Free(conf_file);

    return PyBool_FromLong(success);
}

static PyObject *
osk_text_classifier_classify_language (PyObject *self, PyObject *args)
{
    char* text = NULL;
    int text_size;
    PyObject* result = NULL;

    if (!PyArg_ParseTuple (args, "es#:classify_language",
                           NULL, &text, &text_size))
        return NULL;

    #ifdef USE_LANGUAGE_CLASSIFIER
    OskTextClassifier *tc = (OskTextClassifier*) self;
    if (tc->textcat_handle)
    {
        char* ids = textcat_Classify(tc->textcat_handle, text, text_size);
        if (ids)
            result = PyUnicode_FromString(ids);
    }
    #endif

    PyMem_Free(text);

    if (result)
        return result;

    Py_RETURN_NONE;
}


static PyMethodDef osk_text_classifier_methods[] = {
    { "has_language_classifier",
        (PyCFunction)osk_text_classifier_has_language_classifier,
        METH_NOARGS, NULL },
    { "init_exttextcat",
        (PyCFunction) osk_text_classifier_init_exttextcat,
        METH_VARARGS, NULL },
    { "classify_language",
        (PyCFunction) osk_text_classifier_classify_language,
        METH_VARARGS, NULL },

    { NULL, NULL, 0, NULL }
};

