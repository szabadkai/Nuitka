#     Copyright 2018, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Yield related codes.

The normal "yield", and the Python 3.3 or higher "yield from" variant.
"""

from nuitka import Options

from .CodeHelpers import generateChildExpressionsCode
from .ErrorCodes import getErrorExitCode
from .PythonAPICodes import getReferenceExportCode


def _getYieldPreserveCode(to_name, value_name, preserve_exception, yield_code,
                          emit, context):
    yield_return_label = context.allocateLabel("yield_return")
    yield_return_index = yield_return_label.split('_')[-1]

    locals_preserved = context.variable_storage.getLocalPreservationDeclarations()

    # Need not preserve it, if we are not going to use it for the purpose
    # of releasing it.
    if not context.needsCleanup(value_name):
        locals_preserved.remove(value_name)

    # Target name is not assigned, no need to preserve it.
    if to_name in locals_preserved:
        locals_preserved.remove(to_name)

    if locals_preserved:
        yield_tmp_storage = context.variable_storage.getVariableDeclarationTop("yield_tmps")

        if yield_tmp_storage is None:
            yield_tmp_storage = context.variable_storage.addVariableDeclarationTop(
                "char[1024]",
                "yield_tmps",
                None
            )

        emit(
            "Nuitka_PreserveHeap( %s, %s, NULL );" % (
                yield_tmp_storage,
                ", ".join(
                    "&%s, sizeof(%s)" % (
                        local_preserved,
                        local_preserved.c_type
                    )
                    for local_preserved in
                    locals_preserved

                )
            )
        )

    if preserve_exception:
        emit("SAVE_GENERATOR_EXCEPTION( generator );")

    emit(
        """\
%(context_object_name)s->m_yield_return_index = %(yield_return_index)s;""" % {
                "context_object_name" : context.getContextObjectName(),
                "yield_return_index"  : yield_return_index,
        }
    )

    emit(yield_code)

    emit(
        "%(yield_return_label)s:" % {
            "yield_return_label"  : yield_return_label,
        }
    )

    if locals_preserved:
        emit(
            "Nuitka_RestoreHeap( %s, %s, NULL );" % (
                yield_tmp_storage,
                ", ".join(
                    "&%s, sizeof(%s)" % (
                        local_preserved,
                        local_preserved.c_type
                    )
                    for local_preserved in
                    locals_preserved

                )
            )
        )

    emit(
        "%(to_name)s = yield_return_value;" % {
            "to_name" : to_name
        }
    )

    if preserve_exception:
        emit("RESTORE_GENERATOR_EXCEPTION( generator );")


def generateYieldCode(to_name, expression, emit, context):
    value_name, = generateChildExpressionsCode(
        expression = expression,
        emit       = emit,
        context    = context
    )

    # In handlers, we must preserve/restore the exception.
    preserve_exception = expression.isExceptionPreserving()

    getReferenceExportCode(value_name, emit, context)
    if context.needsCleanup(value_name):
        context.removeCleanupTempName(value_name)

    if Options.isExperimental("generator_goto"):
        yield_code = "return %(yielded_value)s;" % {
            "yielded_value"       : value_name,
        }

        _getYieldPreserveCode(
            to_name            = to_name,
            value_name         = value_name,
            yield_code         = yield_code,
            preserve_exception = preserve_exception,
            emit               = emit,
            context            = context
        )
    else:
        # This will produce GENERATOR_YIELD, COROUTINE_YIELD or ASYNCGEN_YIELD.
        emit(
            "%s = %s_%s( %s, %s );" % (
                to_name,
                context.getContextObjectName().upper(),
                "YIELD"
                  if not preserve_exception else
                "YIELD_IN_HANDLER",
                context.getContextObjectName(),
                value_name
            )
        )


    getErrorExitCode(
        check_name = to_name,
        emit       = emit,
        context    = context
    )

    # Comes as only borrowed.
    # context.addCleanupTempName(to_name)


def generateYieldFromCode(to_name, expression, emit, context):
    value_name, = generateChildExpressionsCode(
        expression = expression,
        emit       = emit,
        context    = context
    )

    # In handlers, we must preserve/restore the exception.
    preserve_exception = expression.isExceptionPreserving()

    # This will produce GENERATOR_YIELD_FROM, COROUTINE_YIELD_FROM or
    # ASYNCGEN_YIELD_FROM.
    getReferenceExportCode(value_name, emit, context)

    if Options.isExperimental("generator_goto"):
        if context.needsCleanup(value_name):
            context.removeCleanupTempName(value_name)
        yield_code = """\
generator->m_yieldfrom = %(yield_from)s;
return NULL;
""" % {
            "yield_from"       : value_name,
        }

        _getYieldPreserveCode(
            to_name            = to_name,
            value_name         = value_name,
            yield_code         = yield_code,
            preserve_exception = preserve_exception,
            emit               = emit,
            context            = context
        )

        getErrorExitCode(
            check_name = to_name,
            emit       = emit,
            context    = context
        )
    else:
        if not context.needsCleanup(value_name):
            context.addCleanupTempName(value_name)

        emit(
            "%s = %s_%s( %s, %s );" % (
                to_name,
                context.getContextObjectName().upper(),
                "YIELD_FROM"
                  if not preserve_exception else
                "YIELD_FROM_IN_HANDLER",
                context.getContextObjectName(),
                value_name
            )
        )

        getErrorExitCode(
            check_name   = to_name,
            release_name = value_name,
            emit         = emit,
            context      = context
        )

    context.addCleanupTempName(to_name)
