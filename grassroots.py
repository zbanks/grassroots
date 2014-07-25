import collections
import json
import os
import time

from werkzeug.serving import run_simple
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import Request, Response
from werkzeug.wsgi import SharedDataMiddleware

class Field(object):
    def __init__(self, value=None):
        self.value = value

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.value

    def __set__(self, obj, value):
        self.value = value

    def parse(self, obj, data):
        self.value = data

    def export(self, obj):
        return self.value

class PropertyField(Field):
    """ Emulate property() behavior as a field """
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
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, data)

    def export(self, obj):
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)

class CallableField(Field):
    def __init__(self, fn):
        self.value = fn

    def parse(self, obj, data=None):
        # Call function on data
        if data is None:
            self.value(obj)
        elif isinstance(data, list):
            self.value(obj, *data)
        elif isinstance(data, dict):
            self.value(obj, **data)
        raise ValueError("Unable to call function. Argument must be a list, a dict, or None")

    def export(self, obj):
        # Nothing to export; Only callable
        return None

class JSONField(Field):
    pass

class BladeMeta(type):
    references = {}
    fields = {}
    actions = {}

    def __new__(meta, name, bases, dct):
        if name not in meta.references:
            meta.references[name] = {}
            meta.fields[name] = {}
            meta.actions[name] = {}

        for key, val in dct.items():
            if key.startswith("_"): # Skip _methods & __methods__
                continue
            if isinstance(val, Field):
                fcls, getter, setter = meta.fields[name].get(key, (None, None, None))
                meta.fields[name][key] = (val, getter, setter)

            prefix, _, rest = key.partition("_")
            if prefix == "get":
                # Field get
                fcls, getter, setter = meta.fields[name].get(rest, (None, None, None))
                meta.fields[name][rest] = (fcls, val, setter)
            elif prefix == "set":
                # Field set
                fcls, getter, setter = meta.fields[name].get(rest, (None, None, None))
                meta.fields[name][rest] = (fcls, getter, val)
            elif prefix == "call":
                # Action
                meta.actions[name][rest] = val

        return super(BladeMeta, meta).__new__(meta, name, bases, dct)

    def __init__(cls, name, bases, dct):
        super(BladeMeta, cls).__init__(name, bases, dct)

    def __call__(cls, *args, **kwargs):
        obj = super(BladeMeta, cls).__call__(*args, **kwargs)
        cls.references[obj.__class__.__name__][id(obj)] = obj
        return obj

class Blade(object):
    __metaclass__ = BladeMeta


class Root(object):
    def __init__(self):
        self.references = collections.defaultdict(dict)
        self.ordering = {}

        self.url_map = Map([
            Rule("/root/<classname>/<cid>", endpoint="object"),
            Rule("/root/<classname>", endpoint="class"),
            Rule("/root", endpoint="all")
        ])

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        adapter = self.url_map.bind_to_environ(environ)
        try:
            endpoint, values = adapter.match()
            try:
                json_resp = getattr(self, "app_" + endpoint)(request, **values)
            except Exception as e:
                json_resp = {"success": False, "error": str(e)}
                raise
        except:
            json_resp = {"success": False, "error": "404"}
            raise

        response = Response(json.dumps(json_resp), mimetype="application/json")

        return response(environ, start_response)

    def __call__(self, *args, **kwargs):
        return self.wsgi_app(*args, **kwargs)

    def app_object(self, request, classname, cid):
        cid = int(cid)
        if request.method == "GET":
            return self.dump(classname, cid)
        elif request.method == "POST":
            pass

    def app_class(self, reqeust, classname):
        return self.list_objects(classname)

    def app_all(self, request):
        return self.list_objects()

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
        for field, (fcls, getter, setter) in BladeMeta.fields[classname].items():
            if fcls is not None:
                #output[field] = fcls.to_native(obj)
                #output[field] = obj.__dict__[field].export()
                output[field] = fcls.export(obj)
            elif getter is not None:
                output[field] = getter(obj)
            elif setter is not None:
                output[field] = "<write_only>"
            else:
                continue
        for field, action in BladeMeta.actions[classname].items():
            if action is not None:
                output[field] = "<function>"
        output["_id"] = cid
        return output  
    
    def load(self, classname, cid, data):
        # Set the JSON that changed
        # cid = data["_id"] #???
        obj = self.references[classname][cid]
        for key, value in data.items():
            if key in BladeMeta.fields[classname]:
                fcls, getter, setter = BladeMeta.fields[classname][key]
                if fcls is not None:
                    #fcls.from_native(value)
                    #obj.__dict__[key].parse(vaLue)
                    fcls.parse(obj, value)
                elif setter is not None:
                    setter(obj, value)
            elif key in BladeMeta.actions[classname]:
                action = BladeMeta.actions[classname]
                action(obj, **value)

def run(app, host="127.0.0.1", port=8080):
    app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
        '/static': os.path.join(os.path.dirname(__file__), 'static')
    })
    run_simple(host, port, app, use_debugger=True, use_reloader=True)

class A(object):
    def __init__(self):
        self.a = 1
        self.b = 2

    def c(self):
        self.a = 0

    def d(self, d):
        self.b = d

    def eget(self):
        print "E", self._e
        return self._e
    
    def eset(self, _e):
        self._e = _e
    e = property(eget, eset)

class Timing(Blade):
    times = Field([])

    @CallableField
    def time(self):
        self.times.append(time.time())

    @PropertyField
    def deltas(self):
        self.times.append(time.time())
        return map(lambda x, y: x - y, self.times[:-1], self.times[1:])





if __name__ == "__main__":
    root = Root()
    tm = Timing()
    run(root)
