# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
operation templates for package/repository/data source objects

For new format implementations, new formats, and generally any new extension,
an operation class will likely have to be defined.  While the implementations
are a bit repetitive, the design of it is intentional to ensure that any derivative
will be forced to adhere to the pkgcore internal api.

Basically it's a crappy form of zope interfaces; converting to zope.interfaces may
occur down the line if dependencies can be kept as minimal as possible.
"""

from snakeoil import klass

class base(object):

    __required__ = frozenset()

    UNSUPPORTED = object()

    def __init__(self, disable_overrides=(), enable_overrides=()):
        self._force_disabled = frozenset(disable_overrides)
        self._force_enabled = frozenset(enable_overrides)
        self._setup_api()

    def _get_observer(self, observer=None):
        return observer

    @klass.cached_property
    def raw_operations(self):
        return frozenset(x[len("_cmd_api_"):] for x in dir(self.__class__)
            if x.startswith("_cmd_api_"))

    @klass.cached_property
    def enabled_operations(self):
        enabled_ops = set(self._filter_disabled_commands(self.raw_operations))
        return frozenset(self._apply_overrides(enabled_ops))

    def _apply_overrides(self, ops):
        ops.update(self._force_enabled)
        ops.difference_update(self._force_disabled)
        return ops

    def _setup_api(self):
        for op in self.enabled_operations:
            setattr(self, op,
                getattr(self, '_cmd_api_%s' % op))

    def _filter_disabled_commands(self, sequence):
        for command in sequence:
            obj = getattr(self, '_cmd_api_%s' % command, None)
            if not getattr(obj, '_is_standalone', False):
                if not hasattr(self, '_cmd_implementation_%s' % command):
                    continue
            check_f = getattr(self, '_cmd_check_support_%s' % command, None)
            if check_f is not None and not check_f():
                continue
            yield command

    def supports(self, operation_name=None, raw=False):
        if not operation_name:
            if not raw:
                return self.enabled_operations
            return self.raw_operations
        if raw:
            return operation_name in self.raw_operations
        return operation_name in self.enabled_operations

    def run_if_supported(self, operation_name, *args, **kwds):
        """invoke an operation if it's supported

        :param operation_name: operation to run if supported
        :param args: positional args passed to the operation
        :param kwds: optional args passed to the operation
        :keyword or_return: if the operation isn't supported, return this
            (if unspecified, it returns :obj:`base.UNSUPPORTED`)
        :return: Either the value of or_return, or if the operation is
            supported, the return value from that operation
        """
        ret = kwds.pop("or_return", self.UNSUPPORTED)
        if self.supports(operation_name):
            ret = getattr(self, operation_name)(*args, **kwds)
        return ret


def is_standalone(functor):
    """decorator to mark a api operation method as containing the implementation

    This is primarily useful for commands that can contain all of the logic in
    the template class itself, rather than requiring a glue method to be provided
    """
    functor._is_standalone = True
    return functor
