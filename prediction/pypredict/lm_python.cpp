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

import pypredict
model = pypredict.DynamicModel()

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
#include <string>

#include "lm_dynamic.h"
#include "lm_merged.h"

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

// Non-virtual helper class to protect the vtable of LanguageModels.
// The vtable pointer is located in the first 8(4) byte of the object
// however that is where python expects PyObject_HEAD to be and thus
// the vtable is destroyed when python touches the reference count.
// Wrapping LanguageModels in this class keeps the vtable safe.
template <class T>
class  PyWrapper
{
    public:
        PyWrapper()
        {
            o = new T;
        }
        ~PyWrapper()
        {
            delete o;
        }
        T* operator->()
        {
            return o;
        }

        // python support
        PyObject_HEAD
        T* o;
};

typedef PyWrapper<LanguageModel> PyLanguageModel;
typedef PyWrapper<LanguageModelDynamic> PyDynamicModel;
typedef PyWrapper<LanguageModelCache> PyCacheModel;

// Another, derived wrapper to encapsulate python reference handling
// of a vector of LanguageModels.
template <class T>
class  PyMergedModelWrapper : public PyWrapper<T>
{
    public:
        PyMergedModelWrapper(const vector<PyLanguageModel*>& models)
        {
            // extract the c++ language models
            vector<LanguageModel*> cmodels;
            for (int i=0; i<(int)models.size(); i++)
            {
                cmodels.push_back(models[i]->o);
                Py_INCREF(models[i]);  // don't let the python objects go away
            }
            (*this)->set_models(cmodels);  // class T must be of type MergedModel

            // store python objects so we can later decrement their refcounts
            references = models;
        }

        ~PyMergedModelWrapper()
        {
            // let go of the python objects now
            for (int i=0; i<(int)references.size(); i++)
                Py_DECREF(references[i]);
        }

        vector<PyLanguageModel*> references;
};

typedef PyMergedModelWrapper<OverlayModel> PyOverlayModel;
typedef PyMergedModelWrapper<LinintModel> PyLinintModel;
typedef PyMergedModelWrapper<LoglinintModel> PyLoglinintModel;


//------------------------------------------------------------------------
// python helper functions
//------------------------------------------------------------------------

// Extract wchar_t string from PyUnicodeObject.
// Allocates string through python memory manager, call PyMem_Free() when done.
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

// free an array of unicode strings
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
// Somewhat redundant as there is now a vector<> version doing the same below.
static wchar_t**
pyseqence_to_strings(PyObject* sequence, int* num_elements)
{
    int i;
    int n = 0;
    int error = 0;
    PyObject *item;
    wchar_t** strings = NULL;

    if (!PySequence_Check(sequence))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
    }
    else
    {
        n = PySequence_Length(sequence);
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

    *num_elements = n;
    return strings;
}


// free a vector of unicode strings
void free_strings(vector<wchar_t*>& strings)
{
    vector<wchar_t*>::iterator it;
    for(it=strings.begin(); it!=strings.end(); it++)
        PyMem_Free(*it);
}

// Extracts vector of wchar_t strings from a PySequence object.
static bool
pyseqence_to_strings(PyObject* sequence, vector<wchar_t*>& strings)
{
    int i;
    int n = 0;
    int error = 0;
    PyObject *item;

    if (!PySequence_Check(sequence))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
        return false;
    }
    else
    {
        n = PySequence_Length(sequence);
        strings.reserve(n);

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
            wchar_t* s = pyunicode_to_wstr(item);
            if (!s)
            {
                error = 1;
                break;
            }
            strings.push_back(s);

            Py_DECREF(item); /* Discard reference ownership */
        }
    }

    if (error)
    {
        free_strings(strings);
        return false;
    }

    return true;
}

static bool
pyseqence_to_doubles(PyObject* sequence, vector<double>& results)
{
    if (!PySequence_Check(sequence))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
        return false;
    }
    else
    {
        int n = PySequence_Length(sequence);
        for (int i = 0; i < n; i++)
        {
            PyObject* item = PySequence_GetItem(sequence, i);
            if (item == NULL)
            {
                PyErr_SetString(PyExc_ValueError, "bad item in sequence");
                return false;
            }

            results.push_back(PyFloat_AsDouble(item));

            Py_DECREF(item); /* Discard reference ownership */
        }
    }

    return true;
}

