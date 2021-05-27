import pickle
import shelve
from shelve import Shelf
from typing import Any, Callable, Type

from cachetools import Cache


class DelMixin:
    """ Mixin that calls a callback after each call to the `__delitem__()` function. """

    def __init__(self, delete_callback: Callable[[str], Any], *args, **kwargs):
        self.delete_callback = delete_callback
        super().__init__(*args, **kwargs)  # type: ignore

    def __delitem__(self, key):
        super().__delitem__(key)
        self.delete_callback(key)


class PersistentCache:
    """Behaves like a subclass of `cachetools.Cache`, but keeps a persistent copy
    of the cache on disk.

    The persistent copy is lazily instantiated at the first access to an attribute
    of the underlying cache.

    The persistent copy is updated after every write (add or delete item).

    If items in the cache are modified without re-adding them to the dict, the
    persistent cache will not be updated.

    Persistency can be deactivated by providing `None` as the filename.

    Internally, the `shelve` library is used to implement the cache.

    Parameters
    ----------
    wrapped_cache_cls: subclass of `Cache`
        the class of the cache that this PersistentCache should mimic.
    filename: str or None
        filename for the persistent cache. A file extension may be appended. See
        `shelve.open()` for more information. If `None`, persistency is deactivated.
    *args:
        forwarded to the init function of `wrapped_cache_cls`
    *kwargs:
        forwarded to the init function of `wrapped_cache_cls`
    """

    def __init__(self, wrapped_cache_cls: Type[Cache], filename: str, *args, **kwargs):
        new_cls = type(
            f"Wrapped{wrapped_cache_cls.__name__}", (DelMixin, wrapped_cache_cls), {}
        )
        if filename:
            self.wrapped = new_cls(self.delete_callback, *args, **kwargs)
        else:
            # no persistency, hence no callback needed
            self.wrapped = wrapped_cache_cls(*args, **kwargs)
        self.filename = filename
        self.persistent_dict: Shelf = None

    def delete_callback(self, key):
        """ Called when an item is deleted from the wrapped cache """
        self.initialize_if_not_initialized()
        hkey = self.hash_key(key)
        del self.persistent_dict[hkey]

    @staticmethod
    def hash_key(key):
        return str(hash(key))

    def __setitem__(self, key, value):
        self.initialize_if_not_initialized()
        self.wrapped[key] = value
        hkey = self.hash_key(key)
        if self.persistent_dict is not None:
            self.persistent_dict[hkey] = (key, value)
            self.persistent_dict.sync()

    def __getitem__(self, item):
        self.initialize_if_not_initialized()
        return self.wrapped[item]

    def __getattr__(self, item):
        self.initialize_if_not_initialized()
        return getattr(self.wrapped, item)

    def __contains__(self, item):
        self.initialize_if_not_initialized()
        return self.wrapped.__contains__(item)

    def initialize_if_not_initialized(self):
        if self.filename and self.persistent_dict is None:
            self.persistent_dict = shelve.open(
                self.filename, protocol=pickle.HIGHEST_PROTOCOL
            )
            for hk, (k, v) in self.persistent_dict.items():
                self.wrapped[k] = v

    def close(self):
        if self.persistent_dict is not None:
            self.persistent_dict.close()
            self.persistent_dict = None

    def __del__(self):
        """Try to tidy up.

        This is just for show since we sync the dict after every change anyway."""
        try:
            self.persistent_dict.close()
            self.persistent_dict = None
        except Exception:
            pass
