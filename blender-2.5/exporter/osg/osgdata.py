# -*- python-indent: 4; mode: python -*-
#
# Copyright (C) 2008-2012 Cedric Pinson
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
#  Peter Amstutz <tetron@interreality.org>

import bpy
import mathutils
from   mathutils import *
import bpy
import sys
import math
import os
import shutil
import subprocess
from sys import exit

import osg
from . import osglog
from . import osgconf
from .osgconf import DEBUG
from .osgconf import debug
from . import osgbake
from . import osgobject
from .osgobject import *

Vector     = mathutils.Vector
Quaternion = mathutils.Quaternion
Matrix     = mathutils.Matrix
Euler      = mathutils.Euler

def createImageFilename(texturePath, image):
    fn = bpy.path.basename(image.filepath)
    i = fn.rfind(".")
    if i != -1:
        name = fn[0:i]
    else:
        name = fn
    # [BMP, IRIS, PNG, JPEG, TARGA, TARGA_RAW, AVI_JPEG, AVI_RAW, FRAMESERVER]
    #print("format " + image.file_format)
    if image.file_format == 'PNG':
        ext = "png"
    elif image.file_format == 'JPEG':
        ext = "jpg"
    elif image.file_format == 'TARGA' or image.file_format == 'TARGA_RAW':
        ext = "tga"
    elif image.file_format == 'BMP':
        ext = "bmp"
    elif image.file_format == 'AVI_JPEG' or image.file_format == 'AVI_RAW':
        ext = "avi"
    else:
        ext = "unknown"
    name = name + "." +ext
    print("create Image Filename " + name)
    if texturePath != "" and not texturePath.endswith("/"):
        texturePath = texturePath + "/"
    return texturePath + name

def getImageFilesFromStateSet(stateset):
    list = []
    #if DEBUG: osglog.log("stateset %s" % str(stateset))
    if stateset is not None and len(stateset.texture_attributes) > 0:
        for unit, attributes in stateset.texture_attributes.items():
            for a in attributes:
                if a.className() == "Texture2D":
                    list.append(a.source_image)
    return list

def getRootBonesList(armature):
    bones = []
    for bone in armature.bones:
        if bone.parent == None:
            bones.append(bone)
    return bones

def getTransform(matrix):
    return (matrix.translationPart(), 
            matrix.scalePart(),
            matrix.toQuat())

def getDeltaMatrixFrom(parent, child):
    if parent is None:
        return child.matrix_world

    return getDeltaMatrixFromMatrix(parent.matrix_world,
                                    child.matrix_world)

def getDeltaMatrixFromMatrix(parent, child):
        p = parent
        bi = p.copy()
        bi.invert()
        return bi*child

def getChildrenOf(scene, object):
    children = []
    for obj in scene.objects:
        if obj.parent == object:
            children.append(obj)
    return children


def findBoneInHierarchy(scene, bonename):
        if scene.name == bonename and (type(scene) == type(Bone()) or type(scene) == type(Skeleton())):
                return scene

        #print scene.name
        if isinstance(scene, Group) is False:
                return None
        
        for child in scene.children:
                result = findBoneInHierarchy(child, bonename)
                if result is not None:
                        return result
        return None

def isActionLinkedToObject(action, objects_name):
    action_fcurves = action.fcurves
    #log("action ipos " + str(action_ipos_items))
    for fcurve in action_fcurves:
        #log("is " + str(obj_name) + " in "+ str(objects_name))
        path = fcurve.data_path.split("\"")
        if objects_name in path:
            return True;
    return False


def findArmatureObjectForTrack(track):
    for o in bpy.data.objects:
        if o.type.lower() == "Armature".lower():
            if list(o.animation_data.nla_tracks).count(track) > 0:
                return 0
    return None

#def findObjectForIpo(ipo):
#    index = ipo.name.rfind('-')
#    if index != -1:
#        objname = ipo.name[index+1:]
#        try:
#            obj = self.config.scene.objects[objname]
#            log("bake ipo %s to object %s" % (ipo.name, objname))
#            return obj
#        except:
#            return None
#
#    for o in self.config.scene.objects:
#        if o.getIpo() == ipo:
#            log("bake ipo %s to object %s" % (ipo.name, o.name))
#            return o
#    return None
#
#def findMaterialForIpo(ipo):
#    index = ipo.name.rfind('-')
#    if index != -1:
#        objname = ipo.name[index+1:]
#        try:
#            obj = bpy.data.materials[objname]
#            log("bake ipo %s to material %s" % (ipo.name, objname))
#            return obj
#        except:
#            return None
#
#    for o in bpy.data.materials:
#        if o.getIpo() == ipo:
#            log("bake ipo %s to material %s" % (ipo.name, o.name))
#            return o
#    return None

def createAnimationUpdate(obj, callback, rotation_mode, prefix="", zero=False):
    has_location_keys = False
    has_scale_keys = False
    has_rotation_keys = False
        
    if obj.animation_data:
        action = obj.animation_data.action
        
        if action:
            for curve in action.fcurves:
                datapath = curve.data_path[len(prefix):]
                osglog.log("curve.data_path " + curve.data_path + " " + str(curve.array_index) + " " + datapath)
                if datapath == "location":
                    has_location_keys = True
                
                if datapath.startswith("rotation"):
                    has_rotation_keys = True
                
                if datapath == "scale":
                    has_scale_keys = True
                    
    if not (has_location_keys or has_scale_keys or has_rotation_keys) and (len(obj.constraints) == 0):
        return None
    
    if zero:
        if has_location_keys:
            callback.stacked_transforms.append(StackedTranslateElement())
            
        if has_rotation_keys:
            if rotation_mode in ["XYZ", "XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]:
                rotation_keys = [StackedRotateAxisElement(name = "euler_x", axis = Vector((1,0,0)), angle = 0),
                                 StackedRotateAxisElement(name = "euler_y", axis = Vector((0,1,0)), angle = 0),
                                 StackedRotateAxisElement(name = "euler_z", axis = Vector((0,0,1)), angle = 0)]
            
                callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[2]) - ord('X')])
                callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[1]) - ord('X')])
                callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[0]) - ord('X')])
            
            if rotation_mode == "QUATERNION":
                callback.stacked_transforms.append(StackedQuaternionElement())
            
            if rotation_mode == "AXIS_ANGLE":
                callback.stacked_transforms.append(StackedRotateAxisElement(name = "axis_angle"))
        
        if has_scale_keys:
            sc = StackedScaleElement(scale = Vector(obj.scale))
            callback.stacked_transforms.append(sc)
            
    else:
        callback.stacked_transforms.append(StackedTranslateElement(translate = Vector(obj.location)))
        
        if rotation_mode in ["XYZ", "XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]:
            rotation_keys = [StackedRotateAxisElement(name = "euler_x", axis = Vector((1,0,0)), angle = obj.rotation_euler.x),
                             StackedRotateAxisElement(name = "euler_y", axis = Vector((0,1,0)), angle = obj.rotation_euler.y),
                             StackedRotateAxisElement(name = "euler_z", axis = Vector((0,0,1)), angle = obj.rotation_euler.z)]
        
            callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[2]) - ord('X')])
            callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[1]) - ord('X')])
            callback.stacked_transforms.append(rotation_keys[ord(rotation_mode[0]) - ord('X')])
            
        if rotation_mode == "QUATERNION": 
            callback.stacked_transforms.append(StackedQuaternionElement(quaternion = obj.rotation_quaternion))
        
        if rotation_mode == "AXIS_ANGLE":
            callback.stacked_transforms.append(StackedRotateAxisElement(name = "axis_angle", 
                                                axis = Vector(obj.rotation_axis_angle[0:2]), 
                                                angle = obj.rotation_axis_angle[3]))
        
        callback.stacked_transforms.append(StackedScaleElement(scale = Vector(obj.scale)))

    return callback