template <class T, class PYTYPE>
static bool
pyseqence_to_objects(PyObject* sequence, vector<T*>& results, PYTYPE* type)
{
    int i;
    int n = 0;
    PyObject *item;

    if (!PySequence_Check(sequence))
    {
        PyErr_SetString(PyExc_ValueError, "expected sequence type");
        return false;
    }
    else
    {
        n = PySequence_Length(sequence);
        for (i = 0; i < n; i++)
        {
            item = PySequence_GetItem(sequence, i);
            if (item == NULL)
            {
                PyErr_SetString(PyExc_ValueError, "bad item in sequence");
                return false;
            }
            if (!PyObject_TypeCheck(item, type))
            {
                PyErr_SetString(PyExc_ValueError,
                                      "unexpected item type in sequence");
                return false;
            }

            results.push_back(((T*)item));

            Py_DECREF(item); /* Discard reference ownership */
        }
    }

    return true;
}

//------------------------------------------------------------------------
// LanguageModel - python interface for LanguageModel
//------------------------------------------------------------------------
// abstract class, can't get instatiated

static PyObject *
LanguageModel_clear(PyLanguageModel* self)
{
    (*self)->clear();
    Py_RETURN_NONE;
}

// predict returns a list of words
static PyObject *
LanguageModel_predict(PyLanguageModel* self, PyObject* args)
{
    int i;
    int error = 0;
    PyObject *result = NULL;
    PyObject *ocontext = NULL;
    vector<wchar_t*> context;
    int limit = -1;
    bool filter_control_words = true;

    if (PyArg_ParseTuple(args, "O|IB:predict", &ocontext, &limit,
                                               &filter_control_words))
    {
        if (!pyseqence_to_strings(ocontext, context))
            return NULL;

        vector<LanguageModel::Result> results;
        (*self)->predict(results, context, limit, filter_control_words);

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

        free_strings(context);

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
LanguageModel_predictp(PyLanguageModel* self, PyObject* args)
{
    int i;
    int error = 0;
    PyObject *result = NULL;
    PyObject *ocontext = NULL;
    vector<wchar_t*> context;
    int limit = -1;
    bool filter_control_words = true;

    if (PyArg_ParseTuple(args, "O|IB:predictp", &ocontext, &limit,
                                                &filter_control_words))
    {
        if (!pyseqence_to_strings(ocontext, context))
            return NULL;
        vector<LanguageModel::Result> results;
        (*self)->predict(results, context, limit, filter_control_words);

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

        free_strings(context);

        if (error)
        {
            Py_XDECREF(result);
            return NULL;
        }
    }
    return result;
}

static PyObject *
LanguageModel_get_probability(PyLanguageModel* self, PyObject* args)
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
LanguageModel_load(PyLanguageModel *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:load", &filename))
        return NULL;

    int err = (*self)->load(filename);
    if(err)
    {
//        char msg[128];
//        snprintf(msg, ALEN(msg)-1, "loading failed (%d)", err);
//        PyErr_SetString(PyExc_IOError, msg);
        PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);
        return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *
LanguageModel_save(PyLanguageModel *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:save", &filename))
        return NULL;

    int err = (*self)->save(filename);
    if(err)
    {
        PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);
        return NULL;
    }

    Py_RETURN_NONE;
}


static PyMethodDef LanguageModel_methods[] = {
    {"clear", (PyCFunction)LanguageModel_clear, METH_NOARGS,
     ""
    },
    {"predict", (PyCFunction)LanguageModel_predict, METH_VARARGS,
     ""
    },
    {"predictp", (PyCFunction)LanguageModel_predictp, METH_VARARGS,
     ""
    },
    {"get_probability", (PyCFunction)LanguageModel_get_probability, METH_VARARGS,
     ""
    },
    {"load", (PyCFunction)LanguageModel_load, METH_VARARGS,
     ""
    },
    {"save", (PyCFunction)LanguageModel_save, METH_VARARGS,
     ""
    },
    {NULL}  /* Sentinel */
};

static PyTypeObject LanguageModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.LanguageModel",             /*tp_name*/
    sizeof(PyLanguageModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    0, /*tp_dealloc*/
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
    "LanguageModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    LanguageModel_methods,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    0                 /* tp_new */
};


//------------------------------------------------------------------------
// NGramIter - python iterator object for traversal of the n-gram trie
//------------------------------------------------------------------------

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
                // python semantics: first item _after_ initial next()
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

        LanguageModelDynamic* lm;
        TrieNode* root;
        TrieRoot::iterator it;
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
    return self;  // python iterator interface: iter() on iterators returns self
}

static PyObject *
NGramIter_iternext(PyObject *self)
{
    int i;
    int error = 0;
    PyObject *result = NULL;

    NGramIter* iter = (NGramIter*) self;

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
        PyObject *ongram = PyTuple_New(ngram.size());
        for (i=0; i<(int)ngram.size(); i++)
        {
            PyObject* oword = NULL;
            wchar_t* word = iter->lm->dictionary.id_to_word(ngram[i]);
            if (word)
            {
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

//------------------------------------------------------------------------
// DynamicModel - python interface for LanguageModelDynamic
//------------------------------------------------------------------------

static PyObject *
DynamicModel_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyDynamicModel *self;

    self = (PyDynamicModel *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self = new(self) PyDynamicModel;   // placement new
    }
    return (PyObject *)self;
}

static int
DynamicModel_init(PyDynamicModel *self, PyObject *args, PyObject *kwds)
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
DynamicModel_dealloc(PyDynamicModel* self)
{
    self->~PyDynamicModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyObject *
DynamicModel_count_ngram(PyDynamicModel* self, PyObject* args)
{
    PyObject* ngram = NULL;
    int increment = 1;
    bool allow_new_words = true;

    if (! PyArg_ParseTuple(args, "O|IB:count_ngram",
              &ngram, &increment, &allow_new_words))
        return NULL;

    vector<wchar_t*> words;
    if (!pyseqence_to_strings(ngram, words))
        return NULL;

    (*self)->count_ngram(&words[0], words.size(), increment, allow_new_words);

    free_strings(words);

    Py_RETURN_NONE;
}

static PyObject *
DynamicModel_get_ngram_count(PyDynamicModel* self, PyObject* ngram)
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
DynamicModel_memory_size(PyDynamicModel* self)
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

// returns an object implementing pythons iterator interface
static PyObject *
DynamicModel_iter_ngrams(PyDynamicModel *self)
{
    NGramIter* iter = PyObject_New(NGramIter, &NGramIterType);
    if (!iter)
        return NULL;
    iter = new(iter) NGramIter(self->o, &(*self)->ngrams);   // placement new
    Py_INCREF(iter);

    #ifndef NDEBUG
    printf("DynamicModel_iter_ngrams: NGramIter=%p, ob_refcnt=%d\n", iter, (int)((PyObject*)iter)->ob_refcnt);
    #endif

    return (PyObject*) iter;
}

static PyObject *
DynamicModel_get_order(PyDynamicModel *self, void *closure)
{
    return PyInt_FromLong((*self)->get_order());
}

static PyObject *
DynamicModel_set_order(PyDynamicModel *self, PyObject *args)
{
    int n = 3;

    if (! PyArg_ParseTuple(args, "i:set_order", &n))
        return NULL;

    (*self)->set_order(n);

    Py_RETURN_NONE;
}

static PyMemberDef DynamicModel_members[] = {
    {NULL}  /* Sentinel */
};

static PyGetSetDef DynamicModel_getseters[] = {
    {(char*)"order",
     (getter)DynamicModel_get_order, NULL,
     (char*)"order of the language model",
     NULL},
    {NULL}  /* Sentinel */
};

static PyMethodDef DynamicModel_methods[] = {
    {"set_order", (PyCFunction)DynamicModel_set_order, METH_VARARGS,
     ""
    },
    {"count_ngram", (PyCFunction)DynamicModel_count_ngram, METH_VARARGS,
     ""
    },
    {"get_ngram_count", (PyCFunction)DynamicModel_get_ngram_count, METH_O,
     ""
    },
    {"iter_ngrams", (PyCFunction)DynamicModel_iter_ngrams, METH_NOARGS,
     ""
    },
    {"memory_size", (PyCFunction)DynamicModel_memory_size, METH_NOARGS,
     ""
    },
    {NULL}  /* Sentinel */
};

static PyTypeObject DynamicModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.DynamicModel",             /*tp_name*/
    sizeof(PyDynamicModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)DynamicModel_dealloc, /*tp_dealloc*/
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
    "DynamicModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    DynamicModel_methods,     /* tp_methods */
    DynamicModel_members,     /* tp_members */
    DynamicModel_getseters,   /* tp_getset */
    &LanguageModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    (initproc)DynamicModel_init,      /* tp_init */
    0,                         /* tp_alloc */
    DynamicModel_new,                 /* tp_new */
};



//------------------------------------------------------------------------
// CacheModel - python interface for LanguageModelCache
//------------------------------------------------------------------------

static PyObject *
CacheModel_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyCacheModel *self;

    self = (PyCacheModel *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self = new(self) PyCacheModel;   // placement new
    }
    return (PyObject *)self;
}

static int
CacheModel_init(PyCacheModel *self, PyObject *args, PyObject *kwds)
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
CacheModel_dealloc(PyCacheModel* self)
{
    self->~PyCacheModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyMethodDef CacheModel_methods[] = {
    {"predict", (PyCFunction)LanguageModel_predict, METH_VARARGS,
     ""
    },
    {NULL}  /* Sentinel */
};

static PyTypeObject CacheModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.CacheModel",             /*tp_name*/
    sizeof(PyCacheModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)CacheModel_dealloc, /*tp_dealloc*/
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
    "CacheModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    CacheModel_methods,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    &LanguageModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    (initproc)CacheModel_init,      /* tp_init */
    0,                         /* tp_alloc */
    CacheModel_new,                 /* tp_new */
};

//------------------------------------------------------------------------
// OverlayModel - python interface for OverlayModel
//------------------------------------------------------------------------

static void
OverlayModel_dealloc(PyOverlayModel* self)
{
    self->~PyOverlayModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyMethodDef OverlayModel_methods[] = {
    {NULL}  /* Sentinel */
};

static PyTypeObject OverlayModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.OverlayModel",             /*tp_name*/
    sizeof(PyOverlayModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)OverlayModel_dealloc, /*tp_dealloc*/
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
    "OverlayModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    OverlayModel_methods,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    &LanguageModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    0,                 /* tp_new */
};

//------------------------------------------------------------------------
// LinintModel - python interface for LinintModel
//------------------------------------------------------------------------

static void
LinintModel_dealloc(PyLinintModel* self)
{
    self->~PyLinintModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyMethodDef LinintModel_methods[] = {
    {NULL}  /* Sentinel */
};

static PyTypeObject LinintModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.LinintModel",             /*tp_name*/
    sizeof(PyLinintModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)LinintModel_dealloc, /*tp_dealloc*/
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
    "LinintModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    LinintModel_methods,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    &LanguageModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    0,                 /* tp_new */
};

//------------------------------------------------------------------------
// LoglinintModel - python interface for LoglinintModel
//------------------------------------------------------------------------

static void
LoglinintModel_dealloc(PyLoglinintModel* self)
{
    self->~PyLoglinintModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyMethodDef LoglinintModel_methods[] = {
    {NULL}  /* Sentinel */
};

static PyTypeObject LoglinintModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.LoglinintModel",             /*tp_name*/
    sizeof(PyLoglinintModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)LoglinintModel_dealloc, /*tp_dealloc*/
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
    "LoglinintModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    LoglinintModel_methods,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    &LanguageModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    0,                 /* tp_new */
};


//------------------------------------------------------------------------
// more python helper functions, depending on LanguageModelType
//------------------------------------------------------------------------

static bool
parse_params(const char* func_name, PyDynamicModel *self, PyObject* args,
             vector<PyLanguageModel*>& models)
{
    PyObject *omodels = NULL;
    string format = "O:" + string(func_name);
    if (PyArg_ParseTuple(args, format.c_str(), &omodels))
    {
        if (!pyseqence_to_objects(omodels, models, &LanguageModelType))
        {
            PyErr_SetString(PyExc_ValueError, "list of LanguageModels expected");
            return false;
        }
    }
    return true;
}

static bool
parse_params(const char* func_name, PyDynamicModel *self, PyObject* args,
             vector<PyLanguageModel*>& models, vector<double>& weights)
{
    PyObject *omodels = NULL;
    PyObject *oweights = NULL;
    string format = "O|O:" + string(func_name);
    if (PyArg_ParseTuple(args, format.c_str(), &omodels, &oweights))
    {
        if (!pyseqence_to_objects(omodels, models, &LanguageModelType))
        {
            PyErr_SetString(PyExc_ValueError, "list of LanguageModels expected");
            return false;
        }
        if (oweights)  // optional parameter
        {
            if (!pyseqence_to_doubles(oweights, weights))
            {
                PyErr_SetString(PyExc_ValueError, "list of numbers expected");
                return false;
            }
        }
    }
    return true;
}


//------------------------------------------------------------------------
// Module methods
//------------------------------------------------------------------------

static PyObject *
overlay(PyDynamicModel *self, PyObject* args)
{
    vector<PyLanguageModel*> models;
    if (!parse_params("overlay", self, args, models))
        return NULL;

    PyOverlayModel* model = PyObject_New(PyOverlayModel, &OverlayModelType);
    if (!model)
        return NULL;

    model = new(model) PyOverlayModel(models);   // placement new
    Py_INCREF(model);

    return (PyObject*) model;
}

static PyObject *
linint(PyDynamicModel *self, PyObject* args)
{
    vector<PyLanguageModel*> models;
    vector<double> weights;
    if (!parse_params("linint", self, args, models, weights))
        return NULL;

    PyLinintModel* model = PyObject_New(PyLinintModel, &LinintModelType);
    if (!model)
        return NULL;

    model = new(model) PyLinintModel(models);   // placement new
    (*model)->set_weights(weights);
    Py_INCREF(model);

    return (PyObject*) model;
}

static PyObject *
loglinint(PyDynamicModel *self, PyObject* args)
{
    vector<PyLanguageModel*> models;
    vector<double> weights;
    if (!parse_params("loglinint", self, args,  models, weights))
        return NULL;

    PyLoglinintModel* model = PyObject_New(PyLoglinintModel,
                                           &LoglinintModelType);
    if (!model)
        return NULL;

    model = new(model) PyLoglinintModel(models);   // placement new
    (*model)->set_weights(weights);
    Py_INCREF(model);

    return (PyObject*) model;
}

static PyMethodDef module_methods[] = {
    {"overlay", (PyCFunction)overlay, METH_VARARGS,
     ""
    },
    {"linint", (PyCFunction)linint, METH_VARARGS,
     ""
    },
    {"loglinint", (PyCFunction)loglinint, METH_VARARGS,
     ""
    },
    {NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
initlm(void)
{
    PyObject* m;

    // Announce all type objects ever used here
    // or face weird crashes deep in python when
    // trying to access them anyway.
    if (PyType_Ready(&NGramIterType) < 0)
        return;
    if (PyType_Ready(&LanguageModelType) < 0)
        return;
    if (PyType_Ready(&DynamicModelType) < 0)
        return;
    if (PyType_Ready(&CacheModelType) < 0)
        return;
    if (PyType_Ready(&OverlayModelType) < 0)
        return;
    if (PyType_Ready(&LinintModelType) < 0)
        return;
    if (PyType_Ready(&LoglinintModelType) < 0)
        return;

    m = Py_InitModule3("lm", module_methods,
                 "Module for a dynamically updatable n-gram language model.");

    if (m == NULL)
      return;

    // add only types here that are allowed to be instantiated from python
    Py_INCREF(&DynamicModelType);
    PyModule_AddObject(m, "DynamicModel",
        (PyObject *)&DynamicModelType);
    Py_INCREF(&CacheModelType);
    PyModule_AddObject(m, "CacheModel",
        (PyObject *)&CacheModelType);
}

