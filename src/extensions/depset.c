/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include "py24-compatibility.h"

// exceptions, loaded during initialization.
static PyObject *pkgcore_depset_ParseErrorExc = NULL;
static PyObject *pkgcore_depset_ValContains = NULL;
static PyObject *pkgcore_depset_PkgCond = NULL;
static PyObject *pkgcore_depset_PkgAnd = NULL;
static PyObject *pkgcore_depset_PkgOr = NULL;

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

void
_Err_SetParse(PyObject *dep_str, PyObject *msg, char *tok_start, char *tok_end)
{
    PyObject *ret;
    ret = PyObject_CallFunction(pkgcore_depset_ParseErrorExc, "S{sSss#}",
        dep_str, "msg", msg, "token", tok_start, tok_end - tok_start);
    if(ret) {
        PyErr_SetObject(pkgcore_depset_ParseErrorExc, ret);
        Py_DECREF(ret);
    }
}

void
Err_WrapException_SetParse(PyObject *dep_str, char *tok_start,
    char *tok_end)
{
    PyObject *type, *val, *tb;
    PyErr_Fetch(&type, &val, &tb);
    PyObject *res = PyObject_CallFunction(type, "O", val);
    if(res) {
        _Err_SetParse(dep_str, res, tok_start, tok_end);
        Py_DECREF(res);
    }
    Py_XDECREF(type);
    Py_XDECREF(val);
    Py_XDECREF(tb);
}

void
Err_SetParse(PyObject *dep_str, char *msg, char *tok_start, char *tok_end)
{
    PyObject *s = PyString_FromString(msg);
    if(!s)
        return
    _Err_SetParse(dep_str, s, tok_start, tok_end);
    Py_DECREF(s);
}

inline PyObject *
make_use_conditional(char *use_start, char *use_end, PyObject *payload)
{
    PyObject *val;
    if('!' == *use_start) {
        val = PyObject_CallFunction(pkgcore_depset_ValContains,
            "s#{ss#}", use_start + 1, use_end - use_start, "negate", Py_True);
    } else {
        val = PyObject_CallFunction(pkgcore_depset_ValContains, "s#",
            use_start, use_end - use_start);
    }
    if(!val)
        return (PyObject *)NULL;
    
    PyObject *restrict = PyObject_CallFunction(pkgcore_depset_PkgCond,
        "sOO", "use", val, payload);
    Py_DECREF(val);
    return restrict;
}

#define SKIP_SPACES(ptr)     \
while ('\t' == *(ptr) || ' ' == *(ptr) || '\n' == *(ptr)) (ptr)++;

#define SKIP_NONSPACES(ptr)                                                  \
while('\t' != *(ptr) && ' ' != *(ptr) && '\n' != *(ptr) && '\0' != *(ptr))  \
    (ptr)++;

#define ISSPACE(ptr) ('\t' == *(ptr) || ' ' == *(ptr) || '\n' == *(ptr))

