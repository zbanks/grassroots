grassroots
==========

An ill-advised library for rapidly prototyping python GUI applications in Javascript + HTML.

(*Metaclasses and introspection are usually the answer!*)

Examples
--------
- https://github.com/zbanks/beetle
- `python test.py` and navigate to http://localhost:8080/static/index.html

Model
-----
Grassroots is intended to make it easy to expose your Python objects in Javascript. It automatically builds a REST interface around your Python classes. This interface is then discovered by the client-side Javascript to build Backbone models to wrap the REST interface, giving you nearly-transparent access to the Python objects.

### Python
`grassroots.py`

`Root` is a singleton object that manages the web server. It is run as a WSGI app.

Classes can subclass `Blade` to be exposed over the REST interface.

Properties of blades are only exposed if they are subclasses of `Field`. 
Functions can be turned into fields with the `@CallableField` decorator. 
`JSONField` automatically serializes/deserializes between Python and Javascript objects.

### Javascript
`grass.js`

A singleton of the `Root` object is exposed as `root`. `root.Collections` contains all the types of classes (blades) exposed over the REST API. 

In general, models extracted from `root` behave like normal Backbone models. They have an additional `.call()` method which provides syntactic sugar for calling methods in Python-land.

Security Note
-------------
It goes without saying that this project *does not* attempt to enforce any form of security: it is only designed for locally running apps (i.e. prototyping).