def createAnimationsGenericObject(osg_object, blender_object, config, update_callback, uniq_anims):
    if (config.export_anim is False) or (update_callback is None):
        return None

    action2animation = BlenderAnimationToAnimation(object = blender_object, config = config, 
                                                   uniq_anims = uniq_anims)
    anim = action2animation.createAnimation()
    osglog.log("animations created for object '%s'" % (blender_object.name))
    if anim != None:
        osglog.log("processed animation '%s'" % anim.name)
        osg_object.update_callbacks.append(update_callback)
    return [anim]
    
def createAnimationsSkeletonObject(osg_object, blender_object, config, uniq_anims):
    osglog.log("animation_data is %s %s" % (blender_object.name, blender_object.animation_data))
    if (config.export_anim is False) or (blender_object.animation_data == None) or (blender_object.animation_data.action == None):
        return None

    action2animation = BlenderAnimationToAnimation(object = blender_object, config = config, 
                                                   uniq_anims = uniq_anims)
    osglog.log("animations created for object '%s'" % (blender_object.name))
    
    anims = []                                           
    for (bname, bone) in osg_object.boneDict.items():
        anim = action2animation.createAnimation(target=bname, prefix=('pose.bones["%s"].' % (bname)))
        osglog.log("animations processed for armature %s bone %s" % (blender_object.name, bname))

        if anim != None:
            anims.append(anim)
    
    return anims

def createAnimationsObjectAndSetCallback(osg_node, obj, config, uniq_anims):
    return createAnimationsGenericObject(osg_node, obj, config, 
                createAnimationUpdate(obj, UpdateMatrixTransform(name=obj.name), obj.rotation_mode), 
                uniq_anims)
    
def createAnimationMaterialAndSetCallback(osg_node, obj, config, uniq_anims):
    osglog.log("WARNING update material animation not yet supported")
    return None
    #return createAnimationsGenericObject(osg_node, obj, config, UpdateMaterial(), uniq_anims)

class Export(object):
    def __init__(self, config = None):
        object.__init__(self)
        self.items = []
        self.config = config
        if self.config is None:
            self.config = osgconf.Config()
        self.rest_armatures = []
        self.animations = []
        self.images = set()
        self.lights = {}
        self.root = None
        self.uniq_objects = {}
        self.uniq_stateset = {}
        self.uniq_geodes = {}
        self.uniq_anims = {}

    def isValidToExport(self, object):
        if object.name in self.config.exclude_objects:
            return False
        
        if self.config.only_visible:
            if object.is_visible(self.config.scene):
                return True
        else:
            return not object.hide_render
        
    def setArmatureInRestMode(self):
        for arm in bpy.data.objects:
            if arm.type == "ARMATURE":
                print(arm)
                if arm.data.pose_position == 'POSE':
                    arm.data.pose_position = 'REST'
                    self.rest_armatures.append(arm)

    def restoreArmaturePoseMode(self):
        for arm in self.rest_armatures:
            arm.data.pose_position = 'POSE'

    def exportItemAndChildren(self, obj):
        item = self.exportChildrenRecursively(obj, None, None)
        if item is not None:
            self.items.append(item)

    def evaluateGroup(self, obj, item, rootItem):
        if obj.dupli_group is None or len(obj.dupli_group.objects) == 0:
            return
        osglog.log(str("resolving " + obj.dupli_group.name + " for " + obj.name + " offset " + str(obj.dupli_group.dupli_offset)) )


        group = MatrixTransform()
        group.matrix = Matrix.Translation(-obj.dupli_group.dupli_offset)
        item.children.append(group)
        
        # for group we disable the only visible
        config_visible = self.config.only_visible
        self.config.only_visible = False
        for o in obj.dupli_group.objects:
            osglog.log(str("object " + str(o)))
            self.exportChildrenRecursively( o, group, rootItem)
        self.config.only_visible = config_visible
        # and restore it after processing group

    def getName(self, obj):
        if hasattr(obj, "name"):
            return obj.name
        return "no name"

    def exportChildrenRecursively(self, obj, parent, rootItem):
        if self.isValidToExport(obj) == False:
            return None
            
        osglog.log("")

        anims = []
        item = None
        if obj in self.uniq_objects:
            osglog.log(str("use referenced item for " + obj.name + " " + obj.type))
            item = self.uniq_objects[obj]
        else:
            osglog.log("Type of " + obj.name + " is " + obj.type)
            if obj.type == "ARMATURE":
                item = self.createSkeleton(obj)
                anims = createAnimationsSkeletonObject(item, obj, self.config, self.uniq_anims)

            elif obj.type == "MESH" or obj.type == "EMPTY":
                # because it blender can insert inverse matrix, we have to recompute the parent child
                # matrix for our use. Not if an armature we force it to be in rest position to compute
                # matrix in the good space
                matrix = getDeltaMatrixFrom(obj.parent, obj)
                item = MatrixTransform()
                item.setName(obj.name)
                
                item.matrix = matrix.copy()
                if self.config.zero_translations and parent == None:
                    if bpy.app.version[0] >= 2 and bpy.app.version[1] >= 62:
                        print("zero_translations option has not been converted to blender 2.62")
                    else:
                        item.matrix[3].xyz = Vector()
                
                anims = createAnimationsObjectAndSetCallback(item, obj, self.config, self.uniq_anims)
                
                if obj.type == "MESH":
                    objectItem = self.createGeodeFromObject(obj)
                    item.children.append(objectItem)
                else:
                    self.evaluateGroup(obj, item, rootItem)

            elif obj.type == "LAMP":
                matrix = getDeltaMatrixFrom(obj.parent, obj)
                item = MatrixTransform()
                item.setName(obj.name)
                item.matrix = matrix
                lightItem = self.createLight(obj)
                anims = createAnimationsObjectAndSetCallback(item, obj, self.config, self.uniq_anims)
                item.children.append(lightItem)

            else:
                osglog.log(str("WARNING " + obj.name + " " + obj.type + " not exported"))
                return None
            
            self.uniq_objects[obj] = item
        
        if anims != None:
            self.animations += [a for a in anims if a != None]

        if rootItem is None:
            rootItem = item

        if obj.parent_type == "BONE":
            bone = findBoneInHierarchy(rootItem, obj.parent_bone)
            if bone is None:
                osglog.log(str("WARNING " + obj.parent_bone + " not found"))
            else:               
                armature = obj.parent.data
                original_pose_position = armature.pose_position
                armature.pose_position = 'REST'

                boneInWorldSpace = obj.parent.matrix_world * armature.bones[obj.parent_bone].matrix_local
                matrix = getDeltaMatrixFromMatrix(boneInWorldSpace, obj.matrix_world)
                item.matrix = matrix
                bone.children.append(item)
                
                armature.pose_position = original_pose_position

        elif parent:
            parent.children.append(item)

        children = getChildrenOf(self.config.scene, obj)
        for child in children:
            self.exportChildrenRecursively(child, item, rootItem)
        return item


    def createSkeleton(self, obj):
        osglog.log("processing Armature " + obj.name)

        roots = getRootBonesList(obj.data)

        matrix = getDeltaMatrixFrom(obj.parent, obj)
        skeleton = Skeleton(obj.name, matrix)
        for bone in roots:
            b = Bone(obj, bone)
            b.buildBoneChildren()
            skeleton.children.append(b)
        skeleton.collectBones()
        return skeleton

    def process(self):
