import collections
import json
import logging
import os
import uuid

from werkzeug.exceptions import NotFound
from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
from werkzeug.wsgi import SharedDataMiddleware

__all__ = ("Field", "PropertyField", "CallableField", "JSONField", "Blade", "Root", "run")
#
# Fields. Expose values & functions over HTTP
# 

class Field(object):
    """Generic property field. Constructor argument is default value"""
    doc = "property"
    nested = False
    def __init__(self, value=None):
        self.value = value

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.value

    def __set__(self, obj, value):
        self.value = value

    def parse(self, obj, data):
        """Redefine `parse` to change the way the value is deserialized (from JSON)"""
        self.value = data

    def export(self, obj):
        """Redefine `export` to change the way the value is serialized (before being serialized to JSON)"""
        return self.value

class PropertyField(Field):
    """Emulate property() behavior as a field"""
    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        if doc is None and fget is not None:
            doc = fget.__doc__
        self.__doc__ = doc

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, value)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)

    def getter(self, fget):
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return type(self)(self.fget, self.fset, fdel, self.__doc__)

    def parse(self, obj, data):
        # Be a bit more leinient with what we accept here
        if self.fset is not None:
            self.fset(obj, data)

    def export(self, obj):
        # Be a bit more leinient with what we accept here
        if self.fget is not None:
            return self.fget(obj)

class CallableField(Field):
    """Turn a function into a (write-only) field
    
    If the field is 'set' to `v`, then the function is called using `v` for arguments.
    If `v` is None, the function is called without arguments.
    If `v` is a list (JSON Array), the function is called with positional arguments.
    If `v` is a dict (JSON Object), the function is called with keyword arguments.
    """
    doc = "callable"
    def __init__(self, fn):
        self.value = fn
        self.retval = None

    def parse(self, obj, data=None):
        # Call function on data
        # Save return value for next time it is exported
        if data is None:
            self.retval = self.value(obj)
        elif isinstance(data, list):
            self.retval = self.value(obj, *data)
        elif isinstance(data, dict):
            self.retval = self.value(obj, **data)
        else:
            raise ValueError("Unable to call function. Argument must be a list, a dict, or None")

    def export(self, obj):
        # Export the last return value from the called function
        # This is a little awkward, but it works
        # XXX: Should the retval be destroyed on read?
        return self.retval

class JSONField(Field):
    """Property field that serializes value with JSON."""
    pass

class ProxyField(Field):
    """ This might not be nessassary..."""
    def parse(self, obj, data=None):
        self.value = self.value.parse(obj, data=data)

    def export(self, obj):
        return self.value.export(obj)

class BladeListField(Field):
    """Field that is a list of Blades of a particular type"""
    doc = "property-nested"
    def __init__(self, bladecls):
        self.bladecls = bladecls
        self.value = []

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.value

    def __set__(self, obj, value):
        if not all([type(v).__name__ == self.bladecls for v in value]):
            raise ValueError
        self.value = value

    def parse(self, obj, data):
        self.value = [self.meta.references[self.bladecls][v] for v in data]

    def export(self, obj):
        return {"__class__": self.bladecls, "__data__": map(id, self.value)}

class BladeDictField(Field):
    """Field that is a dict of Blades of a particular type"""
    doc = "property-nested"
    def __init__(self, bladecls):
        self.bladecls = bladecls
        self.value = {}

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.value

    def __set__(self, obj, value):
        if not all([type(v).__name__ == self.bladecls for v in value.values()]):
            raise ValueError
        self.value = value

    def parse(self, obj, data):
        self.value = {k: self.meta.references[self.bladecls][v] for k, v in data.items()}

    def export(self, obj):
        return {"__class__": self.bladecls, "__data__": {k: id(v) for k, v in self.value.items()}}


