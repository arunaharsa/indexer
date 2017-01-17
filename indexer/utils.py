def is_camel(s):
    return (s != s.lower() and s != s.upper())

def underscore_to_camelcase(word, lower_first=True):
    if not is_camel(word):
        result = ''.join(char.capitalize() for char in word.split('_'))
        if lower_first:
            return result[0].lower() + result[1:]
        else:
            return result
    return word

def recursive_key_map(function, obj):
    if isinstance(obj, dict):
        new_dict = {}
        for key, value in obj.iteritems():
            if isinstance(key, basestring):
                key = function(key)
            new_dict[key] = recursive_key_map(function, value)
        return new_dict
    if hasattr(obj, '__iter__'):
        return [recursive_key_map(function, value) for value in obj]
    else:
        return obj
