# -*- python-indent: 4; coding: iso-8859-1; mode: python -*-
# Copyright (C) 2008 Cedric Pinson, Jeremy Moles
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#  Cedric Pinson <cedric.pinson@plopbyte.com>
#  Jeremy Moles <jeremy@emperorlinux.com>


import bpy
import mathutils
import os
from . import osglog


Matrix    = mathutils.Matrix
Vector    = mathutils.Vector
FLOATPRE  = 5
CONCAT    = lambda s, j="": j.join(str(v) for v in s)
STRFLT    = lambda f: "%%.%df" % FLOATPRE % float(f)
INDENT    = 2


def findNode(name, root):
    if root.name == name:
        return root
    if isinstance(root, Group) is False:
        return None
    for i in root.children:
        found = findNode(name, i)
        if found is not None:
            return found
    return None

def findMaterial(name, root):
    if root.stateset is not None:
        for i in root.stateset.attributes:
            if isinstance(i, Material) is True and i.name == name:
                return i
    if isinstance(root, Geode) is True:
        for i in root.drawables:
            found = findMaterial(name, i)
            if found is not None:
                return found
    if isinstance(root, Group) is True:
        for i in root.children:
            found = findMaterial(name, i)
            if found is not None:
                return found
    return None


class Writer(object):
    instances = {}
    wrote_elements = {}
    file_object = None

    def __init__(self, comment = None):
        object.__init__(self)
        self.comment = comment
        self.indent_level = 0
        self.counter = len(Writer.instances)
        Writer.instances[self] = True

    def write(self, output):
        Writer.serializeInstanceOrUseIt(self, output)
        
    def encode(self, string):
        text = string.replace("\t", "").replace("#", (" " * INDENT)).replace("$", (" " * (INDENT*self.indent_level) ))
        return text.encode('utf-8')

    def writeMatrix(self, output, matrix):
        if bpy.app.version[0] >= 2 and bpy.app.version[1] >= 62:
            for i in range(0,4):
                output.write(self.encode("$##%s %s %s %s\n" % (STRFLT(matrix[0][i]), STRFLT(matrix[1][i]),STRFLT(matrix[2][i]), STRFLT(matrix[3][i])) ) )
        else:
            for i in range(0,4):
                output.write(self.encode("$##%s %s %s %s\n" % (STRFLT(matrix[i][0]), STRFLT(matrix[i][1]),STRFLT(matrix[i][2]), STRFLT(matrix[i][3])) ) )
        output.write(self.encode("$#}\n"))


    @staticmethod
    def resetWriter():
        Writer.instances = {}
        wrote_elements = {}
        file_object = None

    @staticmethod
    def serializeInstanceOrUseIt(obj, output):
        if obj in Writer.wrote_elements and obj.shadow_object is not None:
            obj.shadow_object.indent_level = obj.indent_level
            return obj.shadow_object.serialize(output)
        Writer.wrote_elements[obj] = True
        return obj.serialize(output)

class ShadowObject(Writer):
    def __init__(self, *args, **kwargs):
        Writer.__init__(self, *args, **kwargs)
        self.target = args[0]
    
    def serialize(self, output):
        output.write(self.encode("$Use " + self.target.generateID() + "\n"))
    
class Object(Writer):
    
    def __init__(self, *args, **kwargs):
        Writer.__init__(self, *args)
        self.shadow_object = ShadowObject(self)
        self.dataVariance = "UNKNOWN"
        self.name = kwargs.get('name', "None")

    def copyFrom(self, obj):
        self.name = obj.name
        self.dataVariance = obj.dataVariance

    def generateID(self):
        return "uniqid_" + self.className() + "_" + str(self.counter)

    def setName(self, name):
        self.name = name

    def className(self):
        return "Object"

    def printContent(self):
        id = self.generateID()
        text = ""
        if id is not None:
            text += "$#UniqueID " + self.generateID() + "\n"
        if self.dataVariance is not "UNKNOWN":
            text += "$#DataVariance " + self.dataVariance + "\n"
        if self.name is not "None":
            text += "$#name \"%s\"\n" % self.name
        return text

    def serializeContent(self, output):
        id = self.generateID()
        if id is not None:
            output.write(self.encode("$#UniqueID " + self.generateID() + "\n"))
        if self.dataVariance is not "UNKNOWN":
            output.write(self.encode("$#DataVariance " + self.dataVariance + "\n"))
        if self.name is not "None":
            output.write(self.encode("$#name \"%s\"\n" % self.name))


