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
#include "lm_dynamic_kn.h"
#include "lm_dynamic_cached.h"
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
typedef PyWrapper<DynamicModel> PyDynamicModel;
typedef PyWrapper<DynamicModelKN> PyDynamicModelKN;
typedef PyWrapper<CachedDynamicModel> PyCachedDynamicModel;

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

bool check_error(const LanguageModel::Error err, const char* filename = NULL)
{
//        char msg[128];
//        snprintf(msg, ALEN(msg)-1, "loading failed (%d)", err);
//        PyErr_SetString(PyExc_IOError, msg);
    if (!err)
        return false;

    string filestr = (filename ? string(" in '") + filename + "'" : "");
    switch(err)
    {
        case LanguageModel::ERR_NONE:
            break;
        case LanguageModel::ERR_NOT_IMPL:
            PyErr_SetString(PyExc_NotImplementedError, "Not implemented");
            break;
        case LanguageModel::ERR_FILE:
            if (filename)
                PyErr_SetFromErrnoWithFilename(PyExc_IOError,
                                               const_cast<char*>(filename));
            else
                PyErr_SetFromErrno(PyExc_IOError);
            break;
        case LanguageModel::ERR_MEMORY:
            PyErr_SetString(PyExc_MemoryError, "Out of memory");
            break;
        default:
        {
            string msg;
            switch (err)
            {
                case LanguageModel::ERR_NUMTOKENS:
                    msg = "too few tokens"; break;
                case LanguageModel::ERR_ORDER:
                    msg = "unexpected ngram order"; break;
                case LanguageModel::ERR_COUNT:
                    msg = "ngram count mismatch"; break;
                case LanguageModel::ERR_UNEXPECTED_EOF:
                    msg = "unexpected end of file"; break;
                default:
                    PyErr_SetString(PyExc_ValueError, "Unknown Error");
                    return true;
            }

            PyErr_Format(PyExc_IOError,
                     "Bad file format, %s%s",
                      msg.c_str(), filestr.c_str());
        }
    }
    return true;
}