#        Object.resetWriter()
        self.scene_name = self.config.scene.name
        osglog.log("current scene %s" % self.scene_name)
        if self.config.validFilename() is False:
            self.config.filename += self.scene_name
        self.config.createLogfile()
        
        self.setArmatureInRestMode()
        try:
            if self.config.object_selected != None:
                o = bpy.data.objects[self.config.object_selected]
                try:
                    self.config.scene.objects.active = o
                    self.config.scene.objects.selected = [o]
                except ValueError:
                    osglog.log("Error, problem happens when assigning object %s to scene %s" % (o.name, self.config.scene.name))
                    raise

            for obj in self.config.scene.objects:
                if (self.config.selected == "SELECTED_ONLY_WITH_CHILDREN" and obj.select) \
                            or (self.config.selected == "ALL" and obj.parent == None):
                        self.exportItemAndChildren(obj)
        finally:
            self.restoreArmaturePoseMode()
        
        self.postProcess()

    # OSG requires that rig geometry be a child of the skeleton,
    # but Blender does not.  Move any meshes that are modified by
    # an armature to be under the armature.
    def reparentRiggedGeodes(self, item, parent):
        if      isinstance(item, MatrixTransform) \
                and len(item.children) == 1 \
                and isinstance(item.children[0], Geode) \
                and not isinstance(parent, Skeleton):
            geode = item.children[0]
            osglog.log("geode {}".format(geode.name))
            if geode.armature_modifier != None:
                parent.children.remove(item)
                
                arm = self.uniq_objects[geode.armature_modifier.object]
                for (k, v) in self.uniq_objects.items():
                    if v == item:
                        meshobj = k
                
                item.matrix = getDeltaMatrixFromMatrix(geode.armature_modifier.object.matrix_world, meshobj.matrix_world)
                
                arm.children.append(item)
                osglog.log("NOTICE: Reparenting {} to {}".format(geode.name, arm.name))
        if hasattr(item, "children"):
            for c in list(item.children):
                self.reparentRiggedGeodes(c, item)
                
    def findBone(self, item, bonename):
        if isinstance(item, Skeleton) or isinstance(item, Bone):
            if item.name == bonename:
                return item
            for c in list(item.children):
                n = self.findBone(c, bonename)
                if n != None:
                    return n
        return None
    
    def reparentNonDeformedGeodes(self, item, parent):
        if     isinstance(item, MatrixTransform) \
                and len(item.children) == 1 \
                and isinstance(item.children[0], Geode) \
                and isinstance(parent, Skeleton):
            geode = item.children[0]
            osglog.log("optimizing armature influence on geode {}".format(geode.name))
            if geode.armature_modifier != None:
                singleBoneInfluence = True
                target = None
                for d in geode.drawables:
                    if isinstance(d, RigGeometry):
                        infcount = 0
                        for g in d.groups:
                            if g in geode.armature_modifier.object.data.bones:
                                infcount += 1
                        if infcount != 1:
                            osglog.log("must have exactly one bone influence, can't optimize")
                            singleBoneInfluence = False
                            break
                        
                        for name, grp in d.groups.items():
                            if name in geode.armature_modifier.object.data.bones:
                                if len(grp.vertexes) != len(d.vertexes.array):
                                    osglog.log("bone does not influence every vertex, can't optimize")
                                    singleBoneInfluence = False
                                    break
                                for vtx in grp.vertexes:
                                    if vtx[1] != 1.0:
                                        osglog.log("vertex has less than 1.0 weight, can't optimize")
                                        singleBoneInfluence = False
                                        break
                                target = name
                
                if singleBoneInfluence and target != None:
                    geode.drawables = [(d.sourcegeometry if isinstance(d, RigGeometry) else d) for d in geode.drawables]
                    parent.children.remove(item)
                    blendbone = geode.armature_modifier.object.data.bones[target]
                    blendbone_matrix = blendbone.matrix_local
                   
                    osgbone = self.findBone(parent, target)
                    for (k, v) in self.uniq_objects.items():
                        if v == item:
                            meshobj = k
                    
                    item.matrix = getDeltaMatrixFromMatrix(geode.armature_modifier.object.matrix_world * blendbone_matrix, meshobj.matrix_world)
                    osgbone.children.append(item)
                    osglog.log("NOTICE: Reparenting {} to {}".format(geode.name, osgbone.name))
        if hasattr(item, "children"):
            for c in list(item.children):
                self.reparentNonDeformedGeodes(c, item)

    def postProcess(self):
        # set only one root to the scene
        self.root = None
        self.root = Group()
        self.root.setName("Root")
        self.root.children = self.items
        if len(self.animations) > 0:
            animation_manager = BasicAnimationManager()
            animation_manager.animations = self.animations
            self.root.update_callbacks.append(animation_manager)
            
        self.reparentRiggedGeodes(self.root, None)
        
        if self.config.optimize_influence:
            self.reparentNonDeformedGeodes(self.root, None)

        # index light num for opengl use and enable them in a stateset
        if len(self.lights) > 0:
            st = StateSet()
            self.root.stateset = st
            if len(self.lights) > 8:
                osglog.log("WARNING more than 8 lights")

            # retrieve world to global ambient
            lm = LightModel()
            lm.ambient = (1.0, 1.0, 1.0, 1.0)
            if self.config.scene.world is not None:
                amb = self.config.scene.world.ambient_color
                lm.ambient = (amb[0], amb[1], amb[2], 1.0)

            st.attributes.append(lm)

            # add by default
            st.attributes.append(Material())

            light_num = 0
            for name, ls in self.lights.items():
                ls.light.light_num = light_num
                key = "GL_LIGHT{}".format(light_num)
                st.modes[key] = "ON"
                light_num += 1

        for key in self.uniq_stateset.keys():
            if self.uniq_stateset[key] is not None: # register images to unpack them at the end
                images = getImageFilesFromStateSet(self.uniq_stateset[key])
                for i in images:
                    self.images.add(i)

    def write(self):
        if len(self.items) == 0:
            if self.config.log_file is not None:
                self.config.closeLogfile()
            return

        filename = self.config.getFullName("osg")
        osglog.log("write file to " + filename)
        with open(filename, "wb") as sfile:
        #sfile.write(str(self.root).encode('utf-8'))
            self.root.write(sfile)
        
        nativePath = os.path.join(os.path.abspath(self.config.getFullPath()), self.config.texture_prefix)
        #blenderPath = bpy.path.relpath(nativePath)
        if len(self.images) > 0:
            try:
                if not os.path.exists(nativePath):
                    os.mkdir(nativePath)
            except:
                osglog.log("can't create textures directory {}".format(nativePath))
                raise
                
        copied_images = []
        for i in self.images:
            if i is not None:
                imagename = bpy.path.basename(createImageFilename("", i))
                try:
                    if i.packed_file:
                        original_filepath = i.filepath_raw
                        try:
                            if len(imagename.split('.')) == 1:
                                imagename += ".png"
                            filename = os.path.join(nativePath, imagename)
                            if not os.path.exists(filename):
                                # record which images that were newly copied and can be safely
                                # cleaned up
                                copied_images.append(filename)
                            i.filepath_raw = filename
                            osglog.log("packed file, save it to {}".format(os.path.abspath(bpy.path.abspath(filename))))
                            i.save()
                        except:
                            osglog.log("failed to save file {} to {}".format(imagename, nativePath))
                        i.filepath_raw = original_filepath
                    else:
                        filepath = os.path.abspath(bpy.path.abspath(i.filepath))
                        texturePath = os.path.join(nativePath, imagename)
                        if os.path.exists(filepath):
                            if not os.path.exists(texturePath):
                                # record which images that were newly copied and can be safely
                                # cleaned up
                                copied_images.append(texturePath)
                            shutil.copy(filepath, texturePath)
                            osglog.log("copy file {} to {}".format(filepath, texturePath))
                        else:
                            osglog.log("file {} not available".format(filepath))
                except Exception  as e:
                    osglog.log("error while trying to copy file {} to {}: {}".format(imagename, nativePath, str(e)))

        filetoview = self.config.getFullName("osg")
        if self.config.run_osgconv:
            if self.config.osgconv_embed_textures:
                r = [self.config.osgconv_path, "-O", "includeImageFileInIVEFile", self.config.getFullName("osg"), self.config.getFullName(self.config.osgconv_ext)]
            else:
                r = [self.config.osgconv_path, "-O", "noTexturesInIVEFile", self.config.getFullName("osg"), self.config.getFullName(self.config.osgconv_ext)]
            try:
                osglog.log("Executing osgconv: " + str(r))
                if subprocess.call(r) == 0:
                    filetoview = self.config.getFullName(self.config.osgconv_ext)
                    if self.config.osgconv_cleanup:
                        os.unlink(self.config.getFullName("osg"))
                        if self.config.osgconv_embed_textures:
                            for i in copied_images:
                                os.unlink(i)
            except Exception as e:
                print("Error running osgconv")
                print(repr(e))
            
        if self.config.run_viewer:
            r = [self.config.viewer_path, filetoview]
            try:
                subprocess.Popen(r)
            except Exception as e:
                print("Error running " + str(r))
                print(repr(e))

        if self.config.log_file is not None:
            self.config.closeLogfile()
            

    def createGeodeFromObject(self, mesh, skeleton = None):
        osglog.log("exporting object " + mesh.name)

        # check if the mesh has a armature modifier
        # if no we don't write influence
        exportInfluence = False

        #if mesh.parent and mesh.parent.type == "ARMATURE":
        #    exportInfluence = True
        
        armature_modifier = None
        has_non_armature_modifiers = False
        
        for mod in mesh.modifiers:
            if mod.type == "ARMATURE":
                armature_modifier = mod
            else:
                has_non_armature_modifiers = True
        
        if armature_modifier != None:
            exportInfluence = True
 
        if self.config.apply_modifiers and has_non_armature_modifiers:
            mesh_object = mesh.to_mesh(self.config.scene, True, 'PREVIEW')
        else:
            mesh_object = mesh.data
         
        osglog.log("mesh_object is " + mesh_object.name)
        
        if mesh_object in self.uniq_geodes:
            return self.uniq_geodes[mesh_object]

        hasVertexGroup = False
        
        for vertex in mesh_object.vertices:
            if len(vertex.groups) > 0:
                hasVertexGroup = True
                break

        geometries = []
        converter = BlenderObjectToGeometry(object = mesh, mesh = mesh_object,
                                            config = self.config, 
                                            uniq_stateset = self.uniq_stateset)
        sources_geometries = converter.convert()

        osglog.log("vertex groups %s %s " % (exportInfluence, hasVertexGroup))
        if exportInfluence and hasVertexGroup:
            for geom in sources_geometries:
                rig_geom = RigGeometry()
                rig_geom.sourcegeometry = geom
                rig_geom.copyFrom(geom)
                rig_geom.groups = geom.groups
                geometries.append(rig_geom)
        else:
            geometries = sources_geometries
            
        geode = Geode()
        geode.setName(mesh_object.name)
        geode.armature_modifier = armature_modifier

        if len(geometries) > 0:
            for geom in geometries:
                geode.drawables.append(geom)
            for name in converter.material_animations.keys():
                self.animations.append(converter.material_animations[name])
                
        self.uniq_geodes[mesh_object] = geode
                
        return geode

    def createLight(self, obj):
        converter = BlenderLightToLightSource(lamp=obj)
        lightsource = converter.convert()
        self.lights[lightsource.name] = lightsource # will be used to index lightnum at the end
        return lightsource