class UpdateMatrixTransform(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.stacked_transforms = []

    def className(self):
        return "UpdateMatrixTransform"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        for s in self.stacked_transforms:
            s.indent_level = self.indent_level + 1
            s.write(output)

class UpdateMaterial(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)

    def className(self):
        return "UpdateMaterial"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        output.write(self.encode("$}\n"))

class StackedMatrixElement(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        if self.name == "None":
            self.name = "matrix"
        m = Matrix().to_4x4()
        m.identity()
        self.matrix = kwargs.get('matrix', m)

    def className(self):
        return "StackedMatrixElement"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#Matrix {\n"))
        self.writeMatrix(output, self.matrix)


class StackedTranslateElement(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.translate = kwargs.get('translate', Vector((0,0,0)))
        self.name = "translate"

    def className(self):
        return "StackedTranslateElement"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#translate %s %s %s\n" % (STRFLT(self.translate[0]), STRFLT(self.translate[1]),STRFLT(self.translate[2])) ) )


class StackedScaleElement(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.scale = kwargs.get('scale', Vector((1,1,1)))
        self.name = "scale"

    def className(self):
        return "StackedScaleElement"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#scale %s %s %s\n" % (STRFLT(self.scale[0]), STRFLT(self.scale[1]),STRFLT(self.scale[2]))))

class StackedRotateAxisElement(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.axis = kwargs.get('axis', Vector((1,0,0)))
        self.angle = kwargs.get('angle', 0)

    def className(self):
        return "StackedRotateAxisElement"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#axis %s %s %s\n" % (STRFLT(self.axis[0]), STRFLT(self.axis[1]),STRFLT(self.axis[2]))))
        output.write(self.encode("$#angle %s\n" % (STRFLT(self.angle))))

class StackedQuaternionElement(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        m = Matrix().to_4x4()
        m.identity()
        self.quaternion = kwargs.get('quaternion',  m.to_quaternion())
        self.name = "quaternion"

    def className(self):
        return "StackedQuaternionElement"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#quaternion %s %s %s %s\n" % (STRFLT(self.quaternion.x), STRFLT(self.quaternion.y),STRFLT(self.quaternion.z),STRFLT(self.quaternion.w) ) ))

class UpdateBone(UpdateMatrixTransform):
    def __init__(self, *args, **kwargs):
        UpdateMatrixTransform.__init__(self, *args, **kwargs)

    def className(self):
        return "UpdateBone"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        UpdateMatrixTransform.serializeContent(self, output)
        output.write(self.encode("$}\n"))

class UpdateSkeleton(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)

    def className(self):
        return "UpdateSkeleton"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        output.write(self.encode("$}\n"))

class Node(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.cullingActive = "TRUE"
        self.stateset = None
        self.update_callbacks = []

    def className(self):
        return "Node"

    def makeRef(self, refUniqueID):
        self.uniqueID = refUniqueID

    def makeNodeContents(self, name, uniqueID):
        self.name = name
        self.uniqueID = uniqueID

    def serialize(self, output):
        output.write(self.encode("$Node {\n"))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#cullingActive " + self.cullingActive  + "\n"))
        if self.stateset is not None:
            self.stateset.indent_level = self.indent_level + 1
            self.stateset.write(output)

        if len(self.update_callbacks) > 0:
            output.write(self.encode("$#UpdateCallbacks {\n"))
            for i in self.update_callbacks:
                i.indent_level = self.indent_level + 2
                i.write(output)
            output.write(self.encode("$#}\n"))
            

class Geode(Node):
    def __init__(self, *args, **kwargs):
        Node.__init__(self, *args, **kwargs)
        self.drawables = []

    def setName(self, name):
        self.name = self.className() + name

    def className(self):
        return "Geode"

    def serialize(self, output):
        output.write(self.encode("$Geode {\n"))
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#num_drawables %d" % (len(self.drawables))  + "\n"))
        for i in self.drawables:
            if i is not None:
                i.indent_level = self.indent_level + 1
                i.write(output)

class Group(Node):
    def __init__(self, *args, **kwargs):
        Node.__init__(self, *args, **kwargs)
        self.children = []

    def className(self):
        return "Group"

    def serialize(self, output):
        output.write(self.encode("$Group {\n"))
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#num_children %d" % (len(self.children)) + "\n"))
        for i in self.children:
            i.indent_level = self.indent_level + 1
            i.write(output)

class MatrixTransform(Group):
    def __init__(self, *args, **kwargs):
        Group.__init__(self, *args, **kwargs)
        self.matrix = Matrix().to_4x4()
        self.matrix.identity()
    
    def className(self):
        return "MatrixTransform"

    def serialize(self, output):
        output.write(self.encode("$MatrixTransform {\n"))
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        self.serializeContent(output)
        Group.serializeContent(self, output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#Matrix {\n"))
        self.writeMatrix(output, self.matrix)

class StateAttribute(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.update_callbacks = []

    def className(self):
        return "StateAttribute"

    def printContent(self):
        text = Object.printContent(self)
        if len(self.update_callbacks) > 0:
            text += "$#UpdateCallback {\n"
            for i in self.update_callbacks:
                i.indent_level = self.indent_level + 2
                text += str(i)
            text += "$#}\n"
        return text

    def serializeContent(self, output):
        Object.serializeContent(self, output)
        if len(self.update_callbacks) > 0:
            output.write(self.encode("$#UpdateCallback {\n"))
            for i in self.update_callbacks:
                i.indent_level = self.indent_level + 2
                i.write(output)
            output.write(self.encode("$#}\n"))

class StateTextureAttribute(StateAttribute):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.unit = 0

    def className(self):
        return "StateTextureAttribute"

    def printContent(self):
        text = Object.printContent(self)
        return text

    def serializeContent(self, output):
        Object.serializeContent(self, output)

class Light(StateAttribute):
    def __init__(self, *args, **kwargs):
        StateAttribute.__init__(self, *args, **kwargs)
        self.light_num = 0
        self.ambient = (0.0, 0.0, 0.0, 1.0)
        self.diffuse = (0.8, 0.8, 0.8, 1.0)
        self.specular = (1.0, 1.0, 1.0, 1.0)
        self.position = (0.0, 0.0, 1.0, 0.0)
        self.direction = (0.0, 0.0, -1.0)
        self.spot_exponent = 0.0
        self.spot_cutoff = 180.0
        self.constant_attenuation = 1.0
        self.linear_attenuation = 0.0
        self.quadratic_attenuation = 0.0

    def className(self):
        return "Light"

    def generateID(self):
        return None

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        Object.serializeContent(self, output)
        output.write(self.encode("$#light_num %s\n" % self.light_num))
        output.write(self.encode("$#ambient %s %s %s %s\n" % (STRFLT(self.ambient[0]), STRFLT(self.ambient[1]), STRFLT(self.ambient[2]), STRFLT(self.ambient[3]))))
        output.write(self.encode("$#diffuse %s %s %s %s\n" % (STRFLT(self.diffuse[0]), STRFLT(self.diffuse[1]), STRFLT(self.diffuse[2]), STRFLT(self.diffuse[3]))))
        output.write(self.encode("$#specular %s %s %s %s\n" % (STRFLT(self.specular[0]), STRFLT(self.specular[1]), STRFLT(self.specular[2]), STRFLT(self.specular[3]))))
        output.write(self.encode("$#position %s %s %s %s\n" % (STRFLT(self.position[0]), STRFLT(self.position[1]), STRFLT(self.position[2]), STRFLT(self.position[3]))))

        output.write(self.encode("$#direction %s %s %s\n" % (STRFLT(self.direction[0]), STRFLT(self.direction[1]), STRFLT(self.direction[2]))))

        output.write(self.encode("$#constant_attenuation %s\n" % STRFLT(self.constant_attenuation)))
        output.write(self.encode("$#linear_attenuation %s\n" % STRFLT(self.linear_attenuation)))
        output.write(self.encode("$#quadratic_attenuation %s\n" % STRFLT(self.quadratic_attenuation)))

        output.write(self.encode("$#spot_exponent %s\n" % STRFLT(self.spot_exponent)))
        output.write(self.encode("$#spot_cutoff %s\n" % STRFLT(self.spot_cutoff)))


class LightSource(Group):
    def __init__(self, *args, **kwargs):
        Group.__init__(self, *args, **kwargs)
        self.light = Light()
        self.cullingActive = "FALSE"

    def className(self):
        return "LightSource"

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        if self.light is not None:
            self.light.indent_level = self.indent_level + 1
            self.light.write(output)
        Group.serializeContent(self, output)

class Texture2D(StateTextureAttribute):
    def __init__(self, *args, **kwargs):
        StateTextureAttribute.__init__(self, *args, **kwargs)
        self.source_image = None
        self.file = "none"
        self.wrap_s = "REPEAT"
        self.wrap_t = "REPEAT"
        self.wrap_r = "REPEAT"
        self.min_filter = "LINEAR_MIPMAP_LINEAR"
        self.mag_filter = "LINEAR"
        self.internalFormatMode = "USE_IMAGE_DATA_FORMAT"

    def className(self):
        return "Texture2D"

    def serialize(self, output):
        output.write(self.encode("$GL_TEXTURE_2D ON\n"))
        output.write(self.encode("$%s {\n" % self.className()))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        StateTextureAttribute.serializeContent(self, output)
        output.write(self.encode("$#file \"%s\"\n" % self.file))
        output.write(self.encode("$#wrap_s %s\n" % self.wrap_s))
        output.write(self.encode("$#wrap_t %s\n" % self.wrap_t))
        output.write(self.encode("$#wrap_r %s\n" % self.wrap_r))
        output.write(self.encode("$#min_filter %s\n" % self.min_filter))
        output.write(self.encode("$#mag_filter %s\n" % self.mag_filter))
        output.write(self.encode("$#internalFormatMode %s\n" % self.internalFormatMode))
        output.write(self.encode("$#subloadMode OFF\n"))


class Material(StateAttribute):
    def __init__(self, *args, **kwargs):
        StateAttribute.__init__(self, *args, **kwargs)
        diffuse_energy = 0.8
        self.colormode = "OFF"
        self.emission = (0.0, 0.0, 0.0, 1.0)
        self.ambient = (0.0, 0.0, 0.0, 1.0)
        self.diffuse = (0.8 * diffuse_energy, 0.8 * diffuse_energy, 0.8 * diffuse_energy, 1.0)
        self.specular = (0.5, 0.5, 0.5, 1.0)
        self.shininess = 40/(512/128) # blender encode shininess to 512 and opengl to 128

    def className(self):
        return "Material"

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        StateAttribute.serializeContent(self,output)
        output.write(self.encode("$#ColorMode %s\n" % self.colormode))
        output.write(self.encode("$#ambientColor %s %s %s %s\n" % (STRFLT(self.ambient[0]), STRFLT(self.ambient[1]), STRFLT(self.ambient[2]), STRFLT(self.ambient[3]))))
        output.write(self.encode("$#diffuseColor %s %s %s %s\n" % (STRFLT(self.diffuse[0]), STRFLT(self.diffuse[1]), STRFLT(self.diffuse[2]), STRFLT(self.diffuse[3]))))
        output.write(self.encode("$#specularColor %s %s %s %s\n" % (STRFLT(self.specular[0]), STRFLT(self.specular[1]), STRFLT(self.specular[2]), STRFLT(self.specular[3]))))
        output.write(self.encode("$#emissionColor %s %s %s %s\n" % (STRFLT(self.emission[0]), STRFLT(self.emission[1]), STRFLT(self.emission[2]), STRFLT(self.emission[3]))))
        output.write(self.encode("$#shininess %s\n" % STRFLT(self.shininess)))

class LightModel(StateAttribute):
    def __init__(self, *args, **kwargs):
        StateAttribute.__init__(self, *args, **kwargs)
        self.local_viewer = "FALSE"
        self.color_control = "SEPARATE_SPECULAR_COLOR"
        self.ambient = (0.2, 0.2, 0.2, 1.0)

    def className(self):
        return "LightModel"

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        StateAttribute.serializeContent(self, output)
        output.write(self.encode("$#ambientIntensity %s %s %s %s\n" % (STRFLT(self.ambient[0]), STRFLT(self.ambient[1]), STRFLT(self.ambient[2]), STRFLT(self.ambient[3]))))
        output.write(self.encode("$#colorControl %s\n" % self.color_control))
        output.write(self.encode("$#localViewer %s\n" % self.local_viewer))

class StateSet(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.modes = {}
        self.attributes = []
        self.texture_attributes = {}

    def className(self):
        return "StateSet"

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        for i in self.modes.items():
            if i is not None:
                output.write(self.encode("$#%s %s\n" %i))
        for i in self.attributes:
            if i is not None:
                i.indent_level = self.indent_level + 1
                i.write(output)
        for (unit, attributes) in self.texture_attributes.items():
            if attributes is not None and len(attributes) > 0:
                output.write(self.encode("$#textureUnit %s {\n" % unit))
                for a in attributes:
                    if a is not None:
                        a.indent_level = self.indent_level + 2
                        a.write(output)
                output.write(self.encode("$#}\n"))

class ShadowVertexArrayObject(Writer):
    def __init__(self, *args, **kwargs):
        Writer.__init__(self)
        self.target = args[0]
        self.binding = None
    
    def serialize(self, output):
        if self.binding is not None:
            output.write(self.encode("$" + self.binding + "\n"))
        output.write(self.encode("$" + self.target.className() + " Use " + self.target.generateID() + "\n"))


class VertexArray(Writer):
    def __init__(self, *args, **kwargs):
        Writer.__init__(self)
        self.array = kwargs.get('array', [])
        self.shadow_object = ShadowVertexArrayObject(self, "Vec3Array")

    def className(self):
        return "VertexArray"

    def generateID(self):
        return self.className() + "_" + str(self.counter)

    def serialize(self, output):
        output.write(self.encode("$%s UniqueID %s Vec3Array %s\n${\n" % (self.className(), self.generateID(), str(len(self.array)))))
        for i in self.array:
            output.write(self.encode("$#%s %s %s\n" % (STRFLT(i[0]), STRFLT(i[1]), STRFLT(i[2]) ) ) )
        output.write(self.encode("$}\n") )


class NormalArray(VertexArray):
    def __init__(self, *args, **kwargs):
        VertexArray.__init__(self, *args, **kwargs)
        self.shadow_object = ShadowVertexArrayObject(self, "Vec3Array")
        self.shadow_object.binding = "NormalBinding PER_VERTEX"

    def className(self):
        return "NormalArray"

    def serialize(self, output):
        output.write(self.encode("$NormalBinding PER_VERTEX\n"))
        output.write(self.encode("$%s UniqueID %s Vec3Array %s\n${\n" % (self.className(), self.generateID(), len(self.array))) )
        for i in self.array:
            output.write(self.encode("$#%s %s %s\n" % (STRFLT(i[0]), STRFLT(i[1]), STRFLT(i[2])) ) )
        output.write(self.encode("$}\n") )

class ColorArray(VertexArray):
    def __init__(self, *args, **kwargs):
        VertexArray.__init__(self, *args, **kwargs)
        self.shadow_object = ShadowVertexArrayObject(self, "Vec4Array")
        self.shadow_object.binding = "ColorBinding PER_VERTEX"

    def className(self):
        return "ColorArray"

    def serialize(self, output):
        output.write(self.encode("$%s UniqueID %s Vec4Array %s\n${\n" % (self.className(), self.generateID(), len(self.array)) ) )

        for i in self.array:
            output.write(self.encode("$#%s %s %s %s\n" % (STRFLT(i[0]), STRFLT(i[1]), STRFLT(i[2]), STRFLT(i[3]))) )
        output.write(self.encode("$}\n") )


class TexCoordArray(VertexArray):
    def __init__(self, *args, **kwargs):
        VertexArray.__init__(self, *args, **kwargs)
        self.index = 0
        self.shadow_object = ShadowVertexArrayObject(self, "Vec2Array")

    def className(self):
        return "TexCoordArray"

    def serialize(self, output):
        output.write(self.encode("$%s %s UniqueID %s Vec2Array %s\n${\n" % (self.className(), self.index, self.generateID(),  len(self.array)) ) )
        for i in self.array:
            output.write(self.encode( "$#%s %s\n" % (STRFLT(i[0]), STRFLT(i[1])) ) )
        output.write(self.encode("$}\n") )

class DrawElements(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.indexes = []
        self.type = None
        self.shadow_object = None

    def getSizeArray(self):
        element = "DrawElementsUByte"
        for i in self.indexes:
            if i > 255 and element == "DrawElementsUByte":
                element = "DrawElementsUShort"
            elif i > 65535 and element == "DrawElementsUShort":
                element = "DrawElementsUInt"
                break
        return element

    def className(self):
        return "DrawElements"

    def serialize(self, output):
        element = self.getSizeArray()
        output.write(self.encode("$#%s %s %s {\n" % (element, self.type, str(len(self.indexes))) ) )
        n = 1
        if self.type == "TRIANGLES":
            n = 3
        if self.type == "QUADS":
            n = 4

        total = int(len(self.indexes) / n)
        for i in range(0, total):
            output.write(self.encode("$##"))
            for a in range(0,n):
                output.write(self.encode("%s " % self.indexes[i*n+a]))
            output.write(self.encode("\n") )
        output.write(self.encode("$#}\n"))

    
class Geometry(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.primitives = []
        self.vertexes = None
        self.normals = None
        self.colors = None
        self.uvs = {}
        self.stateset = None

    def className(self):
        return "Geometry"

    def copyFrom(self, geometry):
        Object.copyFrom(self, geometry)
        self.primitives = geometry.primitives
        self.vertexes = geometry.vertexes
        self.normals = geometry.normals
        self.colors = geometry.colors
        self.uvs = geometry.uvs
        self.stateset = geometry.stateset

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.className()) )
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        if len(self.primitives):
            output.write(self.encode("$#Primitives %s {\n" % (str(len(self.primitives))) ) )
            for i in self.primitives:
                i.indent_level = self.indent_level + 1
                i.write(output)
            output.write(self.encode("$#}\n"))
        if self.vertexes:
            self.vertexes.indent_level = self.indent_level + 1
            self.vertexes.write(output)
        if self.normals:
            self.normals.indent_level = self.indent_level + 1
            self.normals.write(output)
        if self.colors:
            self.colors.indent_level = self.indent_level + 1
            self.colors.write(output)
        for i in self.uvs.values():
            if i:
                i.indent_level = self.indent_level + 1
                i.write(output)
        if self.stateset is not None:
            self.stateset.indent_level = self.indent_level + 1
            self.stateset.write(output)

################################## animation node ######################################
class Bone(MatrixTransform):
    def __init__(self, skeleton = None, bone = None, parent=None, **kwargs):
        MatrixTransform.__init__(self, **kwargs)
        self.dataVariance = "DYNAMIC"
        self.parent = parent
        self.skeleton = skeleton
        self.bone = bone
        self.inverse_bind_matrix = Matrix().to_4x4().identity()

    def buildBoneChildren(self):
        if self.skeleton is None or self.bone is None:
            return
        
        self.setName(self.bone.name)
        update_callback = UpdateBone()
        update_callback.setName(self.name)
        self.update_callbacks.append(update_callback)

        bone_matrix = self.bone.matrix_local.copy()

        if self.parent:
            parent_matrix = self.bone.parent.matrix_local.copy()
            bone_matrix = parent_matrix.inverted() * bone_matrix
        
        # add bind matrix in localspace callback
        update_callback.stacked_transforms.append(StackedMatrixElement(name = "bindmatrix", matrix = bone_matrix))
        
        # initialize the bone position to the current pose
        self.skeleton.data.pose_position = 'POSE'
        posebone = self.skeleton.pose.bones[self.bone.name]
        pmat = posebone.matrix_basis.copy()
        
        update_callback.stacked_transforms.append(StackedTranslateElement(translate = pmat.to_translation()))
        
        rotation_mode = posebone.rotation_mode
        if rotation_mode in ["XYZ", "XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]:
            euler = pmat.to_euler(rotation_mode)
            rotation_keys = [StackedRotateAxisElement(name = "euler_x", axis = Vector((1,0,0)), angle = euler.x),
                             StackedRotateAxisElement(name = "euler_y", axis = Vector((0,1,0)), angle = euler.y),
                             StackedRotateAxisElement(name = "euler_z", axis = Vector((0,0,1)), angle = euler.z)]
        
            update_callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[2]) - ord('X')])
            update_callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[1]) - ord('X')])
            update_callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[0]) - ord('X')])
                
        if rotation_mode == "QUATERNION":
            update_callback.stacked_transforms.append(StackedQuaternionElement(quaternion = pmat.to_quaternion()))
        
        if rotation_mode == "AXIS_ANGLE":
            update_callback.stacked_transforms.append(StackedRotateAxisElement(name = "axis_angle", 
                                                 axis = pmat.to_quaternion().to_axis_angle[0], 
                                                 angle = pmat.to_quaternion().to_axis_angle[1]))
        
        update_callback.stacked_transforms.append(StackedScaleElement(scale = pmat.to_scale()))
        
        self.skeleton.data.pose_position = 'REST'

        self.bone_inv_bind_matrix_skeleton = self.bone.matrix_local.copy().inverted()
        if not self.bone.children:
            return

        for boneChild in self.bone.children:
            b = Bone(self.skeleton, boneChild, self)
            self.children.append(b)
            b.buildBoneChildren()

    def getMatrixInArmatureSpace(self):
        return self.bone.matrix_local

    def collect(self, d):
        d[self.name] = self
        for boneChild in self.children:
            boneChild.collect(d)

    def className(self):
        return "Bone"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()) )
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        self.serializeContent(output)
        MatrixTransform.serializeContent(self, output)
        Group.serializeContent(self, output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        matrix = self.bone_inv_bind_matrix_skeleton.copy()
        output.write(self.encode("$#InvBindMatrixInSkeletonSpace {\n"))
        self.writeMatrix(output, matrix)

class Skeleton(MatrixTransform):
    def __init__(self, name="", matrix=None):
        MatrixTransform.__init__(self)
        self.boneDict = {}
        self.matrix = matrix
        self.setName(name)
        self.update_callbacks = []
        self.update_callbacks.append(UpdateSkeleton())

    def collectBones(self):
        self.boneDict = {}
        for bone in self.children:
            bone.collect(self.boneDict)

    def getMatrixInArmatureSpace(self):
        return self.matrix

    def className(self):
        return "Skeleton"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        Node.serializeContent(self, output)
        MatrixTransform.serializeContent(self, output)
        Group.serializeContent(self, output)
        output.write(self.encode("$}\n"))

class RigGeometry(Geometry):
    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)
        self.groups = {}
        self.dataVariance = "DYNAMIC"
        self.sourcegeometry = None

    def className(self):
        return "RigGeometry"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        Geometry.serializeContent(self, output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#num_influences %s\n" % len(self.groups)))
        if len(self.groups) > 0:
            for name, grp in self.groups.items():
                grp.indent_level = self.indent_level + 1
                grp.write(output)

        if self.sourcegeometry is not None:
            self.sourcegeometry.indent_level = self.indent_level + 1
            self.sourcegeometry.write(output)

class AnimationManagerBase(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.animations = []

    def className(self):
        return "AnimationManagerBase"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#num_animations %s\n" % len(self.animations) ))
        for i in self.animations:
            i.indent_level = self.indent_level + 1
            i.write(output)


class BasicAnimationManager(AnimationManagerBase):
    def __init__(self, *args, **kwargs):
        AnimationManagerBase.__init__(self, *args, **kwargs)

    def className(self):
        return "BasicAnimationManager"

    def serialize(self, output):
        AnimationManagerBase.serialize(self, output)

    def serializeContent(self, output):
        AnimationManagerBase.serializeContent(self, output)

class VertexGroup(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.vertexes = []
        self.targetGroupName = "None"

    def className(self):
        return "VertexGroup"

    def generateID(self):
        return "uniqid_" + self.className() + self.targetGroupName

    def serialize(self, output):
        self.setName(self.targetGroupName)
        output.write(self.encode("$osgAnimation::VertexInfluence \"%s\" %s {\n" % (self.targetGroupName, len(self.vertexes)) ) )
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        for i in self.vertexes:
            output.write(self.encode("$#%s %s\n" % (i[0],STRFLT(i[1])) ) )

class Animation(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.channels = []
    
    def className(self):
        return "Animation"

    def serialize(self, output):
        output.write(self.encode("$osgAnimation::%s {\n" % self.className()))
        Object.serializeContent(self, output)
        self.serializeContent(output)
        output.write(self.encode("$}\n") )

    def serializeContent(self, output):
        output.write(self.encode("$#num_channels %s\n" % len(self.channels)))
        for i in self.channels:
            i.indent_level = self.indent_level + 1
            i.write(output)

class Channel(Object):
    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self.keys = []
        self.target = "none"
        self.type = "Unknown"

    def generateID(self):
        return None
    
    def className(self):
        return "Channel"

    def serialize(self, output):
        output.write(self.encode("$%s {\n" % self.type))
        self.serializeContent(output)
        output.write(self.encode("$}\n"))

    def serializeContent(self, output):
        output.write(self.encode("$#name \"%s\"\n" % self.name))
        output.write(self.encode("$#target \"%s\"\n" % self.target))
        output.write(self.encode("$#Keyframes %s {\n" % (len(self.keys))))
        for i in self.keys:
            output.write(self.encode("$##key"))
            for a in range(0, len(i)):
                output.write(self.encode(" %s" % (STRFLT(i[a]))))
            output.write(self.encode("\n"))
        output.write(self.encode("$#}\n"))
