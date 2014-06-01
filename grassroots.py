import collections
import json
import os

from werkzeug.serving import run_simple
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import Request, Response
from werkzeug.wsgi import SharedDataMiddleware

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
        except:
            json_resp = {"success": False, "error": "404"}
            raise

        response = Response(json.dumps(json_resp), mimetype="application/json")

        return response(environ, start_response)

    def __call__(self, *args, **kwargs):
        return self.wsgi_app(*args, **kwargs)

    def app_object(self, request, classname, cid):
        if request.method == "GET":
            return self.dump(classname, cid)
        elif request.method == "POST":
            pass

    def app_class(self, reqeust, classname):
        return self.list_objects(classname)

    def app_all(self, request):
        return self.list_objects()
    
    def expose(self, obj, classname=None, cid=None):
        # Expose an object 
        if classname is None:
            classname = obj.__class__.__name__

        if cid is None:
            # The id is the objects location in memory -- is this a little insecure/sketchy?
            cid = id(obj)

        self.references[classname][cid] = obj

    def list_objects(self, classname=None):
        if classname is None:
            return {clk : clv.keys() for clk, clv in self.references.items()}
        else:
            return {cid : self.dump(classname, cid) for cid in self.references[classname]}

    def dump(self, classname, cid):
        # Return a JSONable representation of an object
        output = {}
        for key, value in self.references[classname][cid].__dict__.items():
            try:
                json.dumps(value)
            except TypeError:
                continue # Unserializable
            output[key] = value
        return output  
    
    def load(self, classname, cid, data):
        # Set the JSON that changed
        # cid = data["_id"] #???
        obj = self.references[classname][cid]
        for key, value in data.items():
            old_value = getattr(obj, key)
            if old_value != value:
                # Perform an update
                setattr(obj, key, value)

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


if __name__ == "__main__":
    root = Root()
    a_s = [A() for i in range(10)]
    [root.expose(a) for a in a_s]
    run(root)