class BladeMeta(type):
    """Metaclass which keeps track of Fields to expose over HTTP"""
    fields = {}
    references = {}
    abstracts = {"Blade"}

    def __new__(meta, name, bases, dct):
        if name not in meta.abstracts:
            if name not in meta.references:
                meta.fields[name] = {}
                meta.references[name] = {}

            for key, val in dct.items():
                if isinstance(val, Field):
                    val.meta = meta
                    meta.fields[name][key] = val

        return super(BladeMeta, meta).__new__(meta, name, bases, dct)

    def __init__(cls, name, bases, dct):
        super(BladeMeta, cls).__init__(name, bases, dct)

    def __call__(cls, *args, **kwargs):
        obj = super(BladeMeta, cls).__call__(*args, **kwargs)
        #TODO: is there a better way of getting this?
        classname = obj.__class__.__name__
        if classname not in cls.abstracts:
            cls.references[classname][id(obj)] = obj
        return obj

class Blade(object):
    """Subclass this to export Fields"""
    __metaclass__ = BladeMeta

class Root(object):
    """Webserver """
    def __init__(self):
        self.references = collections.defaultdict(dict)
        self.ordering = {}
        self.uuid = uuid.uuid4() #TODO: is this the right kind?

        self.url_map = Map([
            Rule("/root/<classname>/<cid>", endpoint="object"),
            Rule("/root/<classname>", endpoint="class"),
            Rule("/root", endpoint="all")
        ])

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        adapter = self.url_map.bind_to_environ(environ)
        try:
            try:
                endpoint, values = adapter.match()
            except NotFound:
                return ""
            try:
                json_resp = getattr(self, "app_" + endpoint)(request, **values)
            except Exception as e:
                # TODO: clean up error handling
                json_resp = {"success": False, "error": str(e)}
                raise
        except:
            json_resp = {"success": False, "error": "404"}
            raise

        headers = {"X-Server-UUID": self.uuid}

        response = Response(json.dumps(json_resp), mimetype="application/json", headers=headers)

        return response(environ, start_response)

    def __call__(self, *args, **kwargs):
        return self.wsgi_app(*args, **kwargs)

    def app_object(self, request, classname, cid):
        cid = int(cid)
        if request.method == "GET":
            return self.dump(classname, cid)
        elif request.method in {"POST", "PUT"}:
            try:
                data = json.loads(request.data)
            except ValueError:
                print "Error parsing data"
                raise
            return self.load(classname, cid, data)

    def app_class(self, request, classname):
        return self.list_objects(classname)

    def app_all(self, request):
        # Discovery 
        output = {}
        for classname, fields in BladeMeta.fields.items():
            output[classname] = {f: d.doc for f, d in fields.items()}
        return output

    def list_objects(self, classname=None):
        if classname is None:
            #return {clk : clv.keys() for clk, clv in self.references.items()}
            #return [{"type": clk, "objects": clv.keys()} for clk, clv in self.references.items()]
            return [clk for clk, clv in BladeMeta.references.items()]
        else:
            #return {cid : self.dump(classname, cid) for cid in self.references[classname]}
            return [self.dump(classname, cid) for cid in BladeMeta.references[classname]]

    def dump(self, classname, cid):
        # Return a JSONable representation of an object
        output = {}
        #for key, value in self.references[classname][cid].__dict__.items():
        obj = BladeMeta.references[classname][cid]
        for fieldname, field in BladeMeta.fields[classname].items():
            output[fieldname] = field.export(obj)
        output["_id"] = cid
        return output  
    
    def load(self, classname, cid, data):
        # Set the JSON that changed
        # cid = data["_id"] #???
        obj = BladeMeta.references[classname][cid]
        print 'data', data
        print 'bm', BladeMeta.fields[classname]
        for key, value in data.items():
            if key in BladeMeta.fields[classname]:
                field = BladeMeta.fields[classname][key]
                field.parse(obj, value)
        return self.dump(classname, cid)

def run(app, host="127.0.0.1", port=8080):
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.CRITICAL)
    app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
        #'/static': os.path.join(os.path.dirname(__file__), 'static')
        '/static': os.path.abspath('static')
    })
    run_simple(host, port, app, use_debugger=True, use_reloader=False)