static PyObject *
predict(PyLanguageModel* self, PyObject* args, PyObject *kwds,
        bool with_probs = false)
{
    int i;
    int error = 0;
    PyObject *result = NULL;
    PyObject *ocontext = NULL;
    vector<wchar_t*> context;
    int limit = -1;
    bool filter_control_words = true;

    // Default to not do explicit normalization for performance reasons.
    // Often results will be implicitely normalized anyway and predictions
    // for word choices just need the correct word order.
    // Normalization must be enabled for entropy/perplexity calculations or
    // other verification purposes.
    bool normalize = false;

    static char *kwlist[] = {(char*)"context",
                             (char*)"limit",
                             (char*)"filter",
                             (char*)"normalize", NULL};
    if (PyArg_ParseTupleAndKeywords(args, kwds, "O|IBB:predict", kwlist,
                                    &ocontext,
                                    &limit,
                                    &filter_control_words,
                                    &normalize))
    {
        if (!pyseqence_to_strings(ocontext, context))
            return NULL;

        uint32_t options = LanguageModel::SORT |
              (filter_control_words ? LanguageModel::FILTER_CONTROL_WORDS : 0) |
              (normalize ? LanguageModel::NORMALIZE : 0);

        vector<LanguageModel::Result> results;
        (*self)->predict(results, context, limit, options);

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
                if (with_probs)
                {
                    double p = results[i].p;
                    PyObject* op     = PyFloat_FromDouble(p);
                    PyObject* otuple = PyTuple_New(2);
                    PyTuple_SetItem(otuple, 0, oword);
                    PyTuple_SetItem(otuple, 1, op);
                    PyList_SetItem(result, i, otuple);
                }
                else
                {
                    PyList_SetItem(result, i, oword);
                }
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
LanguageModel_clear(PyLanguageModel* self)
{
    (*self)->clear();
    Py_RETURN_NONE;
}

// predict returns a list of words
static PyObject *
LanguageModel_predict(PyLanguageModel* self, PyObject* args, PyObject* kwds)
{
    return predict(self, args, kwds);
}

// predictp returns a list of (word, probability) tuples
static PyObject *
LanguageModel_predictp(PyLanguageModel* self, PyObject* args, PyObject* kwds)
{
    return predict(self, args, kwds, true);
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
LanguageModel_lookup_word(PyDynamicModel* self, PyObject* value)
{
    wchar_t* word = pyunicode_to_wstr(value);
    if (!word)
        return NULL;

    int result = (*self)->lookup_word(word);

    if (word)
        PyMem_Free(word);

    return PyInt_FromLong(result);
}

static PyObject *
LanguageModel_load(PyLanguageModel *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:load", &filename))
        return NULL;

    if (check_error((*self)->load(filename), filename))
        return NULL;

    Py_RETURN_NONE;
}

static PyObject *
LanguageModel_save(PyLanguageModel *self, PyObject *args)
{
    char* filename = NULL;

    if (!PyArg_ParseTuple(args, "s:save", &filename))
        return NULL;

    if (check_error((*self)->save(filename), filename))
        return NULL;

    Py_RETURN_NONE;
}


static PyMethodDef LanguageModel_methods[] = {
    {"clear", (PyCFunction)LanguageModel_clear, METH_NOARGS,
     ""
    },
    {"predict", (PyCFunction)LanguageModel_predict, METH_KEYWORDS,
     ""
    },
    {"predictp", (PyCFunction)LanguageModel_predictp, METH_KEYWORDS,
     ""
    },
    {"get_probability", (PyCFunction)LanguageModel_get_probability, METH_VARARGS,
     ""
    },
    {"lookup_word", (PyCFunction)LanguageModel_lookup_word, METH_O,
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
        NGramIter(DynamicModelBase* lm)
        {
            this->lm = lm;
            it = lm->ngrams_begin();
            first_time = true;
        }
        ~NGramIter()
        {
            delete it;
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
                    (*it)++;
            } while (it->at_root());
            return *(*it);
        }

        void get_ngram(vector<WordId>& ngram)
        {
            it->get_ngram(ngram);
        }

    public:
        PyObject_HEAD

        DynamicModelBase* lm;
        DynamicModelBase::ngrams_iter* it;
        bool first_time;
};

//typedef NGramIter<DynamicModel> DynamicModel;
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

    vector<int> values;
    iter->lm->get_node_values(node, ngram.size(), values);

    // build return value

    result = PyTuple_New(1+values.size());
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
            for (int i=0; i<(int)values.size(); i++)
                PyTuple_SetItem(result, 1+i, PyInt_FromLong(values[i]));
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
    //(destructor)(deallocfunc)NGramIter_dealloc<DynamicModel>(), /*tp_dealloc*/
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
// DynamicModel - python interface for DynamicModel
//------------------------------------------------------------------------

bool set_order(PyDynamicModel *self, int order)
{
    if (order < 2)
    {
        PyErr_SetString(PyExc_ValueError, "DynamicModel doesn't support orders less than 2");
        return false;
    }

    (*self)->set_order(order);

    return true;
}

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
    int order = 3;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|i", kwlist,
                                      &order))
        return -1;

    if (!set_order(self, order))
        return -1;


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

    if (!(*self)->count_ngram(&words[0], words.size(),
                              increment, allow_new_words))
    {
        PyErr_SetString(PyExc_MemoryError, "out of memory");
        return NULL;
    }

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
    vector<long> values;
    (*self)->get_memory_sizes(values);

    PyObject* result = PyTuple_New(values.size());
    if (!result)
    {
        PyErr_SetString(PyExc_MemoryError, "failed to allocate tuple");
        return NULL;
    }
    for (int i=0; i<(int)values.size(); i++)
        PyTuple_SetItem(result, i, PyInt_FromLong(values[i]));

    return result;
}

