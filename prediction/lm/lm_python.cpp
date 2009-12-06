/*
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: marmuta <marmvta@gmail.com>

Examples:

import lm
model = lm.LanguageModelDynamic()

model.count_ngram([u"we"])
model.count_ngram([u"we", u"saw"])
model.count_ngram([u"we", u"saw", u"dolphins"])
model.count_ngram([u"saw"])
model.count_ngram([u"saw", u"dolphins"])
model.count_ngram([u"dolphins"])

for ng in model.iter_ngrams():
    print ng

model.save("/tmp/dolphins.lm")
model.predict([u"we", u"saw", u""])

model.load("/tmp/dolphins.lm")
model.predict([u"we", u"saw", u"dol"], 2)

*/

#include "Python.h"
#include "structmember.h"

#include "lm_dynamic.h"

using namespace std;

// hide warning: invalid access to non-static data member of NULL object
#define my_offsetof(TYPE, MEMBER) \
        ((size_t)((char *)&(((TYPE *)0x10)->MEMBER) - (char*)0x10))

#if 1
void* HeapAlloc(size_t size)
{
    return PyMem_Malloc(size);
}

void HeapFree(void* p)
{
    return PyMem_Free(p);
}
#else
void* HeapAlloc(size_t size)
{
    return malloc(size);
}

void HeapFree(void* p)
{
    return free(p);
}
#endif

// python iterator object for the traversal of the n-gram trie
class NGramIter
{
    public:
        NGramIter(class LanguageModelDynamic* _lm, TrieRoot* root)
        : it(root)
        {
            lm = _lm;
            first_time = true;
            this->root = root;
        }

        // next() function of pythons iterator interface
        BaseNode* next()
        {
            do
            {
                // python semantics: first item _after_ first increment
                if (first_time)
                    first_time = false;
                else
                    it++;
            } while (*it == root);
            return *it;
        }

        void get_ngram(vector<WordId>& ngram)
        {
            it.get_ngram(ngram);
        }

    public:
        PyObject_HEAD

        TrieRoot::iterator it;
        TrieNode* root;
        LanguageModelDynamic* lm;
        bool first_time;
};


static void
NGramIter_dealloc(NGramIter* self)
{
    #ifndef NDEBUG
    printf("NGramIter_dealloc: NGramIter=%p, ob_refcnt=%d\n", self, (int)((PyObject*)self)->ob_refcnt);
    #endif
    self->~NGramIter();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyObject *
NGramIter_iter(PyObject *self)
{
    return self;
}

static PyObject *
NGramIter_iternext(PyObject *self)
{
    int i;
    int error = 0;
    PyObject *result = NULL;

    NGramIter* iter = (NGramIter*) self;
    //printf("iternext: %p, ob_refcnt=%d\n", iter, ((PyObject*)iter)->ob_refcnt);

    BaseNode* node = iter->next();
    if (!node)
        return NULL;

    vector<WordId> ngram;
    iter->get_ngram(ngram);

    // build return value
    result = PyTuple_New(2);
    if (!result)
    {
        PyErr_SetString(PyExc_MemoryError, "failed to allocate result tuple");
        error = 1;
    }
    else
    {

        //printf("%ls, %d, %d\n", word, ngram[i], wcslen(word));
        PyObject *ongram = PyTuple_New(ngram.size());
        for (i=0; i<(int)ngram.size(); i++)
        {
            PyObject* oword = NULL;
            wchar_t* word = iter->lm->dictionary.id_to_word(ngram[i]);
            if (word)
            {
                //printf("%ls, %d, %d\n", word, ngram[i], wcslen(word));
                oword = PyUnicode_FromWideChar(word, wcslen(word));
                if (!oword)
                {
                    PyErr_SetString(PyExc_ValueError, "failed to create unicode string for ngram tuple");
                    error = 1;
                    Py_XDECREF(oword);
                    break;
                }
            }
            else
            {
                Py_INCREF(Py_None);
                oword = Py_None;
            }
            PyTuple_SetItem(ongram, i, oword);
        }

        if (!error)
        {
            PyTuple_SetItem(result, 0, ongram);
            PyTuple_SetItem(result, 1, PyInt_FromLong(node->count));
//            PyTuple_SetItem(result, 2, PyInt_FromLong(node->N1pxr));
//            PyTuple_SetItem(result, 3, PyInt_FromLong(node->N1pxrx));
//            PyTuple_SetItem(result, 4, PyInt_FromLong(node->children.size()));
        }
    }

    if (error)
    {
        Py_XDECREF(result);
        return NULL;
    }

    return result;
}

static PyTypeObject NGramIterType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.NGramIter",             /*tp_name*/
    sizeof(NGramIter),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)NGramIter_dealloc, /*tp_dealloc*/
    0,                         /*tp_print*/
    0,                         /*tp_getattr*/
    0,                         /*tp_setattr*/
    0,                         /*tp_compare*/
    0,                         /*tp_repr*/
    0,                         /*tp_as_number*/
    0,                         /*tp_as_sequence*/
    0,                         /*tp_as_mapping*/
    0,                         /*tp_hash */
    0,                         /*tp_call*/
    0,                         /*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
    "NGramIter objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    NGramIter_iter,		               /* tp_iter */
    NGramIter_iternext,		               /* tp_iternext */
    0,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    0,             /* tp_new */
};