class BlenderLightToLightSource(object):
    def __init__(self, *args, **kwargs):
        self.object = kwargs["lamp"]
        self.lamp = self.object.data

    def convert(self):
        ls = LightSource()
        ls.setName(self.object.name)
        light = ls.light
        energy = self.lamp.energy
        light.ambient = (1.0, 1.0, 1.0, 1.0)
        light.diffuse = (self.lamp.color[0] * energy, self.lamp.color[1]* energy, self.lamp.color[2] * energy,1.0) # put light to 0 it will inherit the position from parent transform
        light.specular = (energy, energy, energy, 1.0) #light.diffuse

        # Lamp', 'Sun', 'Spot', 'Hemi', 'Area', or 'Photon
        if self.lamp.type == 'POINT' or self.lamp.type == 'SPOT':
            # position light
            # Note DW - the distance may not be necessary anymore (blender 2.5)
            light.position = (0,0,0,1) # put light to vec3(0) it will inherit the position from parent transform
            light.linear_attenuation = self.lamp.linear_attenuation / self.lamp.distance
            light.quadratic_attenuation = self.lamp.quadratic_attenuation / self.lamp.distance

        elif self.lamp.type == 'SUN':
            light.position = (0,0,1,0) # put light to 0 it will inherit the position from parent transform

        if self.lamp.type == 'SPOT':
            light.spot_cutoff = math.degrees(self.lamp.spot_size * .5)
            if light.spot_cutoff > 90:
                light.spot_cutoff = 180
            light.spot_exponent = 128.0 * self.lamp.spot_blend
            
        return ls