// returns an object implementing pythons iterator interface
static PyObject *
DynamicModel_iter_ngrams(PyDynamicModel *self)
{
    NGramIter* iter = PyObject_New(NGramIter, &NGramIterType);
    if (!iter)
        return NULL;
    iter = new(iter) NGramIter(self->o);   // placement new
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

static int
DynamicModel_set_order(PyDynamicModel *self, PyObject *value, void *closure)
{
    int order = (int) PyInt_AsLong(value);
    if (order == -1)
    {
        PyErr_SetString(PyExc_TypeError, "The value must be an integer");
        return -1;
    }

    if (!set_order(self, order))
        return NULL;

    return 0;
}

static struct
{
    const char* short_short_name;
    const char* short_name;
    const char* name;
    Smoothing id;
} smoothing_table[] =
{
    {"j", "jm", "jelinek-mercer", JELINEK_MERCER_I},
    {"w", "wb", "witten-bell", WITTEN_BELL_I},
    {"d", "ad", "abs-disc", ABS_DISC_I},
    {"k", "kn", "kneser-ney", KNESER_NEY_I},
    {NULL, 0}
};

const char* smoothing_to_string(Smoothing smoothing)
{
    for (int i=0; i<ALEN(smoothing_table); i++)
        if(smoothing == smoothing_table[i].id)
            return smoothing_table[i].name;
    return NULL;
}

Smoothing pystring_to_smoothing(PyObject *value)
{
    Smoothing sm = SMOOTHING_NONE;
    if (value != NULL)
    {
        if (!PyString_Check(value))
        {
            PyErr_SetString(PyExc_TypeError, "string value expected");
            return SMOOTHING_NONE;
        }
        char* s = PyString_AsString(value);
        int i;
        for (i=0; i<ALEN(smoothing_table); i++)
        {
            if(strcmp(smoothing_table[i].short_short_name, s) == 0)
            {
                sm = smoothing_table[i].id;
                break;
            }
            if(strcmp(smoothing_table[i].short_name, s) == 0)
            {
                sm = smoothing_table[i].id;
                break;
            }
            if(strcmp(smoothing_table[i].name, s) == 0)
            {
                sm = smoothing_table[i].id;
                break;
            }
        }
        if (i >= ALEN(smoothing_table))
        {
            PyErr_SetString(PyExc_ValueError, "invalid smoothing option");
            return SMOOTHING_NONE;
        }
    }
    return sm;
}

static PyObject *
DynamicModel_get_smoothing(PyDynamicModel *self, void *closure)
{
    const char* s = smoothing_to_string((*self)->get_smoothing());
    if (s)
        return PyString_FromString(s);
    Py_RETURN_NONE;
}

static int
DynamicModel_set_smoothing(PyDynamicModel *self, PyObject *value, void *closure)
{
    Smoothing sm = pystring_to_smoothing(value);
    if (!sm)
        return -1;

    vector<Smoothing> smoothings = (*self)->get_smoothings();
    if (!count(smoothings.begin(), smoothings.end(), sm))
    {
        PyErr_SetString(PyExc_ValueError, "unsupported smoothing option, "
                                          "try a different model type");
        return -1;
    }

    (*self)->set_smoothing(sm);

    return 0;
}


static PyMemberDef DynamicModel_members[] = {
    {NULL}  /* Sentinel */
};

static PyGetSetDef DynamicModel_getsetters[] = {
    {(char*)"order",
     (getter)DynamicModel_get_order, (setter)DynamicModel_set_order,
     (char*)"order of the language model",
     NULL},
    {(char*)"smoothing",
     (getter)DynamicModel_get_smoothing, (setter)DynamicModel_set_smoothing,
     (char*)"ngram smoothing: 'witten-bell' (default) or 'kneser-ney'",
     NULL},
    {NULL}  /* Sentinel */
};

static PyMethodDef DynamicModel_methods[] = {
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
    DynamicModel_getsetters,   /* tp_getset */
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
// DynamicModelKN - python interface for DynamicModelKN
//------------------------------------------------------------------------

static PyObject *
DynamicModelKN_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyDynamicModelKN *self;

    self = (PyDynamicModelKN*)type->tp_alloc(type, 0);
    if (self != NULL) {
        self = new(self) PyDynamicModelKN;   // placement new
    }
    return (PyObject *)self;
}

static void
DynamicModelKN_dealloc(PyDynamicModelKN* self)
{
    self->~PyDynamicModelKN();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyTypeObject DynamicModelKNType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.DynamicModelKN",             /*tp_name*/
    sizeof(PyDynamicModelKN),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)DynamicModelKN_dealloc, /*tp_dealloc*/
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
    "DynamicModelKN objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    0,     /* tp_methods */
    0,     /* tp_members */
    0,   /* tp_getset */
    &DynamicModelType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    DynamicModelKN_new,                 /* tp_new */
};


//------------------------------------------------------------------------
// CachedDynamicModel - python interface for CachedDynamicModel
//------------------------------------------------------------------------

static PyObject *
CachedDynamicModel_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyCachedDynamicModel *self;

    self = (PyCachedDynamicModel*)type->tp_alloc(type, 0);
    if (self != NULL) {
        self = new(self) PyCachedDynamicModel;   // placement new
    }
    return (PyObject *)self;
}

static void
CachedDynamicModel_dealloc(PyCachedDynamicModel* self)
{
    self->~PyCachedDynamicModel();   // call destructor
    self->ob_type->tp_free((PyObject*)self);
}

static PyObject *
CachedDynamicModel_get_recency_halflife(PyCachedDynamicModel *self, void *closure)
{
    return PyInt_FromLong((*self)->get_recency_halflife());
}

static int
CachedDynamicModel_set_recency_halflife(PyCachedDynamicModel *self, PyObject *value, void *closure)
{
    if (!PyInt_Check(value))
    {
        PyErr_SetString(PyExc_TypeError, "integer value expected");
        return -1;
    }

    long halflife = PyInt_AsLong(value);
    if (halflife <= 0)
    {
        PyErr_SetString(PyExc_ValueError,
                         "The value must be greater than zero");
        return -1;
    }

    (*self)->set_recency_halflife(halflife);

    return 0;
}

