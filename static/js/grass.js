var makeBladeModel = function(type, typeData){
    var properties = _.chain(typeData).pairs().map(function(x){ return x[1] == "property" ? x[0] : null }).compact().value();
    properties.push("_id");
    var callables = _.chain(typeData).pairs().map(function(x){ return x[1] == "callable" ? x[0] : null }).compact().value();
    var nested = _.chain(typeData).pairs().map(function(x){ return x[1] == "property-nested" ? x[0] : null }).compact().value();

    return Backbone.Model.extend({
        idAttribute: "_id",
        properties: properties,
        callables: callables,
        nestedProperties: nested,
        type: type,
        url: function(){
            return "/root/" + type + "/" + this.id;
        },
        parse: function(response, options){
            // Only save properties, not callables
            // Pull out nested relationships
            var self = this;
            var plain =_.pick(response, properties);
            var nest = _.pick(response, nested);
            _.each(nest, function(value, key, obj){
                var col = root.all.get(value.__class__);
                var data = value.__data__;
                var lookup = function(id, idx){
                    if(col.contains(id)){
                        return col.get(id);
                    }else{
                        return col.create({"_id": id});
                    }
                }
                if(_.isArray(data)){
                    nest[key] = _.map(data, lookup);
                    nest[key + "__raw"] = value;
                }else if(_.isObject(data)){
                    var output = {};
                    _.map(data, function(v, k, obj){
                        output[k] = lookup(v, k);
                    });
                    nest[key] = output;
                    nest[key + "__raw"] = value;
                }else{
                    console.warn("Invalid data type", data);
                }
            });
            return _.extend(plain, nest);
        },
        toJSON: function(options){
            // Only send properties to server, not callables
            var plain =_.pick(this.attributes, properties);
            var nest = _.pick(this.attributes, nested);
            return plain; // TODO
        },
        call: function(key, args, options){
            // A combination of `.set` and `.fetch`
            var self = this;
            if(!_.contains(callables, key)){
                throw "Unable to call; function '" + key + "' does not exist.";
            }
            if(args === void 0){
                args = null;
            }

            var options = options ? _.clone(options) : {};
            var success = options.success;
            var data = {};
            data[key] = args;
            var params = {
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(response){
                    var retval = response[key];
                    if (!self.set(self.parse(response, options), options)) return false;
                    if (success) success(self, retval, options);
                    self.trigger('sync', self, response, options);
                    self.trigger('called:' + key, self, retval, options);
                }
            };
            this.sync('create', this, _.defaults(params, options));
        },
        initialize: function(){

        }
    });
}

var makeBladeCollection = function(type, typeData, model){
    return Backbone.Collection.extend({
        model: model,
        url: "/root/" + type,
        type: type,
        initialize: function(){
        }
    });
}

var Root = Backbone.Model.extend({
    url: "/root",
    Collections: {},
    Models: {},
    initialize: function(){
        var self = this;
        this.all = new Backbone.Model();
        this.listenToOnce(this, "change", function(model, options){
            console.log("first change", model.attributes);
            _.each(model.keys(), function(name){
                var mdl = self.Models[name] = makeBladeModel(name, model.get(name));
                self.Collections[name] = makeBladeCollection(name, model.get(name), mdl);
                self.all.set(name, new self.Collections[name]);
            });

            // Next time the model changes, that's bad!
            this.listenTo(this, "change", function(model, options){
                // This isn't good!
                console.log("Uh oh, model changed types!", model);
                Backbone.trigger("typeChange");
                // Maybe fire an event for the particular attrs that changed?
            });

            this.trigger("typesLoaded");
        });
    }
});


var root = new Root();
$(function(){
    console.log('r', root);
    root.fetch();
});

/*
Backbone.listenToOnce(root, "typesLoaded", function(){
    if(root.Collections.Timing){
        Timings = new root.Collections.Timing;

        Backbone.listenTo(Timings, "add", function(model){
            t = model;
        });

        Timings.fetch();
    }
});
*/

//run = function(){t.fetch({success: function(a){ a.fetch({success: function(b){ if(c){run();} }}); }});}

