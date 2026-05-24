# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: nonecheck=False
# cython: initializedcheck=False
# cython: cdivision=True
# cython: overflowcheck=False
# cython: always_failsafe=False
# WriterAgent - Cython accelerator for serialization packing.

import array
from libc.math cimport NAN as c_nan
from cpython.object cimport PyObject
from cpython.list cimport PyList_GET_ITEM, PyList_GET_SIZE
from cpython.float cimport PyFloat_AsDouble, PyFloat_Check
from cpython.long cimport PyLong_AsLong, PyLong_Check
from cpython.bool cimport PyBool_Check
from cpython.exc cimport PyErr_Occurred, PyErr_Clear

cdef extern from "Python.h":
    int PyObject_TypeCheck(object, PyObject*)
    object PyObject_Str(object)
    int PyUnicode_Check(object)

def fast_flatten_grid_2d(list grid, int ncols):
    """
    Cython-accelerated 2D grid flattening.
    Returns (buffer_bytes, strings, column_states, column_has_none, has_non_numeric)
    """
    cdef int nrows = PyList_GET_SIZE(grid)
    cdef int ncells = nrows * ncols
    
    # We use a double array for the buffer
    import array
    cdef object buf = array.array('d', [0.0] * ncells)
    cdef double[:] buf_view = buf
    
    cdef dict strings = {}
    cdef list column_states = [0] * ncols
    cdef list column_has_none = [False] * ncols
    cdef bint has_non_numeric = False
    
    cdef int r, c, idx = 0
    cdef object row, val
    cdef double fval
    cdef int st
    
    for r in range(nrows):
        row = <object>PyList_GET_ITEM(grid, r)
        if PyList_GET_SIZE(row) != ncols:
            raise ValueError(f"Uneven row lengths in data grid at row {r}")
            
        for c in range(ncols):
            val = <object>PyList_GET_ITEM(row, c)
            
            if val is None:
                buf_view[idx] = c_nan
                column_has_none[c] = True
            elif PyUnicode_Check(val):
                has_non_numeric = True
                buf_view[idx] = c_nan
                strings[idx] = val
            else:
                # Try to get as double (robust against numpy scalars)
                fval = PyFloat_AsDouble(val)
                if fval == -1.0 and PyErr_Occurred():
                    PyErr_Clear()
                    # Truly non-numeric
                    has_non_numeric = True
                    buf_view[idx] = c_nan
                    strings[idx] = val if PyUnicode_Check(val) else PyObject_Str(val)
                else:
                    buf_view[idx] = fval
                    # Determine state for column_states
                    st = <int>column_states[c]
                    if st != 3:
                        if PyFloat_Check(val):
                            column_states[c] = 3
                        elif PyBool_Check(val):
                            if st == 0:
                                column_states[c] = 1
                        elif PyLong_Check(val):
                            if st < 2:
                                column_states[c] = 2
                        else:
                            # Robust check for numpy scalars or other numeric types
                            dtype = getattr(val, "dtype", None)
                            if dtype is not None:
                                kind = getattr(dtype, "kind", None)
                                if kind == "f":
                                    column_states[c] = 3
                                elif kind == "i" or kind == "u":
                                    if st < 2:
                                        column_states[c] = 2
                                elif kind == "b":
                                    if st == 0:
                                        column_states[c] = 1
                                else:
                                    # unknown numeric type, fallback to float
                                    column_states[c] = 3
                            else:
                                # unknown numeric type, fallback to float
                                column_states[c] = 3
            
            idx += 1
            
    return buf, strings, column_states, column_has_none, has_non_numeric

def fast_flatten_grid_1d(list grid):
    """
    Cython-accelerated 1D grid flattening.
    Returns (buffer_bytes, strings, column_states, column_has_none, has_non_numeric)
    """
    cdef int ncells = PyList_GET_SIZE(grid)
    
    # We use a double array for the buffer
    import array
    cdef object buf = array.array('d', [0.0] * ncells)
    cdef double[:] buf_view = buf
    
    cdef dict strings = {}
    cdef list column_states = [0]
    cdef list column_has_none = [False]
    cdef bint has_non_numeric = False
    
    cdef int idx = 0
    cdef object val
    cdef double fval
    cdef int st
    
    for idx in range(ncells):
        val = <object>PyList_GET_ITEM(grid, idx)
        
        if val is None:
            buf_view[idx] = c_nan
            column_has_none[0] = True
        elif PyUnicode_Check(val):
            has_non_numeric = True
            buf_view[idx] = c_nan
            strings[idx] = val
        else:
            # Try to get as double (robust against numpy scalars)
            fval = PyFloat_AsDouble(val)
            if fval == -1.0 and PyErr_Occurred():
                PyErr_Clear()
                # Truly non-numeric
                has_non_numeric = True
                buf_view[idx] = c_nan
                strings[idx] = val if PyUnicode_Check(val) else PyObject_Str(val)
            else:
                buf_view[idx] = fval
                # Determine state for column_states
                st = <int>column_states[0]
                if st != 3:
                    if PyFloat_Check(val):
                        column_states[0] = 3
                    elif PyBool_Check(val):
                        if st == 0:
                            column_states[0] = 1
                    elif PyLong_Check(val):
                        if st < 2:
                            column_states[0] = 2
                    else:
                        # Robust check for numpy scalars or other numeric types
                        dtype = getattr(val, "dtype", None)
                        if dtype is not None:
                            kind = getattr(dtype, "kind", None)
                            if kind == "f":
                                column_states[0] = 3
                            elif kind == "i" or kind == "u":
                                if st < 2:
                                    column_states[0] = 2
                            elif kind == "b":
                                if st == 0:
                                    column_states[0] = 1
                            else:
                                # unknown numeric type, fallback to float
                                column_states[0] = 3
                        else:
                            # unknown numeric type, fallback to float
                            column_states[0] = 3
            
    return buf, strings, column_states, column_has_none, has_non_numeric