static PyObject *
CachedDynamicModel_get_recency_lambdas(PyCachedDynamicModel *self, void *closure)
{
    vector<double> lambdas;
    (*self)->get_recency_lambdas(lambdas);

    PyObject* otuple = PyTuple_New(lambdas.size());
    for (int i = 0; i<(int)lambdas.size(); i++)
        PyTuple_SetItem(otuple, i, PyFloat_FromDouble(lambdas[i]));
    return otuple;
}

static int
CachedDynamicModel_set_recency_lambdas(PyCachedDynamicModel *self, PyObject *value, void *closure)
{
    vector<double> lambdas;
    if (!pyseqence_to_doubles(value, lambdas))
    {
        PyErr_SetString(PyExc_ValueError, "list of numbers expected");
        return false;
    }

    (*self)->set_recency_lambdas(lambdas);

    return 0;
}

static PyObject *
CachedDynamicModel_get_recency_ratio(PyCachedDynamicModel *self, void *closure)
{
    return PyFloat_FromDouble((*self)->get_recency_ratio());
}

static int
CachedDynamicModel_set_recency_ratio(PyCachedDynamicModel *self, PyObject *value, void *closure)
{
    double recency_ratio = PyFloat_AsDouble(value);
    if (recency_ratio < 0.0 && recency_ratio > 1.0)
    {
        PyErr_SetString(PyExc_ValueError, "The value must be in the range [0..1]");
        return -1;
    }

    (*self)->set_recency_ratio(recency_ratio);

    return 0;
}

static PyObject *
CachedDynamicModel_get_recency_smoothing(PyCachedDynamicModel *self, void *closure)
{
    const char* s = smoothing_to_string((*self)->get_recency_smoothing());
    if (s)
        return PyString_FromString(s);
    Py_RETURN_NONE;
}

static int
CachedDynamicModel_set_recency_smoothing(PyCachedDynamicModel *self, PyObject *value, void *closure)
{
    Smoothing sm = pystring_to_smoothing(value);
    if (!sm)
        return -1;

    vector<Smoothing> smoothings = (*self)->get_recency_smoothings();
    if (!count(smoothings.begin(), smoothings.end(), sm))
    {
        PyErr_SetString(PyExc_ValueError, "unsupported smoothing option, "
                                          "try a different model type");
        return -1;
    }

    (*self)->set_recency_smoothing(sm);

    return 0;
}

static PyGetSetDef CachedDynamicModel_getsetters[] = {
    {(char*)"recency_halflife",
     (getter)CachedDynamicModel_get_recency_halflife, (setter)CachedDynamicModel_set_recency_halflife,
     (char*)"halflife of exponential falloff in number of recently used words"
            " until w=0.5",
     NULL},
    {(char*)"recency_lambdas",
     (getter)CachedDynamicModel_get_recency_lambdas, (setter)CachedDynamicModel_set_recency_lambdas,
     (char*)"jelinec-mercer smoothing weights, one per order",
     NULL},
    {(char*)"recency_ratio",
     (getter)CachedDynamicModel_get_recency_ratio, (setter)CachedDynamicModel_set_recency_ratio,
     (char*)"ratio of recency-based to count-based probabilities",
     NULL},
    {(char*)"recency_smoothing",
     (getter)CachedDynamicModel_get_recency_smoothing, (setter)CachedDynamicModel_set_recency_smoothing,
     (char*)"ngram recency smoothing: "
            "'jelinec-mercer' (default) or 'witten-bell'",
     NULL},
    {NULL}  /* Sentinel */
};

static PyTypeObject CachedDynamicModelType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "lm.CachedDynamicModel",             /*tp_name*/
    sizeof(PyCachedDynamicModel),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)CachedDynamicModel_dealloc, /*tp_dealloc*/
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
    "CachedDynamicModel objects",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    0,     /* tp_methods */
    0,     /* tp_members */
    CachedDynamicModel_getsetters,   /* tp_getset */
    &DynamicModelKNType,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    0,      /* tp_init */
    0,                         /* tp_alloc */
    CachedDynamicModel_new,                 /* tp_new */
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
    if (PyType_Ready(&DynamicModelKNType) < 0)
        return;
    if (PyType_Ready(&CachedDynamicModelType) < 0)
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
    PyModule_AddObject(m, "DynamicModel", (PyObject *)&DynamicModelType);
    Py_INCREF(&DynamicModelType);
    PyModule_AddObject(m, "DynamicModelKN", (PyObject *)&DynamicModelKNType);
    Py_INCREF(&CachedDynamicModelType);
    PyModule_AddObject(m, "CachedDynamicModel", (PyObject *)&CachedDynamicModelType);
}

