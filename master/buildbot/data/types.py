# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

# See "Type Validation" in master/docs/developer/tests.rst

import re
from buildbot import util
from buildbot.util import json
from buildbot.data import base

class Type(object):

    name = None
    doc = None

    def valueFromString(self, arg):
        # convert a urldecoded bytestring as given in a URL to a value, or
        # raise an exception trying.  This parent method raises an exception,
        # so if the method is missing in a subclass, it cannot be created from
        # a string.
        raise TypeError

    def cmp(self, val, arg):
        return cmp(val, self.valueFromString(arg))

    def validate(self, name, object):
        raise NotImplementedError


class NoneOk(Type):

    def __init__(self, nestedType):
        self.nestedType = nestedType
        self.name = self.nestedType.name + " or None"

    def valueFromString(self, arg):
        return self.nestedType.valueFromString(arg)

    def cmp(self, val, arg):
        return self.nestedType.cmp(val, arg)

    def validate(self, name, object):
        if object is None:
            return
        for msg in self.nestedType.validate(name, object):
            yield msg


class Instance(Type):

    types = ()

    def validate(self, name, object):
        if not isinstance(object, self.types):
            yield "%s (%r) is not a %s" % (
                    name, object, self.name or `self.types`)


class Integer(Instance):

    name = "integer"
    types = (int, long)

    def valueFromString(self, arg):
        return int(arg)


class String(Instance):

    name = "string"
    types = (unicode,)

    def valueFromString(self, arg):
        return arg.decode('utf-8')


class Binary(Instance):

    name = "binary"
    types = (str,)

    def valueFromString(self, arg):
        return arg


class Boolean(Instance):

    name = "boolean"
    types = (bool,)

    def valueFromString(self, arg):
        return util.string2boolean(arg)


class Link(Instance):

    name = "link"
    types = (base.Link,)


class Identifier(Type):

    name = "identifier"
    identRe = re.compile('^[a-zA-Z_-][a-zA-Z0-9_-]*$')

    def __init__(self, len=None, **kwargs):
        Type.__init__(self, **kwargs)
        self.len = len

    def valueFromString(self, arg):
        val = arg.decode('utf-8')
        if not self.identRe.match(val) or not 0 < len(val) <= self.len:
            raise TypeError
        return val

    def validate(self, name, object):
        if not isinstance(object, unicode):
            yield "%s - %r - is not a unicode string" % (name, object)
        elif not self.identRe.match(object):
            yield "%s - %r - is not an identifier" % (name, object)
        elif len(object) < 1:
            yield "%s - identifiers cannot be an empty string" % (name,)
        elif len(object) > self.len:
            yield "%s - %r - is longer than %d characters" % (name, object,
                                                                self.len)


class List(Type):

    name = "list"
    def __init__(self, of=None, **kwargs):
        Type.__init__(self, **kwargs)
        self.of = of

    def validate(self, name, object):
        if type(object) != list: # we want a list, and NOT a subclass
            yield "%s (%r) is not a %s" % (name, object, self.name)
            return

        for idx, elt in enumerate(object):
            for msg in self.of.validate("%s[%d]" % (name, idx), elt):
                yield msg


class SourcedProperties(Type):

    name = "sourced-properties"

    def validate(self, name, object):
        if type(object) != dict: # we want a dict, and NOT a subclass
            yield "%s is not sourced properties (not a dict)" % (name,)
            return
        for k, v in object.iteritems():
            if not isinstance(k, unicode):
                yield "%s property name %r is not unicode" % (name, k)
            if not isinstance(v, tuple) or len(v) != 2:
                yield "%s property value for '%s' is not a 2-tuple" % (name, k)
                return
            propval, propsrc = v
            if not isinstance(propsrc, unicode):
                yield "%s[%s] source %r is not unicode" % (name, k, propsrc)
            try:
                json.loads(propval)
            except:
                yield "%s[%r] value is not JSON-able" % (name, k)


class Entity(Type):

    # NOTE: this type is defined by subclassing it in each resource type class.
    # Instances are generally accessed at e.g.,
    #  * buildsets.Buildset.entityType or
    #  * self.master.data.rtypes.buildsets.entityType

    name = None # set in constructor
    fields = {}
    fieldNames = set([])

    def __init__(self, name):
        fields = {}
        for k, v in self.__class__.__dict__.iteritems():
            if isinstance(v, Type):
                fields[k] = v
        self.fields = fields
        self.fieldNames = set(fields)
        self.name = name

    def validate(self, name, object):
        # this uses isinstance, allowing dict subclasses as used by the DB API
        if not isinstance(object, dict):
            yield "%s (%r) is not a dictionary (got type %s)" \
                    % (name, object, type(object))
            return

        gotNames = set(object.keys())

        unexpected = gotNames - self.fieldNames
        if unexpected:
            yield "%s has unexpected keys %s" % (name,
                    ", ".join([ `n` for n in unexpected ]))

        missing = self.fieldNames - gotNames
        if missing:
            yield "%s is missing keys %s" % (name,
                    ", ".join([ `n` for n in missing ]))

        for k in gotNames & self.fieldNames:
            f = self.fields[k]
            for msg in f.validate("%s[%r]" % (name, k), object[k]):
                yield msg