class BlenderObjectToGeometry(object):
    def __init__(self, *args, **kwargs):
        self.object = kwargs["object"]
        self.config = kwargs.get("config", None)
        if not self.config:
            self.config = osgconf.Config()
        self.uniq_stateset = kwargs.get("uniq_stateset", {})
        self.uniq_anims = kwargs.get("uniq_anims", {})
        self.geom_type = Geometry
        self.mesh = kwargs.get("mesh", None)
        
        #if self.config.apply_modifiers is False:
        #  self.mesh = self.object.data
        #else:
        #  self.mesh = self.object.to_mesh(self.config.scene, True, 'PREVIEW')
        self.material_animations = {}

    def createTexture2D(self, mtex):
        image_object = None
        try: 
            image_object = mtex.texture.image
        except: 
            image_object = None
        if image_object is None:
            osglog.log("WARNING the texture %s has no Image, skip it" % str(mtex))
            return None
        texture = Texture2D()
        texture.name = mtex.texture.name

        # reference texture relative to export path
        filename = createImageFilename(self.config.texture_prefix, image_object)
        texture.file = filename
        texture.source_image = image_object
        return texture

    def adjustUVLayerFromMaterial(self, geom, material):
        uvs = geom.uvs
        if DEBUG: osglog.log("geometry uvs %s" % (str(uvs)))
        geom.uvs = {}

        texture_list = material.texture_slots
        if DEBUG: osglog.log("texture list %s" % str(texture_list))

        # find a default channel if exist uv
        default_uv = None
        default_uv_key = None
        if (len(uvs)) == 1:
            default_uv_key, default_uv = uvs.popitem()

        for i in range(0, len(texture_list)):
            if texture_list[i] is not None:
                uv_layer =  texture_list[i].uv_layer

                if len(uv_layer) > 0 and not uv_layer in uvs.keys():
                    osglog.log("WARNING your material '%s' with texture '%s' use an uv layer '%s' that does not exist on the mesh '%s', use the first uv channel as fallback" % (material.name, texture_list[i], uv_layer, geom.name))
                if len(uv_layer) > 0 and uv_layer in uvs.keys():
                    if DEBUG: osglog.log("texture %s use uv layer %s" % (i, uv_layer))
                    geom.uvs[i] = TexCoordArray()
                    geom.uvs[i].array = uvs[uv_layer].array
                    geom.uvs[i].index = i
                elif default_uv:
                    if DEBUG: osglog.log("texture %s use default uv layer %s" % (i, default_uv_key))
                    geom.uvs[i] = TexCoordArray()
                    geom.uvs[i].index = i
                    geom.uvs[i].array = default_uv.array

        # adjust uvs channels if no textures assigned
        if len(geom.uvs.keys()) == 0:
            if DEBUG: osglog.log("no texture set, adjust uvs channels, in arbitrary order")
            index = 0
            for k in uvs.keys():
                uvs[k].index = index
                index += 1
            geom.uvs = uvs
        return

    def createStateSet(self, index_material, mesh, geom):
        s = StateSet()
        if len(mesh.materials) > 0:
            mat_source = mesh.materials[index_material]
            if mat_source in self.uniq_stateset.keys():
                #s = ShadowObject(self.uniq_stateset[mat_source])
                s = self.uniq_stateset[mat_source]
                return s

            if mat_source is not None:
                self.uniq_stateset[mat_source] = s
                m = Material()
                m.setName(mat_source.name)
                s.setName(mat_source.name)

                #bpy.ops.object.select_name(name=self.object.name)
                anim = createAnimationMaterialAndSetCallback(m, mat_source, self.config, self.uniq_anims)
                if anim :
                    self.material_animations[anim.name] = anim

                if mat_source.use_shadeless:
                    s.modes["GL_LIGHTING"] = "OFF"

                alpha = 1.0
                if mat_source.use_transparency:
                    alpha = 1.0 - mat_source.alpha

                refl = mat_source.diffuse_intensity
                m.diffuse = (mat_source.diffuse_color[0] * refl, mat_source.diffuse_color[1] * refl, mat_source.diffuse_color[2] * refl, alpha)

                # if alpha not 1 then we set the blending mode on
                if DEBUG: osglog.log("state material alpha %s" % str(alpha))
                if alpha != 1.0:
                    s.modes["GL_BLEND"] = "ON"

                ambient_factor = mat_source.ambient
                if bpy.context.scene.world:
                    m.ambient =((bpy.context.scene.world.ambient_color[0])*ambient_factor,
                                (bpy.context.scene.world.ambient_color[1])*ambient_factor,
                                (bpy.context.scene.world.ambient_color[2])*ambient_factor,
                                1.0)
                else:
                    m.ambient = (0, 0, 0, 1.0)
                spec = mat_source.specular_intensity
                m.specular = (mat_source.specular_color[0] * spec, mat_source.specular_color[1] * spec, mat_source.specular_color[2] * spec, 1)

                emissive_factor = mat_source.emit
                m.emission = (mat_source.diffuse_color[0] * emissive_factor, mat_source.diffuse_color[1] * emissive_factor, mat_source.diffuse_color[2] * emissive_factor, 1)
                m.shininess = (mat_source.specular_hardness / 512.0) * 128.0

                s.attributes.append(m)

                texture_list = mat_source.texture_slots
                if DEBUG: osglog.log("texture list %s" % str(texture_list))

                for i in range(0, len(texture_list)):
                    if texture_list[i] is not None:
                        t = self.createTexture2D(texture_list[i])
                        if DEBUG: osglog.log("texture %s %s" % (i, texture_list[i]))
                        if t is not None:
                            if not i in s.texture_attributes.keys():
                                s.texture_attributes[i] = []
                            s.texture_attributes[i].append(t)
                            try:
                                if t.source_image.getDepth() > 24: # there is an alpha
                                    s.modes["GL_BLEND"] = "ON"
                            except:
                                pass
                                # happens for all generated textures
                                #log("can't read the source image file for texture %s" % t.name)
                #if DEBUG: osglog.log("state set %s" % str(s))
        return s

    def createGeomForMaterialIndex(self, material_index, mesh):
        geom = Geometry()
        geom.groups = {}
        if (len(mesh.faces) == 0):
            osglog.log("object %s has no faces, so no materials" % self.object.name)
            return None
        if len(mesh.materials) and mesh.materials[material_index] != None:
            material_name = mesh.materials[material_index].name
            title = "mesh %s with material %s" % (self.object.name, material_name)
        else:
            title = "mesh %s without material" % (self.object.name)
        osglog.log(title)

        vertexes = []
        collected_faces = []
        for face in mesh.faces:
            if face.material_index != material_index:
                continue
            f = []
            if DEBUG: fdebug = []
            for vertex in face.vertices:
                index = len(vertexes)
                vertexes.append(mesh.vertices[vertex])
                f.append(index)
                if DEBUG: fdebug.append(vertex)
            if DEBUG: osglog.log("true face %s" % str(fdebug))
            if DEBUG: osglog.log("face %s" % str(f))
            collected_faces.append((face,f))

        if (len(collected_faces) == 0):
            osglog.log("object %s has no faces for sub material slot %s" % (self.object.name, str(material_index)))
            end_title = '-' * len(title)
            osglog.log(end_title)
            return None

        # colors = {}
        # if mesh.vertex_colors:
        #     names = mesh.getColorLayerNames()
        #     backup_name = mesh.activeColorLayer
        #     for name in names:
        #         mesh.activeColorLayer = name
        #         mesh.update()
        #         color_array = []
        #         for face,f in collected_faces:
        #             for i in range(0, len(face.vertices)):
        #                 color_array.append(face.col[i])
        #         colors[name] = color_array
        #     mesh.activeColorLayer = backup_name
        #     mesh.update()
        colors = {}
        if mesh.vertex_colors:
            backupColor = None
            for colorLayer in mesh.vertex_colors:
                if colorLayer.active:
                    backupColor = colorLayer
            for colorLayer in mesh.vertex_colors:
                idx = 0
                colorLayer.active= True
                mesh.update()
                color_array = []
                for data in colorLayer.data:
                    color_array.append(data.color1)
                    color_array.append(data.color2)
                    color_array.append(data.color3)
                    # DW - how to tell if this is a tri or a quad?
                    if len(mesh.faces[idx].vertices) > 3:
                        color_array.append(data.color4)
                    idx += 1
                colors[colorLayer.name] = color_array
            backupColor.active = True
            mesh.update()

        # uvs = {}
        # if mesh.faceUV:
        #     names = mesh.getUVLayerNames()
        #     backup_name = mesh.activeUVLayer
        #     for name in names:
        #         mesh.activeUVLayer = name
        #         mesh.update()
        #         uv_array = []
        #         for face,f in collected_faces:
        #             for i in range(0, len(face.vertices)):
        #                 uv_array.append(face.uv[i])
        #         uvs[name] = uv_array
        #     mesh.activeUVLayer = backup_name
        #     mesh.update()
        uvs = {}
        if mesh.uv_textures:
            backup_texture = None
            for textureLayer in mesh.uv_textures:
                if textureLayer.active:
                    backup_texture = textureLayer


            for textureLayer in mesh.uv_textures:
                textureLayer.active = True
                mesh.update()
                uv_array = []

                for face,f in collected_faces:
                    data = textureLayer.data[face.index]
                    uv_array.append(data.uv1)
                    uv_array.append(data.uv2)
                    uv_array.append(data.uv3)
                    if len(face.vertices) > 3:
                        uv_array.append(data.uv4)
                uvs[textureLayer.name] = uv_array
            backup_texture.active = True
            mesh.update()

        normals = []
        for face,f in collected_faces:
            if face.use_smooth:
                for vert in face.vertices:
                    normals.append(mesh.vertices[vert].normal)
            else:
                for vert in face.vertices:
                    normals.append(face.normal)

        mapping_vertexes = []
        merged_vertexes = []
        tagged_vertexes = []
        for i in range(0,len(vertexes)):
            merged_vertexes.append(i)
            tagged_vertexes.append(False)

        def truncateFloat(value, digit = 5):
            return round(value, digit)

        def truncateVector(vector, digit = 5):
            for i in range(0,len(vector)):
                vector[i] = truncateFloat(vector[i], digit)
            return vector

        def get_vertex_key(index):
            return (
                (truncateFloat(vertexes[index].co[0]), truncateFloat(vertexes[index].co[1]), truncateFloat(vertexes[index].co[2])),

                (truncateFloat(normals[index][0]), truncateFloat(normals[index][1]), truncateFloat(normals[index][2])),
                tuple([tuple(truncateVector(uvs[x][index])) for x in uvs.keys()]))
                # vertex color not supported
                #tuple([tuple(truncateVector(colors[x][index])) for x in colors.keys()]))

        # Build a dictionary of indexes to all the vertexes that
        # are equal.
        vertex_dict = {}
        for i in range(0, len(vertexes)):
            key = get_vertex_key(i)
            if DEBUG: osglog.log("key %s" % str(key))
            if key in vertex_dict.keys():
                vertex_dict[key].append(i)
            else:
                vertex_dict[key] = [i]

        for i in range(0, len(vertexes)):
            if tagged_vertexes[i] is True: # avoid processing more than one time a vertex
                continue
            index = len(mapping_vertexes)
            merged_vertexes[i] = index
            mapping_vertexes.append([i])
            if DEBUG: osglog.log("process vertex %s" % i)
            vertex_indexes = vertex_dict[get_vertex_key(i)]
            for j in vertex_indexes:
                if j <= i:
                    continue
                if tagged_vertexes[j] is True: # avoid processing more than one time a vertex
                    continue
                if DEBUG: osglog.log("   vertex %s is the same" % j)
                merged_vertexes[j] = index
                tagged_vertexes[j] = True
                mapping_vertexes[index].append(j)

        if DEBUG:
            for i in range(0, len(mapping_vertexes)):
                osglog.log("vertex %s contains %s" % (str(i), str(mapping_vertexes[i])))

        if len(mapping_vertexes) != len(vertexes):
            osglog.log("vertexes reduced from %s to %s" % (str(len(vertexes)),len(mapping_vertexes)))
        else:
            osglog.log("vertexes %s" % str(len(vertexes)))

        faces = []
        for (original, face) in collected_faces:
            f = []
            if DEBUG: fdebug = []
            for v in face:
                f.append(merged_vertexes[v])
                if DEBUG: fdebug.append(vertexes[mapping_vertexes[merged_vertexes[v]][0]].index)
            faces.append(f)
            if DEBUG: osglog.log("new face %s" % str(f))
            if DEBUG: osglog.log("true face %s" % str(fdebug))
            
        osglog.log("faces %s" % str(len(faces)))

        vgroups = {}
        original_vertexes2optimized = {}
        for i in range(0, len(mapping_vertexes)):
            for k in mapping_vertexes[i]:
                index = vertexes[k].index
                if not index in original_vertexes2optimized.keys():
                    original_vertexes2optimized[index] = []
                original_vertexes2optimized[index].append(i)

        # for i in mesh.getVertGroupNames():
        #    verts = {}
        #    for idx, weight in mesh.getVertsFromGroup(i, 1):
        #        if weight < 0.001:
        #            log( "WARNING " + str(idx) + " to has a weight too small (" + str(weight) + "), skipping vertex")
        #            continue
        #        if idx in original_vertexes2optimized.keys():
        #            for v in original_vertexes2optimized[idx]:
        #                if not v in verts.keys():
        #                    verts[v] = weight
        #                #verts.append([v, weight])
        #    if len(verts) == 0:
        #        log( "WARNING " + str(i) + " has not vertexes, skip it, if really unsued you should clean it")
        #    else:
        #        vertex_weight_list = [ list(e) for e in verts.items() ]
        #        vg = VertexGroup()
        #        vg.targetGroupName = i
        #        vg.vertexes = vertex_weight_list
        #        vgroups[i] = vg

        #blenObject = None
        #for obj in bpy.context.blend_data.objects:
        #    if obj.data == mesh:
        #        blenObject = obj

        for vertex_group in self.object.vertex_groups:
            #osglog.log("Look at vertex group: " + repr(vertex_group))
            verts = {}
            for idx in range(0, len(mesh.vertices)):
                weight = 0

                for vg in mesh.vertices[idx].groups:
                    if vg.group == vertex_group.index:
                        weight = vg.weight
                if weight >= 0.001:
                    if idx in original_vertexes2optimized.keys():
                        for v in original_vertexes2optimized[idx]:
                            if not v in verts.keys():
                                verts[v] = weight
                    
            if len(verts) == 0:
                osglog.log( "WARNING group has no vertexes, skip it, if really unsued you should clean it")
            else:
                vertex_weight_list = [ list(e) for e in verts.items() ]
                vg = VertexGroup()
                vg.targetGroupName = vertex_group.name
                vg.vertexes = vertex_weight_list
                vgroups[vertex_group.name] = vg

        if (len(vgroups)):
            osglog.log("vertex groups %s" % str(len(vgroups)))
        geom.groups = vgroups
        
        osg_vertexes = VertexArray()
        osg_normals = NormalArray()
        osg_uvs = {}
        #osg_colors = {}
        for vertex in mapping_vertexes:
            vindex = vertex[0]
            coord = vertexes[vindex].co
            osg_vertexes.array.append([coord[0], coord[1], coord[2] ])

            ncoord = normals[vindex]
            osg_normals.array.append([ncoord[0], ncoord[1], ncoord[2]])

            for name in uvs.keys():
                if not name in osg_uvs.keys():
                    osg_uvs[name] = TexCoordArray()
                osg_uvs[name].array.append(uvs[name][vindex])

        if (len(osg_uvs)):
            osglog.log("uvs channels %s - %s" % (len(osg_uvs), str(osg_uvs.keys())))

        nlin = 0
        ntri = 0
        nquad = 0
        # counting number of lines, triangles and quads
        for face in faces:
            nv = len(face)
            if nv == 2:
                nlin = nlin + 1
            elif nv == 3:
                ntri = ntri + 1
            elif nv == 4:
                nquad = nquad + 1
            else:
                osglog.log("WARNING can't manage faces with %s vertices" % nv)

        # counting number of primitives (one for lines, one for triangles and one for quads)
        numprims = 0
        if (nlin > 0):
            numprims = numprims + 1
        if (ntri > 0):
            numprims = numprims + 1
        if (nquad > 0):
            numprims = numprims + 1

        # Now we write each primitive
        primitives = []
        if nlin > 0:
            lines = DrawElements()
            lines.type = "LINES"
            nface=0
            for face in faces:
                nv = len(face)
                if nv == 2:
                    lines.indexes.append(face[0])
                    lines.indexes.append(face[1])
                nface = nface + 1
            primitives.append(lines)

        if ntri > 0:
            triangles = DrawElements()
            triangles.type = "TRIANGLES"
            nface=0
            for face in faces:
                nv = len(face)
                if nv == 3:
                    triangles.indexes.append(face[0])
                    triangles.indexes.append(face[1])
                    triangles.indexes.append(face[2])
                nface = nface + 1
            primitives.append(triangles)

        if nquad > 0:
            quads = DrawElements()
            quads.type = "QUADS"
            nface=0
            for face in faces:
                nv = len(face)
                if nv == 4:
                    quads.indexes.append(face[0])
                    quads.indexes.append(face[1])
                    quads.indexes.append(face[2])
                    quads.indexes.append(face[3])
                nface = nface + 1
            primitives.append(quads)

        geom.uvs = osg_uvs
        #geom.colors = osg_colors
        geom.vertexes = osg_vertexes
        geom.normals = osg_normals
        geom.primitives = primitives
        geom.setName(self.object.name)
        geom.stateset = self.createStateSet(material_index, mesh, geom)

        if len(mesh.materials) > 0 and mesh.materials[material_index] is not None:
            self.adjustUVLayerFromMaterial(geom, mesh.materials[material_index])

        end_title = '-' * len(title)
        osglog.log(end_title)
        return geom

    def process(self, mesh):
        geometry_list = []
        material_index = 0
        if len(mesh.materials) == 0:
            geom = self.createGeomForMaterialIndex(0, mesh)
            if geom is not None:
                geometry_list.append(geom)
        else:
            for material in mesh.materials:
                geom = self.createGeomForMaterialIndex(material_index, mesh)
                if geom is not None:
                    geometry_list.append(geom)
                material_index += 1
        return geometry_list

    def convert(self):
        # looks like this was dropped
        # if self.mesh.vertexUV:
        #     osglog.log("WARNING mesh %s use sticky UV and it's not supported" % self.object.name)

        list = self.process(self.mesh)
        return list