// Non-virtual helper class to protect the vtable of LanguageModelDynamic.
// The vtable pointer is located in the first 8(4) byte of the object
// however that is where python expects PyObject_HEAD to be and thus
// the vtable is destroyed when python touches the reference count.
// Wrapping LanguageModelDynamic in this class keeps the vtable safe.
class  PyLanguageModelDynamic
{
public:
    // python support
    PyObject_HEAD

    LanguageModelDynamic o;
    LanguageModelDynamic* operator->()
    {
        return &o;
    }
};


static PyObject *
LanguageModelDynamic_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyLanguageModelDynamic *self;

    self = (PyLanguageModelDynamic *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self = new(self) PyLanguageModelDynamic;   // placement new
    }
    return (PyObject *)self;
}

static int
LanguageModelDynamic_init(PyLanguageModelDynamic *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {(char*)"order", NULL};
    int n = 3;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|i", kwlist,
                                      &n))
        return -1;

    (*self)->set_order(n);

    return 0;
}


static void
LanguageModelDynamic_dealloc(PyLanguageModelDynamic* self)
{
    self->~PyLanguageModelDynamic();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

// Extracts wchar_t string from PyUnicodeObject.
// Allocates string through python memory manager, must call PyMem_Free() on it.
static wchar_t*
pyunicode_to_wstr(PyObject* object)
{
    if (PyUnicode_Check(object))
    {
        PyUnicodeObject* o = (PyUnicodeObject*) object;
        int size = PyUnicode_GET_SIZE(o);
        wchar_t* wstr = (wchar_t*) PyMem_Malloc(sizeof(wchar_t) * (size+1));
        if (PyUnicode_AsWideChar(o, wstr, size) < 0)
        {
            PyErr_SetString(PyExc_ValueError, "cannot convert to wide string");
            PyMem_Free(wstr);
            return NULL;
        }
        wstr[size] = 0;
        return wstr;
    }
    PyErr_SetString(PyExc_TypeError, "expected unicode object");
    return NULL;
}

void free_strings(wchar_t** words, int n)
{
    int i;
    if (words)
    {
        for(i=0; i<n; i++)
            if (words[i])
                PyMem_Free(words[i]);
        PyMem_Free(words);
    }
}

// Extracts array of wchar_t strings from a PySequence object.
// Allocates array through python memory manager, must call PyMem_Free() on it.
static wchar_t**
pyseqence_to_strings(PyObject* sequence, int* num_strings)
{
    int i, n;
    int error = 0;
    PyObject *item;
    wchar_t** strings = NULL;

    n = PySequence_Length(sequence);
    if (n > 0)
    {
        strings = (wchar_t**)PyMem_Malloc(sizeof(*strings) * n);
        if (!strings)
        {
            PyErr_SetString(PyExc_MemoryError, "failed to allocate strings");
            return NULL;
        }
        memset(strings, 0, sizeof(*strings) * n);

        for (i = 0; i < n; i++)
        {
            item = PySequence_GetItem(sequence, i);
            if (item == NULL)
            {
                PyErr_SetString(PyExc_ValueError, "bad item in sequence");
                error = 1;
                break;
            }
            if (!PyUnicode_Check(item))
            {
                PyErr_SetString(PyExc_ValueError, "item is not a unicode string");
                error = 1;
                break;
            }

            strings[i] = pyunicode_to_wstr(item);
            if (!strings[i])
            {
                error = 1;
                break;
            }

            Py_DECREF(item); /* Discard reference ownership */
        }
    }

    if (error)
    {
        free_strings(strings, n);
        return NULL;
    }

    *num_strings = n;
    return strings;
}


static PyObject *
LanguageModelDynamic_count_ngram(PyLanguageModelDynamic* self, PyObject* ngram)
{
    int n;
    wchar_t** words = pyseqence_to_strings(ngram, &n);
    if (!words)
        return NULL;

    (*self)->count_ngram(words, n);

    free_strings(words, n);

    Py_RETURN_NONE;
}

static PyObject *
LanguageModelDynamic_get_ngram_count(PyLanguageModelDynamic* self, PyObject* ngram)
{
    int n;
    wchar_t** words = pyseqence_to_strings(ngram, &n);
    if (!words)
        return NULL;

    int count = (*self)->get_ngram_count((const wchar_t**) words, n);
    PyObject* result = PyInt_FromLong(count);

    free_strings(words, n);

    return result;
}

static PyObject *
LanguageModelDynamic_clear(PyLanguageModelDynamic* self)
{
    (*self)->clear();
    Py_RETURN_NONE;
}

// predict returns a list of words
static PyObject *
LanguageModelDynamic_predict(PyLanguageModelDynamic* self, PyObject* args)
{
    int i, n;
    int error = 0;
    PyObject *result = NULL;
    PyObject *ocontext = NULL;
    wchar_t** context = NULL;
    int limit = -1;

    if (PyArg_ParseTuple(args, "O|I:predict", &ocontext, &limit))
    {
        context = pyseqence_to_strings(ocontext, &n);
        if (!context)
            return NULL;

        vector<LanguageModel::Result> results;
        (*self)->predict(context, n, limit,  results);

        // build return list
        result = PyList_New(results.size());
        if (!result)
        {
            PyErr_SetString(PyExc_MemoryError, "failed to allocate results list");
            error = 1;
        }
        else
        {
            for (i=0; i<(int)results.size(); i++)
            {
                const wchar_t* word = results[i].word;

                PyObject* oword  = PyUnicode_FromWideChar(word, wcslen(word));
                if (!oword)
                {
                    PyErr_SetString(PyExc_ValueError, "failed to create unicode string for return list");
                    error = 1;
                    Py_XDECREF(oword);
                    break;
                }
                PyList_SetItem(result, i, oword);
            }
        }

        free_strings(context, n);

        if (error)
        {
            Py_XDECREF(result);
            return NULL;
        }
    }
    return result;
}

// predictp returns a list of (word, probability) tuples
static PyObject *
LanguageModelDynamic_predictp(PyLanguageModelDynamic* self, PyObject* args)
{
    int i, n;
    int error = 0;
    PyObject *result = NULL;
    PyObject *ocontext = NULL;
    wchar_t** context = NULL;
    int limit = -1;

    if (PyArg_ParseTuple(args, "O|I:predictp", &ocontext, &limit))
    {
        context = pyseqence_to_strings(ocontext, &n);
        if (!context)
            return NULL;

        vector<LanguageModel::Result> results;
        (*self)->predict(context, n, limit,  results);

        // build return list
        result = PyList_New(results.size());
        if (!result)
        {
            PyErr_SetString(PyExc_MemoryError, "failed to allocate results list");
            error = 1;
        }
        else
        {
            for (i=0; i<(int)results.size(); i++)
            {
                double p = results[i].p;
                const wchar_t* word = results[i].word;

                PyObject* oword  = PyUnicode_FromWideChar(word, wcslen(word));
                if (!oword)
                {
                    PyErr_SetString(PyExc_ValueError, "failed to create unicode string for return list");
                    error = 1;
                    Py_XDECREF(oword);
                    break;
                }
                PyObject* op     = PyFloat_FromDouble(p);
                PyObject* otuple = PyTuple_New(2);
                PyTuple_SetItem(otuple, 0, oword);
                PyTuple_SetItem(otuple, 1, op);
                PyList_SetItem(result, i, otuple);
            }
        }

        free_strings(context, n);

        if (error)
        {
            Py_XDECREF(result);
            return NULL;
        }
    }
    return result;
}

// predictp returns a list of (word, probability) tuples
static PyObject *
LanguageModelDynamic_get_probability(PyLanguageModelDynamic* self, PyObject* args)
{
    int n;
    PyObject *result = NULL;
    PyObject *ongram = NULL;
    wchar_t** ngram = NULL;

    if (PyArg_ParseTuple(args, "O:get_probability", &ongram))
    {
        ngram = pyseqence_to_strings(ongram, &n);
        if (!ngram)
            return NULL;

        double p = (*self)->get_probability(ngram, n);
        result = PyFloat_FromDouble(p);

        free_strings(ngram, n);
    }
    return result;
}

static PyObject *
LanguageModelDynamic_set_order(PyLanguageModelDynamic *self, PyObject *args)
{
    int n = 3;

    if (! PyArg_ParseTuple(args, "i:set_order", &n))
        return NULL;

    (*self)->set_order(n);

    Py_RETURN_NONE;
}

static PyObject *
LanguageModelDynamic_load(PyLanguageModelDynamic *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:load", &filename))
        return NULL;

    int err = (*self)->load(filename);
    if(err)
    {
        char msg[128];
        snprintf(msg, ALEN(msg)-1, "loading failed (%d)", err);
        PyErr_SetString(PyExc_IOError, msg);
        return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *
LanguageModelDynamic_save(PyLanguageModelDynamic *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:save", &filename))
        return NULL;

    int err = (*self)->save(filename);
    if(err)
    {
        PyErr_SetString(PyExc_IOError, "saving failed");
        return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *
LanguageModelDynamic_memory_size(PyLanguageModelDynamic* self)
{
    // build return value
    PyObject* result = PyTuple_New(2);
    if (!result)
    {
        PyErr_SetString(PyExc_MemoryError, "failed to allocate tuple");
        return NULL;
    }
    PyTuple_SetItem(result, 0, PyInt_FromLong((*self)->dictionary.get_memory_size()));
    PyTuple_SetItem(result, 1, PyInt_FromLong((*self)->ngrams.get_memory_size()));

    return result;
}


static PyObject *
LanguageModelDynamic_iter_ngrams(PyLanguageModelDynamic *self)
{
    NGramIter* iter = PyObject_New(NGramIter, &NGramIterType);
    if (!iter)
        return NULL;
    iter = new(iter) NGramIter(&self->o, &(*self)->ngrams);   // placement new
    Py_INCREF(iter);

    #ifndef NDEBUG
    printf("LanguageModelDynamic_iter_ngrams: NGramIter=%p, ob_refcnt=%d\n", iter, (int)((PyObject*)iter)->ob_refcnt);
    #endif

    return (PyObject*) iter;
}

static PyObject *
LanguageModelDynamicget_order(PyLanguageModelDynamic *self, void *closure)
{
    return PyInt_FromLong((*self)->get_order());
}

static PyMemberDef LanguageModelDynamic_members[] = {
    {NULL}  /* Sentinel */
};

static PyGetSetDef LanguageModelDynamic_getseters[] = {
    {(char*)"order",
     (getter)LanguageModelDynamicget_order, NULL,
     (char*)"order of the language model",
     NULL},
    {NULL}  /* Sentinel */
};

static PyMethodDef LanguageModelDynamic_methods[] = {
    {"set_order", (PyCFunction)LanguageModelDynamic_set_order, METH_VARARGS,
     ""
    },
    {"count_ngram", (PyCFunction)LanguageModelDynamic_count_ngram, METH_O,
     ""
    },
    {"get_ngram_count", (PyCFunction)LanguageModelDynamic_get_ngram_count, METH_O,
     ""
    },
    {"iter_ngrams", (PyCFunction)LanguageModelDynamic_iter_ngrams, METH_NOARGS,
     ""
    },
    {"clear", (PyCFunction)LanguageModelDynamic_clear, METH_NOARGS,
     ""
    },
    {"predict", (PyCFunction)LanguageModelDynamic_predict, METH_VARARGS,
     ""
    },
    {"predictp", (PyCFunction)LanguageModelDynamic_predictp, METH_VARARGS,
     ""
    },
    {"get_probability", (PyCFunction)LanguageModelDynamic_get_probability, METH_VARARGS,
     ""
    },
    {"load", (PyCFunction)LanguageModelDynamic_load, METH_VARARGS,
     ""
    },
    {"save", (PyCFunction)LanguageModelDynamic_save, METH_VARARGS,
     ""
    },
    {"memory_size", (PyCFunction)LanguageModelDynamic_memory_size, METH_NOARGS,
     ""
    },
    {NULL}  /* Sentinel */
};

static PyTypeObject LanguageModelDynamicType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.LanguageModelDynamic",             /*tp_name*/
    sizeof(PyLanguageModelDynamic),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)LanguageModelDynamic_dealloc, /*tp_dealloc*/
    0,                         /*tp_print*/
    0,                         /*tp_getattr*/
    0,                         /*tp_setattr*/
    0,                         /*tp_compare*/
    0,                         /*tp_repr*/
    0,                         /*tp_as_number*/
    0,                         /*tp_as_sequence*/
    0,                         /*tp_as_mapping*/
    0,                         /*tp_hash */
    0,                         /*tp_call*/
    0,                         /*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
    "LanguageModelDynamic objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    LanguageModelDynamic_methods,     /* tp_methods */
    LanguageModelDynamic_members,     /* tp_members */
    LanguageModelDynamic_getseters,   /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    (initproc)LanguageModelDynamic_init,      /* tp_init */
    0,                         /* tp_alloc */
    LanguageModelDynamic_new,                 /* tp_new */
};

static PyMethodDef module_methods[] = {
    {NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
initlm(void)
{
    PyObject* m;

    if (PyType_Ready(&LanguageModelDynamicType) < 0)
        return;
    if (PyType_Ready(&NGramIterType) < 0)
        return;

    m = Py_InitModule3("lm", module_methods,
                 "Module for a dynamically updatable n-gram language model.");

    if (m == NULL)
      return;

    Py_INCREF(&LanguageModelDynamicType);
    PyModule_AddObject(m, "LanguageModelDynamic",
        (PyObject *)&LanguageModelDynamicType);
}