PyObject *
internal_parse_depset(PyObject *dep_str, char **ptr, int *has_conditionals,
    PyObject *element_func, char enable_or, char initial_frame)
{
    char *start = *ptr;
    char *p = NULL;
    PyObject *restrictions = NULL;
    PyObject *item = NULL;
    PyObject *tmp = NULL;
    PyObject *kwds = NULL;
    #define PARSE_DEPSET_STACK_STORAGE 8
    PyObject *stack_restricts[PARSE_DEPSET_STACK_STORAGE];
    Py_ssize_t item_count = 0, tup_size = PARSE_DEPSET_STACK_STORAGE;

    SKIP_SPACES(start);
    p = start;
    while('\0' != *start) {
        start = p;
        SKIP_NONSPACES(p);
        if('(' == *start) {
            // new and frame.
            if(p - start != 1) {
                Err_SetParse(dep_str,
                    "either a space or end of string is required after (",
                    start, p);
                goto internal_parse_depset_error;
            }
            if(!(tmp = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, enable_or, 0)))
                goto internal_parse_depset_error;

            if(!(kwds = Py_BuildValue("{sO}", "finalize", Py_True))) {
                Py_DECREF(tmp);
                goto internal_parse_depset_error;
            }

            item = PyObject_Call(pkgcore_depset_PkgAnd, tmp, kwds);
            Py_DECREF(kwds);
            Py_DECREF(tmp);
            if(!item)
                goto internal_parse_depset_error;

            if(!PyTuple_Size(item)) {
                Py_DECREF(item);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;
            }

        } else if(')' == *start) {
            // end of a frame
            if(initial_frame) {
                Err_SetParse(dep_str, ") found without matching (",
                    NULL, NULL);
                goto internal_parse_depset_error;
            }
            if(p - start != 1) {
                Err_SetParse(dep_str,
                    "either a space or end of string is required after )",
                    start, p);
                goto internal_parse_depset_error;
            }
            if(*p)
                p++;
            break;

        } else if('?' == p[-1]) {
            // use conditional
            if (p - start == 1 || ('!' == *start && p - start == 2)) {
                Err_SetParse(dep_str, "empty use conditional", start, p);
                goto internal_parse_depset_error;
            }
            char *conditional_end = p - 1;
            SKIP_SPACES(p);
            if ('(' != *p || (!ISSPACE(p + 1) && '\0' != p[1])) {
                Err_SetParse(dep_str,
                    "( has to be the next token for a conditional",
                    start, p);
                goto internal_parse_depset_error;
            }
            p++;
            if(!(item = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, enable_or, 0)))
                goto internal_parse_depset_error;

            if(!PyTuple_Size(item)) {
                Py_DECREF(item);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;
            }

            if(!(kwds = Py_BuildValue("{sO}", "finalize", Py_True))) {
                Py_DECREF(item);
                goto internal_parse_depset_error;
            }
            tmp = PyObject_Call(pkgcore_depset_PkgAnd, item, kwds);
            Py_DECREF(kwds);
            Py_DECREF(item);
            if(!tmp)
                goto internal_parse_depset_error;
            
            item = make_use_conditional(start, conditional_end, tmp);
            Py_DECREF(tmp);
            if(!item)
                goto internal_parse_depset_error;
            *has_conditionals = 1;

        } else if ('|' == *start) {
            if('|' != p[1] || !enable_or) {
                Err_SetParse(dep_str, "stray |", NULL, NULL);
                goto internal_parse_depset_error;
            }
            p += 2;
            SKIP_SPACES(p);
            if ('(' != *p || (!ISSPACE(p + 1) && '\0' != p[1])) {
                Err_SetParse(dep_str,
                    "( has to be the next token for a conditional",
                    start, p);
                goto internal_parse_depset_error;
            }
            p++;
            if(!(tmp = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, enable_or, 0)))
                goto internal_parse_depset_error;
            
            if (!PyTuple_Size(tmp)) {
                Py_DECREF(tmp);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;
            }

            if(!(kwds = Py_BuildValue("{sO}", "finalize", Py_True))) {
                Py_DECREF(tmp);
                goto internal_parse_depset_error;
            }
            item = PyObject_Call(pkgcore_depset_PkgOr, tmp, kwds);
            Py_DECREF(kwds);
            Py_DECREF(tmp);
            if(!item)
                goto internal_parse_depset_error;

        } else {
            printf("item %i, '%s'\n", p - start, start);
            item = PyObject_CallFunction(element_func, "s#", start, p - start);
            if(!item)
                goto internal_parse_depset_error;
        }

        // append it.
        if(item_count == tup_size) {
            if(item_count == PARSE_DEPSET_STACK_STORAGE) {
                // switch over.
                restrictions = PyTuple_New(PARSE_DEPSET_STACK_STORAGE << 1);
                if(!restrictions) {
                    Py_DECREF(item);
                    goto internal_parse_depset_error;
                }
                for(item_count=0; item_count < PARSE_DEPSET_STACK_STORAGE;
                    item_count++) {
                    PyTuple_SET_ITEM(restrictions, item_count,
                        stack_restricts[item_count]);
                }
            } else if(_PyTuple_Resize(&restrictions, tup_size << 1)) {
                Py_DECREF(item);
                goto internal_parse_depset_error;
            }
            // now we're using restrictions.
        }
        if(restrictions) {
            PyTuple_SET_ITEM(restrictions, item_count, item);
        } else {
            stack_restricts[item_count] = item;
        }
        item_count++;
        start = p;
        SKIP_SPACES(p);
    }
    if(!restrictions) {
        restrictions = PyTuple_New(item_count);
        item_count--;
        while(item_count >= 0) {
            PyTuple_SET_ITEM(restrictions, item_count,
                stack_restricts[item_count]);
            item_count--;
        }
    } else if(item_count + 1 < tup_size) {
        if(_PyTuple_Resize(&restrictions, item_count))
            goto internal_parse_depset_error;
    }
    *ptr = p;
    return restrictions;
    
    internal_parse_depset_error:
    if(item_count) {
        if(!restrictions) {
            item_count--;
            while(item_count >= 0) {
                Py_DECREF(stack_restricts[item_count]);
                item_count--;
            }
        } else
            Py_DECREF(restrictions);
    }
    // dealloc.
    return (PyObject *)NULL;
}            