class BlenderObjectToRigGeometry(BlenderObjectToGeometry):
    def __init__(self, *args, **kwargs):
        BlenderObjectToGeometry.__init__(self, *args, **kwargs)
        self.geom_type = RigGeometry


class BlenderAnimationToAnimation(object):
    def __init__(self, *args, **kwargs):
        self.config = kwargs["config"]
        self.object = kwargs.get("object", None)
        self.uniq_anims = kwargs.get("uniq_anims", {})
        self.animations = None
        self.action = None
        self.action_name = None

    def createAnimation(self, target=None, prefix=""):

        # track could be interesting, to export multi animation but we would need to be able to associate different track to an animation. Why ?
        # because track are used to compose an animation base on different action
        # so it makes more sense to compose your animation with different track
        # and then bake it into one Action

        # for game export or more complex exporter. It's better to adjust the osgExport
        # in python and merge your actions as you want. I did it for the game pokme,
        # the osgExporter is able to be used by other scripts


        # nla_tracks = []
        # if hasattr(self.object, "animation_data") and hasattr(self.object.animation_data, "nla_tracks"):
        #     nla_tracks = self.object.animation_data.nla_tracks
        #     if len(nla_tracks) == 0:
        #         action = self.object.animation_data.action

        # osglog.log("create animation for %s" % self.object.name)
        # anims = []
        # if len(nla_tracks) > 0:
        #     osglog.log("found tracks %d" % (len(nla_tracks)))
        #     for nla_track in nla_tracks:
        #         osglog.log("found track %s" % str(nla_track))
        #         anim = self.createAnimationFromTrack(self.object.name, nla_track)
        #         anims.append(anim)
        
        osglog.log("Exporting animation on object " + str(self.object))
        
        if self.action == None:
            need_bake = False
            
            if hasattr(self.object, "animation_data") and hasattr(self.object.animation_data, "action") and self.object.animation_data.action != None:
                self.action_name = self.object.animation_data.action.name
            
            if hasattr(self.object, "constraints") and (len(self.object.constraints) > 0) and self.config.bake_constraints:
                osglog.log("Baking constraints " + str(self.object.constraints))
                need_bake = True
            else:
                if hasattr(self.object, "animation_data") and hasattr(self.object.animation_data, "action"):
                    self.action = self.object.animation_data.action
                    for fcu in self.action.fcurves:
                        for kf in fcu.keyframe_points:
                            if kf.interpolation != 'LINEAR':
                                need_bake = True
                                
            if need_bake:
                self.action = osgbake.bake(self.config.scene,
                         self.object,
                         self.config.scene.frame_start, 
                         self.config.scene.frame_end,
                         self.config.bake_frame_step,
                         False, #only_selected
                         True,  #do_pose
                         True,  #do_object
                         False, #do_constraint_clear
                         False) #to_quat

        if self.action != None:
            osglog.log("found action %s, prefix is %s" % (self.action.name, prefix))
            
            # Sharing animation channels isn't possible with the osg 2.8 file format reader
            # so we have to export a separate channel for every object it applies to.
            # Keeping the following code there for future reference, though.
            #if self.action in self.uniq_anims:
            #    return self.uniq_anims[self.action]
            
            if target == None:
                target = self.object.name
            
            anim = self.createAnimationFromAction(target, self.action_name, self.action, prefix)

            osglog.log("uniq_anims ".format(self.uniq_anims))
            
            if self.action in self.uniq_anims:
                add_to_anim = self.uniq_anims[self.action]
                add_to_anim.channels = add_to_anim.channels + anim.channels
                return add_to_anim
            else:
                self.uniq_anims[self.action] = anim
                return anim
        else:
            return None

    #def createAnimationFromTrack(self, name, track):
    #    animation = Animation()
    #    animation.setName(name)
    #
    #    actions = []
    #    if track:
    #        for strip in track.strips:
    #            actions.append(strip.action)
    #
    #    self.convertActionsToAnimation(animation, actions)
    #    self.animation = animation
    #    return animation

    def createAnimationFromAction(self, target, name, action, prefix):
        animation = Animation()
        animation.setName(name)
        self.convertActionsToAnimation(target, animation, action, prefix)
        self.animation = animation
        return animation

    def convertActionsToAnimation(self, target, anim, action, prefix):
        channels = exportActionsToKeyframeSplitRotationTranslationScale(target, action, self.config.anim_fps, prefix)
        for i in channels:
            anim.channels.append(i)


