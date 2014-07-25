var Blade = Backbone.Model.extend({
    idAttribute: "_id",
    initialize: function(){

    },
});

var Blades = Backbone.Collection.extend({
    model: Blade,
    initialize: function(type){
        this.type = type;
        this.url = "/root/" + type;
    }
});

var Root = Backbone.Model.extend({
    url: "/root",
    collections: [],
    parse: function(response, options){
        var resp = {};
        var self = this;
        _.each(response, function(r){
            resp[r] = r;
        });
        return resp;
    },
    set: function(key, val, options) {
        if (key == null) return this;

        // Handle both `"key", value` and `{key: value}` -style arguments.
        if (typeof key === 'object') {
            attrs = key;
            options = val;
        } else {
            (attrs = {})[key] = val;
        }
        
        for(attr in attrs){
            if(this.has(attr)){
                this.get(attr).fetch();
            }else{
                var blades = new Blades(attrs[attr]);
                blades.fetch();
                Backbone.Model.prototype.set.apply(this, [attr, blades, options]);
            }
        }
    }


});

var root = new Root();
root.fetch();
run = function(){t.fetch({success: function(a){ a.fetch({success: function(b){ if(c){run();} }}); }});}