static PyObject *
pkgcore_parse_depset(PyObject *self, PyObject *args)
{
    PyObject *dep_str, *element_func;
    PyObject *disable_or = NULL;
    if(!PyArg_ParseTuple(args, "SO|O", &dep_str, &element_func, &disable_or))
        return (PyObject *)NULL;

    int enable_or, has_conditionals;

    if(!disable_or) {
        enable_or = 1;
    } else {
        enable_or = PyObject_IsTrue(disable_or);
        if(enable_or == -1)
            return (PyObject *)NULL;
    }
    char *p = PyString_AsString(dep_str);
    if(!p)
        return (PyObject *)NULL;
    return internal_parse_depset(dep_str, &p, &has_conditionals,
        element_func, enable_or, 1);
}

static PyMethodDef pkgcore_depset_methods[] = {
    {"parse_depset", (PyCFunction)pkgcore_parse_depset, METH_VARARGS,
        "initialize a depset instance"},
    {NULL}
};


PyDoc_STRVAR(
    pkgcore_depset_documentation,
    "cpython depset parsing functionality");


int
load_external_objects()
{
    PyObject *s, *m = NULL;
    #define LOAD_MODULE(module)         \
    s = PyString_FromString(module);    \
    if(!s)                              \
        return 1;                       \
    m = PyImport_Import(s);             \
    Py_DECREF(s);                       \
    if(!m)                              \
        return 1;
        
    if(!pkgcore_depset_ParseErrorExc) {
        LOAD_MODULE("pkgcore.ebuild.errors");
        pkgcore_depset_ParseErrorExc = PyObject_GetAttrString(m, 
            "ParseError");
        Py_DECREF(m);
        if(!pkgcore_depset_ParseErrorExc) {
            return 1;
        }
    }
    if(!pkgcore_depset_ValContains) {
        LOAD_MODULE("pkgcore.restrictions.values");
        pkgcore_depset_ValContains = PyObject_GetAttrString(m,
            "ContainmentMatch");
        Py_DECREF(m);
        if(!pkgcore_depset_ValContains)
            return 1;
    }
    if(!pkgcore_depset_PkgAnd || !pkgcore_depset_PkgOr || 
        !pkgcore_depset_PkgCond) {
        LOAD_MODULE("pkgcore.restrictions.packages");
    } else
        m = NULL;
        
    #undef LOAD_MODULE

    #define LOAD_ATTR(ptr, attr)                            \
    if(!(ptr)) {                                            \
        if(!((ptr) = PyObject_GetAttrString(m, (attr)))) {  \
            Py_DECREF(m);                                   \
            return 1;                                       \
        }                                                   \
    }
    LOAD_ATTR(pkgcore_depset_PkgAnd, "AndRestriction");
    LOAD_ATTR(pkgcore_depset_PkgOr, "OrRestriction");
    LOAD_ATTR(pkgcore_depset_PkgCond, "Conditional");
    #undef LOAD_ATTR

    Py_CLEAR(m);
    return 0;
}


PyMODINIT_FUNC
init_depset()
{
    // first get the exceptions we use.
    if(load_external_objects())
        return;
    
    Py_InitModule3("_depset", pkgcore_depset_methods,
        pkgcore_depset_documentation);
    
    if (PyErr_Occurred()) {
        Py_FatalError("can't initialize module _depset");
    }
}