def getChannel(target, action, fps, data_path, array_indexes):
    times = []
    duration = 0
    fcurves = []
    
    for array_index in array_indexes:
        for fcurve in action.fcurves:
            #osglog.log("fcurves %s %s matches %s %s " %(fcurve.data_path, fcurve.array_index, data_path, array_index))
            if fcurve.data_path == data_path and fcurve.array_index == array_index:
                fcurves.append(fcurve)
                #osglog.log("yes")
            
    if len(fcurves) == 0:
        return None
        
    
    for fcurve in fcurves:
        for keyframe in fcurve.keyframe_points:
            if times.count(keyframe.co[0]) == 0:
                times.append(keyframe.co[0])
    
    if len(times) == 0:
        return None
        
    channel = Channel()
    channel.target = target
    
    if len(array_indexes) == 1:
        channel.type = "FloatLinearChannel"
    if len(array_indexes) == 3:
        channel.type = "Vec3LinearChannel"
    if len(array_indexes) == 4:
        channel.type = "QuatSphericalLinearChannel"
    
    times.sort()
    
    for time in times:
        realtime = (time) / fps
        osglog.log("time {} {} {}".format(time, realtime, fps))

        # realtime = time
        if realtime > duration:
            duration = realtime

        value = [realtime]
        for fcurve in fcurves:
            value.append(fcurve.evaluate(time))
        channel.keys.append(value)
    
    return channel

# as for blender 2.49
def exportActionsToKeyframeSplitRotationTranslationScale(target, action, fps, prefix):
    channels = []

    translate = getChannel(target, action, fps, prefix+"location", [0, 1, 2])
    if translate:
        translate.setName("translate")
        channels.append(translate)

    euler = []
    eulerName = [ "euler_x", "euler_y", "euler_z"]
    for i in range(0,3):
        c = getChannel(target, action, fps, prefix+"rotation_euler", [i])
        if c:
            c.setName(eulerName[i])
            channels.append(c)

    quaternion = getChannel(target, action, fps, prefix+"rotation_quaternion", [1, 2, 3, 0])
    if quaternion:
        quaternion.setName("quaternion")
        channels.append(quaternion)
        
    axis_angle = getChannel(target, action, fps, prefix+"rotation_axis_angle", [1, 2, 3, 0])
    if axis_angle:
        axis_angle.setName("axis_angle")
        channels.append(axis_angle)

    scale = getChannel(target, action, fps, prefix+"scale", [0, 1, 2])
    if scale:
        scale.setName("scale")
        channels.append(scale)

    return channels

    
