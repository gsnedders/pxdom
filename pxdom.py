""" pxdom - stand-alone embeddable pure-Python DOM implementation and
    non-validating parser conforming to DOM Level 3 Core/XML and Load/Save
    (based on the February 2004 Proposed Recommendations).
"""

__version__= 1,0
__author__ = 'Andrew Clover <and@doxdesk.com>'
__date__   = '13 February 2004'
__all__    = [
  'getDOMImplementation', 'getDOMImplementations', 'parse', 'parseString'
]


# Setup, utility functions
# ============================================================================

import os, sys, string, StringIO, urlparse, urllib, httplib
r= string.replace

def _insertMethods():
  """ In this source, not all members are defined directly inside their class
      definitions; some are organised into aspects and defined together later
      in the file, to improve readability. This function is called at the end
      to combine the externally-defined members, whose names are in the format
      _class__member, into the classes they are meant to be in.
  """
  for key, value in globals().items():
    if key[:1]=='_' and string.find(key, '__')>=1:
      class_, method= string.split(key[1:], '__', 1)
      setattr(globals()[class_], method, value)


# Backwards-compatibility boolean type (<2.2.3)
#
try:
  True
except NameError:
  globals()['True'], globals()['False']= None is None, None is not None


# Check unicode is supported (Python 1.6+) and find width of character string
# (in Python 2.2+ it can be 16 or 32 bits depending on compile option).
#
try:
  unicode
except NameError:
  globals()['unicode']= None
  unicodedata= None
  nativeEncoding= 'utf-8'
else:
  import unicodedata
  if getattr(sys, 'maxunicode', 0)>0xFFFF:
    nativeEncoding= 'utf-32'
  else:
    nativeEncoding= 'utf-16'

# Extra line separator chars for XML 1.1
#
if unicode is not None:
  EBCLS= unichr(0x85)
  UNILS= unichr(0x2028)
else:
  EBCLS= chr(0x85)
  UNILS= ''


# Unicode character normalisation (>=2.3). Also includes a kludge for
# composing-characters that we can't check through unicodedata, see
# 'Character Model for the World Wide Web', Appendix C
#
CNORM= False
if unicode is not None:
  if hasattr(unicodedata, 'normalize'):
    CNORM= True
    EXTRACOMPOSERS= string.join(map(unichr, [
      0x09BE, 0x09D7, 0x0B3E, 0x0B56, 0x0B57, 0x0BBE, 0x0BD7, 0x0CC2, 0x0CD5,
      0x0CD6, 0x0D3E, 0x0D57, 0x0DCF, 0x0DDF, 0x0FB5, 0x0FB7, 0x102E
    ] + range(0x1161, 0x1176) + range(0x11A8, 0x11C2) ), '')
def _identity(x, y= None):
  """ Null character normalisation function, doesn't do anything.
  """
  return x

def dictadd(a, b):
  ab= a.copy()
  ab.update(b)
  return ab

# Special namespace URIs
#
XMNS= 'http://www.w3.org/XML/1998/namespace'
NSNS= 'http://www.w3.org/2000/xmlns/'
DTNS= 'http://www.w3.org/TR/REC-xml'

class _NONS:
  """ Singleton value type used internally as a value for namespaceURI
      signifying that a non-namespace version of a node or method is in use;
      the accompanying localName is then the complete nodeName. This is
      different to None, which is a null namespace value.
  """
  def __str__(self):
    return '(non-namespace)'
NONS= _NONS()


# Name token utilities
#
_NOTTEXT= string.join(map(chr, range(32)), '')
_NOTNAME= _NOTTEXT+' !"#$%&\'()*+,/;<=>?@[\\]^`{|}~\x7F'
_NOTFIRST= _NOTNAME+'.-0123456789'

def _checkName(name, nc= False):
  """ Check name string, raise exception if not well-formed. Optionally check
      it also matches NCName (no colons).
  """
  if name=='':
    raise InvalidCharacterErr(name, '')
  if name[0] in _NOTFIRST:
    raise InvalidCharacterErr(name, name[0])
  for char in name[1:]:
    if char in _NOTNAME:
      raise InvalidCharacterErr(name, char)
  if nc and ':' in name:
      raise NamespaceErr(name, None)

def _splitName(name):
  """ Utility function to split a qualified name into prefix and localName.
      prefix may be None if no prefix is used; both will be None if the name
      is not a valid qualified name.
  """
  parts= string.split(name, ':', 2)
  if len(parts)==2 and '' not in parts:
    return tuple(parts)
  if len(parts)==1:
    return (None, name)
  return (None, None)


class DOMObject:
  """ Base class that allows access to properties through calling getter and
      setter methods of the form _get_propertyName. Immutable properties can
      be made by providing no _set_propertyName method; immutable objects are
      made by setting the readonly property.
  """
  def __init__(self, readonly= False):
    self._readonly= readonly
  def _get_readonly(self):
    return self._readonly
  def _set_readonly(self, value):
    self._readonly= value

  def __getattr__(self, key):
    if key[:1]=='_':
      raise AttributeError, key
    try:
      getter= getattr(self, '_get_'+key)
    except AttributeError:
      raise AttributeError, key
    return getter()

  def __setattr__(self, key, value):
    if key[:1]=='_':
      self.__dict__[key]= value
      return

    # When an object is readonly, there are a few attributes that can be set
    # regardless. Readonly is one (obviously), but due to a nasty hack in the
    # DOM spec it must also be possible to set nodeValue and textContent to
    # anything on nodes where these properties are defined to be null (with no
    # effect).
    #
    if self._readonly and key not in ('readonly', 'nodeValue', 'textContent'):
      raise NoModificationAllowedErr(self, key)
    try:
      setter= getattr(self, '_set_'+key)
    except AttributeError:
      if hasattr(self, '_get_'+key):
        raise NoModificationAllowedErr(self, key)
      raise AttributeError, key
    setter(value)


# Node-structure classes
# ============================================================================

class DOMList(DOMObject):
  """ A list structure that can be accessed either using the DOM IDL methods
      or Python list accessor constructs.
  """
  def __init__(self, initial= None):
    DOMObject.__init__(self)
    if initial is None:
      self._list= []
    else:
      self._list= initial

  # DOM-style methods
  #
  def _get_length(self):
    return len(self._list)

  def item(self, index):
    if index<0 or index>=len(self._list):
      return None
    return self._list[index]

  def contains(self, str):
    return str in self._list

  # Python-style methods
  #
  def __len__(self):
    return len(self._list)

  def __getitem__(self, index):
    return self._list[index]

  def __setitem__(self, index, value):
    raise NoModificationAllowedErr(self, 'item(%s)' % str(index))

  def __delitem__(self, index):
    raise NoModificationAllowedErr(self, 'item(%s)' % str(index))

  # Mutable sequence convenience methods for internal use
  #
  def _index(self, value):
    return self._list.index(value)

  def _append(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'item(%s)' % str(len(self._list)))
    self._list.append(value)

  def _insertseq(self, index, values):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'item(%s)' % str(index))
    self._list[index:index]= values


class NodeList(DOMList):
  """ Abstract list of nodes dependent on an owner node.
  """
  def __init__(self, ownerNode= None):
    DOMList.__init__(self)
    self._ownerNode= ownerNode


class ChildNodeList(NodeList):
  """ A NodeList of children of the owner node. Alterations to the list result
      in calls to the parent's DOM methods (this seems to be required by the
      Python DOM bindings, although never actually used in practice).
  """
  def __setitem__(self, index, value):
    self._ownerNode.replaceChild(value, self._list[index])

  def __delitem__(self, index):
    self._ownerNode.removeChild(self._list[index])


class NodeListByTagName(NodeList):
  """ A NodeList returned by an Element.getElementsByTagName[NS] method. This
      is still 'live' - the internal _list acts only as a cache, and is
      recalculated if the owner Element's contents have changed since it was
      last built.
  """
  def __init__(self, ownerNode, namespaceURI, localName):
    NodeList.__init__(self, ownerNode)
    self._namespaceURI= namespaceURI
    self._localName= localName
    self._sequence= None

  def _get_length(self):
    if self._sequence!=self._ownerNode._sequence: self._calculate()
    return NodeList._get_length(self)

  def item(self, index):
    if self._sequence!=self._ownerNode._sequence: self._calculate()
    return NodeList.item(self, index)

  def __getitem__(self, index):
    if self._sequence!=self._ownerNode._sequence: self._calculate()
    return NodeList.__getitem__(self, index)

  def __len__(self):
    if self._sequence!=self._ownerNode._sequence: self._calculate()
    return NodeList.__len__(self)

  def _calculate(self):
    """ Recalculate the list. This method does the actual work of the
        Element.getElementsByTagName call.
    """
    self._list= []
    self._walk(self._ownerNode)
    self._sequence= self._ownerNode._sequence

  def _walk(self, element):
    """ Recursively add a node's child elements to the internal node list when
        they match the conditions passed to Element.getElementsByTagName.
    """
    for childNode in element.childNodes:
      if childNode.nodeType==Node.ELEMENT_NODE:
        if (
          self._localName=='*' and
          self._namespaceURI in ('*', NONS, childNode.namespaceURI)
        ) or (
          self._namespaceURI=='*' and
          self._localName==childNode.localName
        ) or (
          self._namespaceURI==NONS and
          self._localName==childNode.nodeName
        ) or (
          self._namespaceURI==childNode.namespaceURI and
          self._localName==childNode.localName
        ):
          self._list.append(childNode)
      if childNode.nodeType in (Node.ELEMENT_NODE,Node.ENTITY_REFERENCE_NODE):
        self._walk(childNode)


class NamedNodeMap(NodeList):
  """ Dictionary-style object used for mappings. Must be initialised with a
      nodeType for nodes it wishes to handle.
  """
  def __init__(self, ownerNode, childType):
    NodeList.__init__(self, ownerNode)
    self._childType= childType

  def getNamedItemNS(self, namespaceURI, localName):
    if namespaceURI=='':
      namespaceURI= None
    for node in self._list:
      if (
        (namespaceURI==NONS and localName==node.nodeName) or
        (namespaceURI==node.namespaceURI and localName==node.localName)
      ):
        return node
    return None

  def setNamedItemNS(self, arg):
    node= self.getNamedItemNS(arg.namespaceURI, arg.localName)
    self._writeItem(node, arg)
    return node

  def removeNamedItemNS(self, namespaceURI, localName):
    node= self.getNamedItemNS(namespaceURI, localName)
    if node is None:
      raise NotFoundErr(self, namespaceURI, localName)
    self._writeItem(node, None)
    return node

  def getNamedItem(self, name):
    return self.getNamedItemNS(NONS, name)

  def setNamedItem(self, arg):
    node= self.getNamedItemNS(NONS, arg.nodeName)
    self._writeItem(node, arg)
    return node

  def removeNamedItem(self, name):
    return self.removeNamedItemNS(NONS, name)

  def _writeItem(self, oldItem, newItem):
    """ Internal alteration functions through which all add, remove and
        replace operations are made. If oldItem is not None it is removed;
        if newItem is not None it is added; if both not None the new item is
        written the previous position of the oldItem.
    """
    if self._readonly:
      raise NoModificationAllowedErr(self, 'namedItem')
    if newItem is not None:
      if newItem.nodeType!=self._childType:
        raise HierarchyRequestErr(newItem, self)
      if newItem.ownerDocument is not self._ownerNode.ownerDocument:
        raise WrongDocumentErr(self._ownerNode.ownerDocument, newItem)
    if oldItem is None:
      index= len(self._list)
    else:
      try:
        index= self._list.index(oldItem)
      except ValueError:
        raise NotFoundErr(self, NONS, oldItem.nodeName)
      oldItem._containerNode= None
    if newItem is not None:
      newItem._containerNode= self._ownerNode
      self._list[index:index+1]= [newItem]
    else:
      self._list[index:index+1]= []

  # Python dictionary-style methods for minidom compatibility. This is
  # inconsistent with how Python dictionaries normally work, and is subject
  # to change. It is recommended to use the standard DOM methods instead.
  #
  def __getitem__(self, key):
    if isinstance(key, type(0)):
      return self._list[key]
    elif isinstance(key, type(())):
      return self.getNamedItemNS(key[0], key[1])
    else:
      return self.getNamedItem(key)

  def __delitem__(self, key):
    if isinstance(key, type(0)):
      self._writeItem(self._list[key], None)
    elif isinstance(key, type(())):
      self.removeNamedItemNS(key[0], key[1])
    else:
      return self.removeNamedItem(key)

  def __setitem__(self, key, value):
    if isinstance(value, Attr):
      if isinstance(key, type(0)):
        self._writeItem(self._list[key], value)
      elif isinstance(key, type(())):
        self._ownerNode.setAttributeNodeNS(value)
      else:
        self._ownerNode.setAttributeNode(value)
    else:
      if isinstance(key, type(0)):
        self._list[key].value= value
      elif isinstance(key, type(())):
        return self._ownerNode.setAttributeNS(key[0], key[1], value)
      else:
        return self._ownerNode.setAttribute(key, value)

  def values(self):
    return self._list[:]
  def keys(self):
    return map(lambda a: a.nodeName, self._list)
  def items(self):
    return map(lambda a: (a.nodeName, a.value), self._list)
  def keysNS(self):
    return map(lambda a: (a.namespaceURI, a.localName), self._list)
  def itemsNS(self):
    return map(lambda a: ((a.namespaceURI,a.localName),a.value), self._list)


class AttrMap(NamedNodeMap):
  """ A node map used for storing the attributes of an element, and updating
      the defaulted attributes automatically on changes.
  """
  def __init__(self, ownerNode):
    NamedNodeMap.__init__(self, ownerNode, Node.ATTRIBUTE_NODE)
  def _writeItem(self, oldItem, newItem):
    if newItem is not None and newItem.nodeType==Node.ATTRIBUTE_NODE and (
      newItem._containerNode not in (None, self._ownerNode)
    ):
      raise InuseAttributeErr(newItem)
    NamedNodeMap._writeItem(self, oldItem, newItem)
    if oldItem is not None:
      oldItem._isId= False
      if newItem is None or newItem.nodeName!=oldItem.nodeName:
        ownerDocument= self._ownerNode.ownerDocument
        if ownerDocument is not None:
          doctype= ownerDocument.doctype
          if doctype is not None:
            declarationList= doctype._attlists.getNamedItem(
              self._ownerNode.nodeName
            )
            if declarationList is not None:
              declaration= declarationList.declarations.getNamedItem(
                oldItem.nodeName
              )
              if (
                declaration is not None and declaration.defaultType in (
                  AttributeDeclaration.DEFAULT_VALUE,
                  AttributeDeclaration.FIXED_VALUE
                )
              ):
                declaration._createAttribute(self._ownerNode)


# Core non-node classes
# ============================================================================

class DOMImplementation(DOMObject):
  """ Main pxtl.dom implementation interface, a singleton class. The pxdom
      module itself implements the DOMImplementationSource interface, so you
      can get hold of an implementation with pxdom.getDOMImplementation('')
  """
  [MODE_SYNCHRONOUS,MODE_ASYNCHRONOUS
  ]=range(1, 3)

  _features= {
    'xml':  ['1.0', '2.0', '3.0'],
    'core':        ['2.0', '3.0'],
    'ls':                 ['3.0'],
    'xmlversion':  ['1.0', '1.1']
  }
  def hasFeature(self, feature, version):
    f= string.lower(feature)
    if f[:1]=='+':
      f= f[1:]
    if self._features.has_key(f):
      if version in self._features[f]+['', None]:
        return True
    return False
  def getFeature(self, feature, version):
    if self.hasFeature(feature, version):
      return self

  def createDocument(self, namespaceURI, qualifiedName, doctype):
    if namespaceURI=='':
      namespaceURI= None
    document= Document()
    if doctype is not None:
      document.appendChild(doctype)
    if qualifiedName is not None:
      root= document.createElementNS(namespaceURI, qualifiedName)
      document.appendChild(root)
    return document

  def createDocumentType(self, qualifiedName, publicId, systemId):
    if _splitName(qualifiedName)[1] is None:
      raise NamespaceErr(qualifiedName, None)
    doctype= DocumentType(None, qualifiedName, publicId, systemId)
    doctype.entities.readonly= True
    doctype.notations.readonly= True
    return doctype

_implementation= DOMImplementation()

def getDOMImplementation(features= ''):
  """ DOM 3 Core hook to get the Implementation object. If features is
      supplied, only return the implementation if all features are satisfied.
  """
  fv= string.split(features, ' ')
  for index in range(0, len(fv)-1, 2):
    if not _implementation.hasFeature(fv[index], fv[index+1]):
      return None
  return _implementation

def getDOMImplementationList(features= ''):
  """ DOM 3 Core method to get implementations in a list. For pxdom this will
      only ever be the single implementation, if any.
  """
  implementation= getDOMImplementation(features)
  implementationList= DOMImplementationList()
  if implementation is not None:
    implementationList._append(implementation)
  implementationList.readonly= True
  return implementationList


class DOMImplementationList(DOMList):
  """ List of DOMImplementation classes; no special features over DOMList.
  """
  pass


class DOMConfiguration(DOMObject):
  """ Object holding a mapping of parameter names to values, and performing
      the flag-flipping warts of infoset and canonical-form. _defaults holds
      the default values (mostly defined by the spec), together with a flag
      document whether each can be changed from the defaults (optional
      features relating to validation and character normalisation are not
      supported by pxdom).
  """
  _defaults= {
    # Core configuration
    'canonical-form':                            (False, True ),
    'cdata-sections':                            (True,  True ),
    'check-character-normalization':             (False, CNORM),
    'comments':                                  (True,  True ),
    'datatype-normalization':                    (False, False),
    'element-content-whitespace':                (True,  True ),
    'entities':                                  (True,  True ),
    'error-handler':                             (None,  True ),
    'ignore-unknown-character-denormalizations': (True,  False),
    'namespaces':                                (True,  True ),
    'namespace-declarations':                    (True,  True ),
    'normalize-characters':                      (False, CNORM),
    'schema-location':                           (None,  False),
    'schema-type':                               (None,  False),
    'split-cdata-sections':                      (True,  True ),
    'validate':                                  (False, False),
    'validate-if-schema':                        (False, False),
    'well-formed':                               (True,  True ),
    # LSParser-specific configuration
    'charset-overrides-xml-encoding':            (True,  True ),
    'disallow-doctype':                          (False, True ),
    'resource-resolver':                         (None,  True ),
    'supported-media-types-only':                (False, True),
    # LSSerializer-specific configuration
    'discard-default-content':                   (True,  True ),
    'format-pretty-print':                       (False, True),
    'xml-declaration':                           (True,  True ),
    # Non-standard extensions
    'pxdom-assume-element-content':              (False, True ),
    'pxdom-resolve-resources':                   (False, False)
  }

  _complexparameters= {
    'infoset': ((
        'cdata-sections', 'datatype-normalization', 'entities',
        'validate-if-schema'
      ), (
        'comments', 'element-content-whitespace', 'namespace-declarations',
        'namespaces', 'well-formed'
    )),
    'canonical-form': ((
        'cdata-sections', 'entities', 'normalize-characters',
        'discard-default-content', 'xml-declaration'
      ), (
        'element-content-whitespace', 'namespace-declarations', 'namespaces',
        'well-formed'
    ))
  }

  def __init__(self, copyFrom= None):
    """ Make a new DOMConfiguration mapping, using either default values or
        the current values of another DOMConfiguration, if using the
        copy-constructor feature.
    """
    DOMObject.__init__(self)
    self._parameters= {}
    for (name, (value, canSet)) in self._defaults.items():
      if copyFrom is not None:
        self._parameters[name]= copyFrom._parameters[name]
      else:
        self._parameters[name]= value

  def canSetParameter(self, name, value):
    name= string.lower(name)
    if name=='infoset':
      return True
    if self._parameters[name]==value:
      return True
    return self._defaults.get(name, (None, False))[1]

  def getParameter(self, name):
    name= string.lower(name)
    if self._complexparameters.has_key(name):
      for b in False, True:
        for p in self._complexparameters[name][b]:
          if self._parameters[p]!=b:
            return False
      if name=='infoset':
        return True
    if not self._parameters.has_key(name):
      raise NotFoundErr(self, None, name)
    return self._parameters[name]

  def setParameter(self, name, value):
    name= string.lower(name)
    if self._complexparameters.has_key(name):
      if value:
        for b in False, True:
          for p in self._complexparameters[name][b]:
            self._parameters[p]= b
      if name=='infoset':
        return
    if not self._defaults.has_key(name):
      raise NotFoundErr(self, None, name)
    if self._parameters[name]!=value:
      if not self._defaults[name][1]:
        raise NotSupportedErr(self, name)
      self._parameters[name]= value

  def _get_parameterNames(self):
    return DOMList(self._parameters.keys()+['infoset'])

  # Convenience method to do character normalization and/or check character
  # normalization on a string, depending on the parameters set on the config
  #
  def _cnorm(self, text, node):
    nc= self._parameters['normalize-characters']
    cn= self._parameters['check-character-normalization']
    if not nc and not cn or text=='' or isinstance(text, type('')):
      return text
    normal= unicodedata.normalize('NFC', text)
    if nc:
      text= normal
    if (not nc and text!=normal or cn and
      (unicodedata.combining(text[0])!=0 or text[0] in EXTRACOMPOSERS)
    ):
      self._handleError(DOMErrorCheckCharacterNormalizationFailure(node))
    return text

  # Convenience method for pxdom to callback the error-handler if one is set
  # on the DOMConfiguration, and raise an exception if the error or handler
  # says processing should not continue.
  #
  def _handleError(self, exn):
    handler= self._parameters['error-handler']
    cont= None
    if handler is not None:
      error= DOMError(exn.severity, str(exn), exn.type, exn.node)
      cont= handler.handleError(error)
    if not exn.allowContinue(cont):
      raise exn


# For some reason, the spec says configs owned by LSParsers can't have
# well-formed set to False
#
class ParserConfiguration(DOMConfiguration):
  _defaults= dictadd(DOMConfiguration._defaults, {
    'well-formed': (True, False)
  })


class TypeInfo(DOMObject):
  """ Value type belonging to an Element or Attribute supplying information
      about its schema type. Since only DTDs are supported, this returns nulls
      except for Attribute typeNames, which might be grabbable from the
      internal subset's attlists.
  """
  [DERIVATION_RESTRICTION, DERIVATION_EXTENSION, DERIVATION_UNION,
  DERIVATION_LIST]= range(1, 5) # not used, but in interface spec

  def __init__(self, ownerNode):
    DOMObject.__init__(self, False)
    self._ownerNode= ownerNode
  def _get_typeNamespace(self):
    return self._getType()[0]
  def _get_typeName(self):
    return self._getType()[1]

  def _getType(self):
    if (
      self._ownerNode.nodeType==Node.ATTRIBUTE_NODE and
      self._ownerNode.ownerElement is not None and
      self._ownerNode.ownerDocument is not None and
      self._ownerNode.ownerDocument.doctype is not None
    ):
      tagName= self._ownerNode.ownerElement.tagName
      attlist= self._ownerNode.ownerDocument.doctype._attlists.getNamedItem(
        tagName
      )
      if attlist is not None:
        attdecl= attlist.declarations.getNamedItem(self._ownerNode.name)
        if attdecl is not None:
          return (DTNS,AttributeDeclaration.ATTR_NAMES[attdecl.attributeType])
    return (None, None)


class DOMLocator(DOMObject):
  """ Value type used to return information on the source document and position
      of a node. Used in the standard DOM to locate DOMErrors; pxdom also
      allows any Node to be located this way.
  """
  def __init__(self, node= None, lineNumber= -1, columnNumber= -1, uri= None):
    self._relatedNode= node
    self._lineNumber= lineNumber
    self._columnNumber= columnNumber
    if uri is not None:
      self._uri= uri
    elif node is not None:
      self._uri= node._ownerDocument.documentURI
    else:
      self._uri= ''
  def _get_lineNumber(self):
    return self._lineNumber
  def _get_columnNumber(self):
    return self._columnNumber
  def _get_byteOffset(self):
    return -1
  def _get_utf16Offset(self):
    return -1
  def _get_relatedNode(self):
    return self._relatedNode
  def _get_uri(self):
    return self._uri


class UserDataHandler:
  """ Any Python object that supplies a 'handle' method can be bound to the
      DOM type UserDataHandler; this merely holds its static constants. NB.
      NODE_DELETED is never called because (as noted in the DOM Core spec)
      we have no idea when the object will be deleted by Python. No __del__
      handler is provided for this because it stops the garbage collector
      from freeing nodes with reference cycles (of which pxdom has many).
  """
  [NODE_CLONED, NODE_IMPORTED, NODE_DELETED, NODE_RENAMED, NODE_ADOPTED
  ]= range(1, 6)


# Core node classes
# ============================================================================

class Node(DOMObject):
  """ Abstract base class for all DOM Nodes.
  """
  [ELEMENT_NODE,ATTRIBUTE_NODE,TEXT_NODE,CDATA_SECTION_NODE,
  ENTITY_REFERENCE_NODE,ENTITY_NODE,PROCESSING_INSTRUCTION_NODE,COMMENT_NODE,
  DOCUMENT_NODE,DOCUMENT_TYPE_NODE,DOCUMENT_FRAGMENT_NODE,NOTATION_NODE
  ]= range(1,13)
  [ELEMENT_DECLARATION_NODE,ATTRIBUTE_DECLARATION_NODE,ATTRIBUTE_LIST_NODE
  ]= range(301, 304)
  [DOCUMENT_POSITION_DISCONNECTED,DOCUMENT_POSITION_PRECEDING,
  DOCUMENT_POSITION_FOLLOWING,DOCUMENT_POSITION_CONTAINS,
  DOCUMENT_POSITION_CONTAINED_BY,DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC
  ]= map(lambda n: 1<<n, range(6))

  # Node properties
  #
  def __init__(self,
    ownerDocument= None, namespaceURI= None, localName= None, prefix= None
  ):
    DOMObject.__init__(self)
    self._ownerDocument= ownerDocument
    self._containerNode= None
    self._namespaceURI= namespaceURI
    self._localName= localName
    self._prefix= prefix
    self._childNodes= ChildNodeList(self)
    self._attributes= None
    self._userData= {}
    self._childNodes.readonly= True
    self._sequence= 0
    self._row= -1
    self._col= -1
  def _cloneTo(self, node):
    node._ownerDocument= self._ownerDocument
    node._namespaceURI= self._namespaceURI
    node._localName= self._localName
    node._prefix= self._prefix
    node._row= self._row
    node._col= self._col

  def _get_ownerDocument(self): return self._ownerDocument
  def _get_parentNode(self): return self._containerNode
  def _get_nodeType(self): return None
  def _get_nodeName(self): return '#abstract-node'
  def _get_nodeValue(self): return None
  def _get_namespaceURI(self): return self._namespaceURI
  def _get_localName(self): return self._localName
  def _get_prefix(self): return self._prefix
  def _get_childNodes(self): return self._childNodes
  def _get_attributes(self): return self._attributes
  def _set_nodeValue(self, value):
    pass

  # Hierarchy access
  #
  def _get_firstChild(self):
    if self.childNodes.length>0:
      return self.childNodes.item(0)
    return None

  def _get_lastChild(self):
    if self.childNodes.length>0:
      return self._childNodes.item(self.childNodes.length-1)
    return None

  def _get_previousSibling(self):
    if self.parentNode is None:
      return None
    try:
      index= self.parentNode.childNodes._index(self)
    except ValueError:
      return None
    if index<1:
      return None
    return self.parentNode.childNodes.item(index-1)

  def _get_nextSibling(self):
    if self.parentNode is None:
      return None
    try:
      index= self.parentNode.childNodes._index(self)
    except ValueError:
      return None
    if index>=self.parentNode.childNodes.length-1:
      return None
    return self.parentNode.childNodes.item(index+1)

  def hasAttributes(self):
    if self._attributes is not None:
      if self._attributes.length>0:
        return True
    return False

  def hasChildNodes(self):
    return self._childNodes.length>0

  # Hierarchy alteration
  #
  _childTypes= [
    ELEMENT_NODE, COMMENT_NODE, ENTITY_REFERENCE_NODE,TEXT_NODE,
    CDATA_SECTION_NODE, PROCESSING_INSTRUCTION_NODE
  ]

  def appendChild(self, newChild):
    self._writeChild(newChild, None, False)
    return newChild
  def insertBefore(self, newChild, oldChild):
    self._writeChild(newChild, oldChild, False)
    return newChild
  def replaceChild(self, newChild, oldChild):
    self._writeChild(newChild, oldChild, True)
    return oldChild
  def removeChild(self, oldChild):
    self._writeChild(None, oldChild, True)
    return oldChild

  def _writeChild(self, newChild, oldChild, removeOld):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'Child')
    if oldChild is not None and oldChild not in self._childNodes:
      raise NotFoundErr(
        self._childNodes, oldChild.namespaceURI, oldChild.localName
      )

    if newChild is not None:
      if newChild.ownerDocument not in (self._ownerDocument, None):
        raise WrongDocumentErr(newChild, self._ownerDocument)
      ancestor= self
      while ancestor is not None:
        if newChild is ancestor:
          raise HierarchyRequestErr(newChild, self)
        ancestor= ancestor.parentNode
      if newChild.nodeType==Node.DOCUMENT_FRAGMENT_NODE:
        newNodes= list(newChild._childNodes._list)
      else:
        newNodes= [newChild]
      for node in newNodes:
        if node.nodeType not in self._childTypes:
          raise HierarchyRequestErr(node, self)
        if node.parentNode is not None:
          node.parentNode.removeChild(node)

    self._childNodes.readonly= False
    if oldChild is None:
      index= self._childNodes.length
    else:
      index= self._childNodes._index(oldChild)
    if removeOld:
      oldChild._containerNode= None
      del self._childNodes._list[index]
    if newChild is not None:
      if newChild.ownerDocument is None:
        newChild._recurse(True, ownerDocument= self._ownerDocument)
      self._childNodes._insertseq(index, newNodes)
      for node in newNodes:
        node._containerNode= self
    self._childNodes.readonly= True
    self._changed()

  # DOM 3 UserData
  #
  def getUserData(self, key):
    return self._userData.get(key, (None, None))[0]

  def setUserData(self, key, data, handler):
    oldData= self.getUserData(key)
    self._userData[key]= (data, handler)
    return oldData

  def _callUserDataHandlers(self, operation, src, dst):
    """ Internal convenience method to dispatch callbacks to all registered
        UserDataHandlers.
    """
    for (key, (data, handler)) in self._userData.items():
      if handler is not None:
        handler.handle(operation, key, data, src, dst)

  def isSupported(self, feature, version):
    return _implementation.hasFeature(feature, version)

  def getFeature(self, feature, version):
    if implementation.hasFeature(feature, version):
      return self
    return None

  def _get_baseURI(self):
    if self._attributes is not None:
      base= self._attributes.getNamedItemNS(XMNS, 'base')
      if base is not None:
        if urlparse.urlparse(base.value)[0]!='':
          return base.value
        if self._containerNode is None:
          return base.value
        return urlparse.urljoin(self._containerNode.baseURI, base.value)
    if self._containerNode is None:
      return None
    if self._containerNode.nodeType==Node.DOCUMENT_TYPE_NODE:
      if self.ownerDocument is not None:
        return self.ownerDocument.documentURI
    return self._containerNode.baseURI

  def _get_pxdomLocation(self):
    return DOMLocator(self, self._row, self._col)
  def _setLocation(self, (row, col)):
    self._row= row
    self._col= col

  def _renameNode(self, namespaceURI, qualifiedName):
    raise NotSupportedErr(self, 'renameNode')

  def _changed(self):
    self._sequence= self._sequence+1
    if self._containerNode is not None:
      self._containerNode._changed()

  def _getDescendants(self, descendants):
    for child in self._childNodes:
      descendants.append(child)
      child._getDescendants(descendants)

  def _containsUnboundPrefix(self):
    if self._prefix is not None and self._namespaceURI is None:
      return True
    if self._attributes is not None:
      for attr in self._attributes:
        if attr._containsUnboundPrefix():
          return True
    for child in self._childNodes:
      if child._containsUnboundPrefix():
        return True
    return False


class NamedNode(Node):
  """ Base class for nodes who have specific names but no namespace
      capability (entity references and so on).
  """
  def __init__(self, ownerDocument= None, nodeName= None, _strict= True):
    Node.__init__(self, ownerDocument, None, None, None)
    if _strict and nodeName is not None:
      _checkName(nodeName)
    self._nodeName= nodeName
  def _cloneTo(self, node):
    Node._cloneTo(self, node)
    node._nodeName= self._nodeName
  def _get_nodeName(self):
    return self._nodeName


class NamedNodeNS(Node):
  """ Base class for nodes whose names are derived from their prefix and
      local name (Element and Attribute). In these nodes, namespaceURI may be
      stored internally as NONS, signifying a node created by Level 1 methods.
      In this case the node name is stored internally in localName, but
      trying to read either namespaceURI or localName will result in a null
      value as specified by DOM Level 2 Core.
  """
  def __init__(self,
    ownerDocument= None, namespaceURI= None, localName= None, prefix= None
  ):
    for name in (prefix, localName):
      if name is not None:
        _checkName(name, nc= namespaceURI!=NONS)
    Node.__init__(self, ownerDocument, namespaceURI, localName, prefix)
  def _get_nodeName(self):
    if self._namespaceURI==NONS or self._prefix is None:
      return self._localName
    return '%s:%s' % (self._prefix, self._localName)
  def _get_localName(self):
    if self._namespaceURI==NONS:
      return None
    return self._localName
  def _get_namespaceURI(self):
    if self._namespaceURI==NONS:
      return None
    return self._namespaceURI
  def _get_schemaTypeInfo(self):
    return TypeInfo(self)

  def _set_prefix(self, value):
    if value=='':
      value= None
    else:
      _checkName(value)
    if (':' in value or
      (self._namespaceURI in (None, NONS) and value is not None) or
      (value=='xml' and self._namespaceURI!=XMNS) or
      (value=='xmlns' and self._namespaceURI!=NSNS) or
      (value not in ('xml', 'xmlns') and self._namespaceURI in (XMNS, NSNS))
    ):
      raise NamespaceErr((value or '')+':'+self._localName,self._namespaceURI)
    self._prefix= value
    self._changed()

  def _renameNode(self, namespaceURI, qualifiedName):
    prefix, localName= _splitName(qualifiedName)
    if localName is None:
      _checkName(qualifiedName)
      self._namespaceURI= NONS
      self._prefix= None
      self._localName= qualifiedName
    else:
      _checkName(localName, nc= True)
      if prefix is not None:
          _checkName(prefix, nc= True)
      if (
        (namespaceURI is None and prefix is not None) or
        (namespaceURI==XMNS)!=(prefix=='xml') or
        (namespaceURI==NSNS)!=('xmlns' in (prefix, qualifiedName))
      ):
        raise NamespaceErr(qualifiedName, namespaceURI)
      self._namespaceURI= namespaceURI
      self._prefix= prefix
      self._localName= localName


class Document(Node):
  """ Implementation of DOM 3 Document interface.
  """
  def __init__(self):
    Node.__init__(self, self, None, None, None)
    self._xmlStandalone= False
    self._xmlVersion= '1.0'
    self._xmlEncoding= None
    self._inputEncoding= None
    self._documentURI= None
    self._strictErrorChecking= True
    self._domConfig= DOMConfiguration()
  def _cloneTo(self, node):
    Node._cloneTo(self, node)
    node._xmlStandalone= self._xmlStandalone
    node._xmlVersion= self._xmlVersion
    node._xmlEncoding= self._xmlEncoding
    node._inputEncoding= self._inputEncoding
    node._documentURI= self._documentURI
    node._strictErrorChecking= self._strictErrorChecking
    node._domConfig= DOMConfiguration(self._domConfig)

  def _get_nodeType(self):
    return Node.DOCUMENT_NODE
  def _get_nodeName(self):
    return '#document'
  def _get_ownerDocument(self):
    return None
  _childTypes= [
    Node.ELEMENT_NODE, Node.COMMENT_NODE, Node.TEXT_NODE,
    Node.PROCESSING_INSTRUCTION_NODE, Node.DOCUMENT_TYPE_NODE
  ]

  def _get_implementation(self):
    return _implementation
  def _get_documentElement(self):
    for child in self._childNodes:
      if child.nodeType==Node.ELEMENT_NODE:
        return child
    return None
  def _get_doctype(self):
    for child in self._childNodes:
       if child.nodeType==Node.DOCUMENT_TYPE_NODE:
        return child
    return None
  def _get_baseURI(self):
    return self._documentURI
  def _get_domConfig(self):
    return self._domConfig

  def _get_xmlStandalone(self):
    return self._xmlStandalone
  def _set_xmlStandalone(self, value):
    self._xmlStandalone= value
  def _get_xmlVersion(self):
    return self._xmlVersion
  def _set_xmlVersion(self, value):
    if value not in ('1.0', '1.1'):
      raise NotSupportedErr(self, 'xmlVersion '+value)
    self._xmlVersion= value
  def _get_xmlEncoding(self):
    return self._xmlEncoding
  def _get_inputEncoding(self):
    return self._inputEncoding
  def _get_documentURI(self):
    return self._documentURI
  def _set_documentURI(self, value):
    self._documentURI= value
  def _get_strictErrorChecking(self):
    return self._strictErrorChecking
  def _set_strictErrorChecking(self, value):
    self._strictErrorChecking= value

  def createElement(self, tagName, _default= True):
    element= Element(self, NONS, tagName, None)
    if _default:
      element._setDefaultAttributes()
    return element
  def createElementNS(
    self, namespaceURI, qualifiedName, _strict= True, _default= True
  ):
    if namespaceURI=='':
      namespaceURI= None
    prefix, localName= _splitName(qualifiedName)
    if (
      localName is None or
      (_strict and namespaceURI is None and prefix is not None) or
      namespaceURI in (XMNS, NSNS) or prefix in ('xml', 'xmlns')
    ):
      raise NamespaceErr(qualifiedName, namespaceURI)
    element= Element(self, namespaceURI, localName, prefix)
    if _default:
      element._setDefaultAttributes()
    return element
  def createAttribute(self, name):
    return Attr(self, NONS, name, None, True)
  def createAttributeNS(self, namespaceURI, qualifiedName, _strict= True):
    if namespaceURI=='':
      namespaceURI= None
    prefix, localName= _splitName(qualifiedName)
    if (
      localName is None or
      (_strict and namespaceURI is None and prefix is not None) or
      (namespaceURI==XMNS)!=(prefix=='xml') or
      (namespaceURI==NSNS)!=('xmlns' in (prefix, qualifiedName)) or
      (prefix=='xmlns' and localName in ('xml', 'xmlns'))
    ):
      raise NamespaceErr(qualifiedName, namespaceURI)
    return Attr(self, namespaceURI, localName, prefix, True)
  def createTextNode(self, data):
    node= Text(self)
    node.data= data
    return node
  def createComment(self, data):
    node= Comment(self)
    node.data= data
    return node
  def createCDATASection(self, data):
    node= CDATASection(self)
    node.data= data
    return node
  def createProcessingInstruction(self, target, data):
    node= ProcessingInstruction(self, target)
    node.data= data
    return node
  def createDocumentFragment(self):
    return DocumentFragment(self)
  def createEntityReference(self, name, _strict= True):
    node= EntityReference(self, name, _strict)
    node._normalize(ents= True)
    return node

  def getElementsByTagName(self, name):
    return NodeListByTagName(self, NONS, name)
  def getElementsByTagNameNS(self, namespaceURI, localName):
    if namespaceURI=='':
      namespaceURI= None
    return NodeListByTagName(self, namespaceURI, localName)
  def getElementById(self, elementId):
    return self._getElementById(self, elementId)
  def _getElementById(self, node, elementId):
    if node._attributes is not None:
      for attr in node._attributes:
        if attr.isId and attr.value==elementId:
          return node
    if Node.ELEMENT_NODE in node._childTypes:
      for child in node._childNodes:
        element= self._getElementById(child, elementId)
        if element is not None:
          return element
    return None

  def renameNode(self, n, namespaceURI, qualifiedName):
    if namespaceURI=='':
      namespaceURI= None
    if self._readonly:
      raise NoModificationAllowedErr(self, 'renameNode')
    if n.ownerDocument is not self:
      raise WrongDocumentErr(n, self)
    n._renameNode(namespaceURI, qualifiedName)
    n._changed()
    n._callUserDataHandlers(UserDataHandler.NODE_RENAMED, n, None)
    return n

  def _writeChild(self, newChild, oldChild, removeOld):
    """ Before allowing a child hierarchy change to go ahead, check that
        allowing it wouldn't leave the document containing two Element or two
        DocumentType children.
    """
    if newChild is not None:
      if newChild.nodeType==Node.DOCUMENT_FRAGMENT_NODE:
        newNodes= newChild._childNodes._list
      else:
        newNodes= [newChild]
      doctype= None
      documentElement= None
      afterNodes= list(self._childNodes._list)
      if removeOld and oldChild in afterNodes:
        afterNodes.remove(oldChild)
      for node in afterNodes+newNodes:
        if node.nodeType==Node.DOCUMENT_TYPE_NODE:
          if doctype not in (node, None):
            raise HierarchyRequestErr(node, self)
          doctype= node
        if node.nodeType==Node.ELEMENT_NODE:
          if documentElement not in (node, None):
            raise HierarchyRequestErr(node, self)
          documentElement= node
    Node._writeChild(self, newChild, oldChild, removeOld)


class DocumentFragment(Node):
  def __init__(self, ownerDocument= None):
    Node.__init__(self, ownerDocument, None, None, None)
  def _get_nodeType(self):
    return Node.DOCUMENT_FRAGMENT_NODE
  def _get_nodeName(self):
    return '#document-fragment'


class Element(NamedNodeNS):
  """ Implementation of DOM 3 Element interface.
  """
  def __init__(self,
    ownerDocument= None, namespaceURI= None, localName= None, prefix= None
  ):
    NamedNodeNS.__init__(self, ownerDocument, namespaceURI, localName, prefix)
    self._attributes= AttrMap(self)
  def _get_nodeType(self):
    return Node.ELEMENT_NODE
  def _get_tagName(self):
    return self.nodeName

  def hasAttribute(self, name):
    return self._attributes.getNamedItem(name) is not None
  def getAttribute(self, name):
    attr= self._attributes.getNamedItem(name)
    if attr is None:
      return ''
    return attr.value
  def setAttribute(self, name, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setAttribute')
    attr= self._attributes.getNamedItem(name)
    if attr is None:
      attr= Attr(self._ownerDocument, NONS, name, None, True)
      self._attributes.setNamedItem(attr)
    else:
      attr._specified= True
    attr.value= value
  def removeAttribute(self, name):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'removeAttribute')
    try:
      self._attributes.removeNamedItem(name)
    except NotFoundErr:
      pass
  def getAttributeNode(self, name):
    return self._attributes.getNamedItem(name)
  def setAttributeNode(self, node):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setAttributeNode')
    return self._attributes.setNamedItem(node)
  def removeAttributeNode(self, node):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'removeAttributeNode')
    self._attributes._writeItem(node, None)
    return node

  def hasAttributeNS(self, namespaceURI, localName):
    return self._attributes.getNamedItemNS(namespaceURI,localName) is not None
  def getAttributeNS(self, namespaceURI, localName):
    attr= self._attributes.getNamedItemNS(namespaceURI, localName)
    if attr is None:
      return ''
    return attr.value
  def setAttributeNS(self, namespaceURI, qualifiedName, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setAttributeNS')
    attr= self._attributes.getNamedItemNS(namespaceURI, qualifiedName)
    if attr is None:
      attr= self._ownerDocument.createAttributeNS(namespaceURI, qualifiedName)
      self._attributes.setNamedItemNS(attr)
    else:
      attr._specified= True
    attr.value= value
  def removeAttributeNS(self, namespaceURI, localName):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'removeAttributeNS')
    try:
      self._attributes.removeNamedItemNS(namespaceURI, localName)
    except NotFoundErr:
      pass
  def getAttributeNodeNS(self, namespaceURI, localName):
    return self._attributes.getNamedItemNS(namespaceURI, localName)
  def setAttributeNodeNS(self, node):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setAttributeNodeNS')
    return self._attributes.setNamedItemNS(node)

  def getElementsByTagName(self, name):
    return NodeListByTagName(self, NONS, name)
  def getElementsByTagNameNS(self, namespaceURI, localName):
    if namespaceURI=='':
      namespaceURI= None
    return NodeListByTagName(self, namespaceURI, localName)

  def setIdAttribute(self, name, isId):
    node= self.getAttributeNode(name)
    if node is None:
      raise NotFoundErr(self._attributes, NONS, name)
    self.setIdAttributeNode(node, isId)
  def setIdAttributeNS(self, namespaceURI, localName, isId):
    node= self.getAttributeNodeNS(namespaceURI, localName)
    if node is None:
      raise NotFoundErr(self._attributes,namespaceURI, localName)
    self.setIdAttributeNode(node, isId)
  def setIdAttributeNode(self, idAttr, isId):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setIdAttribute')
    if idAttr not in self._attributes._list:
      raise NotFoundErr(self._attributes, NONS, idAttr.name)
    idAttr._isId= isId

  def _renameNode(self, namespaceURI, qualifiedName):
    NamedNodeNS._renameNode(self, namespaceURI, qualifiedName)
    self._setDefaultAttributes()

  def _setDefaultAttributes(self):
    if self._ownerDocument is None or self._ownerDocument.doctype is None:
      return
    declarationList= self._ownerDocument.doctype._attlists.getNamedItem(
      self.tagName
    )
    if declarationList is None:
      return
    for attr in self._attributes._list[:]:
      if not attr.specified:
        self.removeAttributeNode(attr)
    for declaration in declarationList.declarations:
      if (
        declaration.defaultType in (
          AttributeDeclaration.DEFAULT_VALUE,
          AttributeDeclaration.FIXED_VALUE
        ) and  not self.hasAttribute(declaration.nodeName)
      ):
        declaration._createAttribute(self)


class Attr(NamedNodeNS):
  def __init__(self,
    ownerDocument= None,
    namespaceURI= None, localName= None, prefix= None, specified= True
  ):
    NamedNodeNS.__init__(self, ownerDocument, namespaceURI, localName, prefix)
    self._specified= specified
    self._isId= False
  def _cloneTo(self, node):
    """ Make a clone of a node. Clones are always specified.
    """
    NamedNodeNS._cloneTo(self, node)
    node._isId= self._isId
    node._specified= True

  def _get_nodeType(self):
    return Node.ATTRIBUTE_NODE
  def _get_nodeValue(self):
    return self.textContent
  def _get_name(self):
    return self.nodeName
  def _get_value(self):
    c= self._childNodes
    if c.length==1 and c[0].nodeType==Node.TEXT_NODE:
      value= c[0].data
    else:
      value= self.textContent
    if self.schemaTypeInfo.typeName in ('CDATA', None):
      return value
    else:
      return string.join(
        filter(lambda s: s!='', string.split(value, ' ')), ' '
      )
  def _set_nodeValue(self, value):
    self.value= value

  def _set_value(self, value):
    while self.firstChild is not None:
      self.removeChild(self.firstChild)
    if value!='':
      self.appendChild(self._ownerDocument.createTextNode(value))
    self._specified= True

  _childTypes= [Node.TEXT_NODE, Node.ENTITY_REFERENCE_NODE]
  def _get_parentNode(self):
    return None
  def _get_ownerElement(self):
    return self._containerNode
  def _get_schemaTypeInfo(self):
    return TypeInfo(self)

  def _get_specified(self):
    return self._specified
  def _get_isId(self):
    return self._isId

  def _renameNode(self, namespaceURI, qualifiedName):
    owner= self._containerNode
    if owner is not None:
      owner.removeAttributeNode(self)
    NamedNodeNS._renameNode(self, namespaceURI, qualifiedName)
    if owner is not None:
      owner.setAttributeNodeNS(self)


class CharacterData(Node):
  def __init__(self, ownerDocument= None):
    Node.__init__(self, ownerDocument, None, None, None)
    self._data= ''
  def _cloneTo(self, node):
    Node._cloneTo(self, node)
    node._data= self._data

  _childTypes= []
  def _get_nodeName(self):
    return '#character-data'
  def _get_nodeValue(self):
    return self.data
  def _set_nodeValue(self, value):
    self.data= value

  def _get_data(self):
    return self._data
  def _get_length(self):
    return len(self._data)
  def _set_data(self, value):
    self._data= value

  def substringData(self, offset, count):
    if offset<0 or count<0 or offset>len(self._data):
      raise IndexSizeErr(self._data, offset)
    return self._data[offset:offset+count]
  def appendData(self, arg):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'data')
    self._data= self._data+arg
  def insertData(self, offset, arg):
    self.replaceData(offset, 0, arg)
  def deleteData(self, offset, count):
    self.replaceData(offset, count, '')
  def replaceData(self, offset, count, arg):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'data')
    if offset<0 or count<0 or offset>len(self._data):
      raise IndexSizeErr(self._data, offset)
    self._data= self._data[:offset]+arg+self._data[offset+count:]


class Comment(CharacterData):
  def _get_nodeType(self):
    return Node.COMMENT_NODE
  def _get_nodeName(self):
    return '#comment'


class Text(CharacterData):
  def _get_nodeType(self):
    return Node.TEXT_NODE
  def _get_nodeName(self):
    return '#text'

  def _get_isElementContentWhitespace(self, config= None):
    """ Return whether a node is whitespace in an element whose content model
        is declared in the document type as element-only (not ANY). If we
        don't know the content model, guess either ANY (by default), or
        element-only (if the appropriate config parameter is set).
    """
    # Find the nearest element ancestor, as we might be in nested entity
    # references.
    #
    pn= self.parentNode
    while pn is not None:
      if pn.nodeType==Node.ENTITY_REFERENCE_NODE:
        pn= pn.parentNode
        continue
      if pn.nodeType==Node.ELEMENT_NODE:
        break
      return False
    else:
      return False

    # Get the DOMConfiguration to look at - usually the current Document's,
    # but an LS process might pass an alternative in. Get the default content
    # model from this.
    #
    if config is None:
      config= self._ownerDocument.domConfig
    contentType= ElementDeclaration.ANY_CONTENT
    if config.getParameter('pxdom-assume-element-content'):
      contentType= ElementDeclaration.ELEMENT_CONTENT

    # See if the element has a different content model declared. If the final
    # content model is not element-only, can't be ECW.
    #
    if self._ownerDocument.doctype is not None:
      eldecl= self._ownerDocument.doctype._elements.getNamedItem(pn.nodeName)
      if eldecl is not None:
        contentType= eldecl.contentType
    if contentType!=ElementDeclaration.ELEMENT_CONTENT:
      return False

    # Finally check the node does only have whitespaces. (For it not to do so
    # would be invalid, but still well-formed.)
    #
    for c in self._data:
      if c not in ' \t\n':
        return False
    return True

  def splitText(self, offset):
    """ Move character data following the offset point from this node to a new
        (next sibling) node of the same type (could be subclass CDATASection).
    """
    newNode= self.cloneNode(False)
    self.deleteData(offset, len(self._data)-offset)
    newNode.deleteData(0, offset)
    if self.parentNode is not None:
      self.parentNode.insertBefore(newNode, self.nextSibling)
    return newNode


class CDATASection(Text):
  def _get_nodeType(self):
    return Node.CDATA_SECTION_NODE
  def _get_nodeName(self):
    return '#cdata-section'


class ProcessingInstruction(NamedNode):
  def __init__(self, ownerDocument= None, target= None):
    NamedNode.__init__(self, ownerDocument, target)
    self._data= ''
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._data= self._data

  _childTypes= []
  def _get_nodeType(self):
    return Node.PROCESSING_INSTRUCTION_NODE
  def _get_nodeValue(self):
    return self.data
  def _set_nodeValue(self, value):
    self.data= value

  def _get_target(self):
    return self.nodeName
  def _get_data(self):
    return self._data
  def _set_data(self, value):
    self._data= value


class EntityReference(NamedNode):
  def __init__(self, ownerDocument= None, nodeName= None, _strict= True):
    NamedNode.__init__(self, ownerDocument, nodeName, _strict)
    self.readonly= True
  def _recurse(self, deep, clone= False, ownerDocument= None, readonly= None):
    if clone:
      document= ownerDocument
      if document is None:
        document= self._ownerDocument
      return document.createEntityReference(self.nodeName)
    return Node._recurse(self, deep, clone, ownerDocument, readonly)
  def _get_nodeType(self):
    return Node.ENTITY_REFERENCE_NODE
  def _get_baseURI(self):
    if self.ownerDocument.doctype is not None:
      decl= self.ownerDocument.doctype.entities.getNamedItem(self.nodeName)
      if decl is not None:
        return decl.baseURI
    return None


class DocumentType(NamedNode):
  """ Implementation of DocumentType interface. Goes a little beyond the DOM 3
      interface in providing maps for attlists and entity declarations of the
      internal subset (attlists are required internally to support attribute
      defaulting).
  """
  def __init__(self,
    ownerDocument= None, name= None, publicId=None, systemId= None
  ):
    NamedNode.__init__(self, ownerDocument, name)
    self._publicId= publicId
    self._systemId= systemId
    self._internalSubset= None
    self._entities= NamedNodeMap(self, Node.ENTITY_NODE)
    self._notations= NamedNodeMap(self, Node.NOTATION_NODE)
    self._elements= NamedNodeMap(self, Node.ELEMENT_DECLARATION_NODE)
    self._attlists= NamedNodeMap(self, Node.ATTRIBUTE_LIST_NODE)
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._publicId= self._publicId
    node._systemId= self._systemId
    node._internalSubset= self._internalSubset
  def _get_nodeType(self):
    return Node.DOCUMENT_TYPE_NODE

  def _get_name(self):
    return self.nodeName
  def _get_publicId(self):
    return self._publicId
  def _get_systemId(self):
    return self._systemId
  def _get_internalSubset(self):
    return self._internalSubset
  def _get_entities(self):
    return self._entities
  def _get_notations(self):
    return self._notations
  def _get_pxdomElements(self):
    return self._elements
  def _get_pxdomAttlists(self):
    return self._attlists
  def _set_internalSubset(self, value):
    self._internalSubset= value
  def _get_baseURI(self):
    return None

  def createEntity(self, name, publicId, systemId, notationName):
    return Entity(self._ownerDocument, name, publicId, systemId, notationName)
  def createNotation(self, name, publicId, systemId):
    return Notation(self._ownerDocument, name, publicId, systemId)
  def createElementDeclaration(self, name, contentType, elements):
    return ElementDeclaration(self._ownerDocument, name, contentType,elements)
  def createAttributeListDeclaration(self, name):
    return AttributeListDeclaration(self._ownerDocument, name)
  def createAttributeDeclaration(self,
    name, attributeType, typeValues, defaultType
  ):
    return AttributeDeclaration(self._ownerDocument,
      name, attributeType, typeValues, defaultType
    )


class Entity(NamedNode):
  def __init__(self,
    ownerDocument= None, nodeName= None, publicId= None, systemId= None,
    notationName= None
  ):
    NamedNode.__init__(self, ownerDocument, nodeName)
    self._publicId= publicId
    self._systemId= systemId
    self._notationName= notationName
    self._xmlVersion= None
    self._xmlEncoding= None
    self._inputEncoding= None
    self._available= True
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._publicId= self._publicId
    node._systemId= self._systemId
    node._notationName= self._notationName
    node._xmlVersion= self._xmlVersion
    node._xmlEncoding= self._xmlEncoding
    node._inputEncoding= self._inputEncoding
    node._available= self._available
  def _get_nodeType(self):
    return Node.ENTITY_NODE
  def _get_parentNode(self):
    return None
  def _get_publicId(self):
    return self._publicId
  def _get_systemId(self):
    return self._systemId
  def _get_notationName(self):
    return self._notationName
  def _get_xmlVersion(self):
    return self._xmlVersion
  def _get_xmlEncoding(self):
    return self._xmlEncoding
  def _get_inputEncoding(self):
    return self._inputEncoding
  def _get_pxdomAvailable(self):
    return self._available

class Notation(NamedNode):
  def __init__(self,
    ownerDocument= None, nodeName= None, publicId= None, systemId= None
  ):
    NamedNode.__init__(self, ownerDocument, nodeName)
    self._publicId= publicId
    self._systemId= systemId
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._publicId= self._publicId
    node._systemId= self._systemId
  def _get_nodeType(self):
    return Node.NOTATION_NODE
  def _get_parentNode(self):
    return None
  def _get_publicId(self):
    return self._publicId
  def _get_systemId(self):
    return self._systemId


# Extended pxdom node classes for doctype parts not currently modelled in the
# standard DOM
# ============================================================================

class ElementDeclaration(NamedNode):
  """ Node representing an <!ELEMENT> declaration in document type. Prescribed
      content is described by 'contentType' and 'elements', which is null for
      EMPTY and ANY content, or a ContentDeclaration for Mixed and element
      content.
  """
  [EMPTY_CONTENT, ANY_CONTENT, MIXED_CONTENT, ELEMENT_CONTENT
  ]= range(1, 5)
  def __init__(
    self, ownerDocument= None, nodeName= None,
    contentType= ANY_CONTENT, elements= None
  ):
    NamedNode.__init__(self, ownerDocument, nodeName)
    self._contentType= contentType
    self._elements= elements
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._contentType= self._contentType
    node._elements= self._elements
  def _get_nodeType(self):
    return Node.ELEMENT_DECLARATION_NODE
  def _get_contentType(self):
    return self._contentType
  def _get_elements(self):
    return self._elements
  def _get_parentNode(self):
    return None


class ContentDeclaration(DOMList):
  """ A list representing part of the content model given in an <!ELEMENT>
      declaration. Apart from normal DOMList accessors, has flags specifying
      whether the group is optional, can be included more than once (or both),
      and whether it's a sequence or a choice. List items are element name
      strings or, in the case of element content, ContentDeclarations. In
      mixed content the initial #PCDATA is omitted and nesting is not used.
  """
  def __init__(self):
    DOMList.__init__(self)
    self._isOptional= False
    self._isMultiple= False
    self._isSequence= False
  def _get_isOptional(self):
    return self._isOptional
  def _get_isMultiple(self):
    return self._isMultiple
  def _get_isSequence(self):
    return self._isSequence
  def _set_isOptional(self, value):
    self._isOptional= value
  def _set_isMultiple(self, value):
    self._isMultiple= value
  def _set_isSequence(self, value):
    self._isSequence= value


class AttributeListDeclaration(NamedNode):
  def __init__(self, ownerDocument= None, nodeName= None):
    NamedNode.__init__(self, ownerDocument, nodeName)
    self._declarations= NamedNodeMap(self, Node.ATTRIBUTE_DECLARATION_NODE)
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
  def _get_nodeType(self):
    return Node.ATTRIBUTE_LIST_NODE
  def _get_parentNode(self):
    return None
  def _get_declarations(self):
    return self._declarations


class AttributeDeclaration(NamedNode):
  """ Node representing the declaration of a single attribute in an attlist.
      The type of attribute is made known, along with a list of values or
      notation names if the type is Enumeration or Notation. The defaulting
      is made known; if it is #FIXED or defaulted, the child Nodes of the
      declaration are the child nodes to be used by the attribute.
  """
  [REQUIRED_VALUE,IMPLIED_VALUE,DEFAULT_VALUE,FIXED_VALUE
  ]= range(1,5)
  [ID_ATTR,IDREF_ATTR,IDREFS_ATTR,ENTITY_ATTR,ENTITIES_ATTR,NMTOKEN_ATTR,
  NMTOKENS_ATTR,NOTATION_ATTR,CDATA_ATTR,ENUMERATION_ATTR
  ]= range(1,11)
  ATTR_NAMES= [ None,
    'ID', 'IDREF', 'IDREFS', 'ENTITY', 'ENTITIES', 'NMTOKEN', 'NMTOKENS',
    'NOTATION', 'CDATA', 'ENUMERATION'
  ]
  def __init__(self,
    ownerDocument= None, nodeName= None, attributeType= None,
    typeValues= None, defaultType= None
  ):
    NamedNode.__init__(self, ownerDocument, nodeName)
    self._attributeType= attributeType
    self._typeValues= typeValues
    self._defaultType= defaultType
  def _cloneTo(self, node):
    Node._cloneTo(self, node)
    node._attributeType= self.attributeType
    node._typeValues= self.typeValues
    node._defaultType= self.defaultType
  _childTypes= [Node.TEXT_NODE, Node.ENTITY_REFERENCE_NODE]
  def _get_nodeType(self):
    return Node.ATTRIBUTE_DECLARATION_NODE
  def _get_parentNode(self):
    return None
  def _get_attributeType(self):
    return self._attributeType
  def _get_typeValues(self):
    return self._typeValues
  def _get_defaultType(self):
    return self._defaultType
  def _get_nodeValue(self):
    return self.textContent

  def _createAttribute(self, element):
    prefix, localName= _splitName(self.nodeName)
    if localName is None:
      attr= element.ownerDocument.createAttribute(self.nodeName)
    else:
      if prefix is None:
        namespaceURI= None
      else:
        namespaceURI= element.lookupNamespaceURI(prefix)
      attr= element.ownerDocument.createAttributeNS(
        namespaceURI, self.nodeName, _strict= False
      )
    for child in self._childNodes:
      attr.appendChild(child.cloneNode(True))
    element.setAttributeNodeNS(attr)
    attr._specified= False


# Recursive node operations: clone, adopt, import (=clone+adopt) and, for
# entity-reference purporses, recursive-set-readonly.
# ============================================================================

def _Node__cloneNode(self, deep):
  """ Make an identical copy of a node, and optionally its descendants.
  """
  return self._recurse(deep, clone= True)


def _Document__adoptNode(self, source):
  """ Take over a node and its descendants from a potentially different
      document.
  """
  # Adoption of Documents and - for some reason - DocumentTypes is explicitly
  # disallowed by the spec.
  #
  if source.nodeType in (Node.DOCUMENT_NODE, Node.DOCUMENT_TYPE_NODE):
    raise NotSupportedErr(source, 'beAdopted')

  # Try to remove the node from wherever it is in the current document. If it
  # has a proper parent node this is easy; otherwise we have to guess which
  # of its owner's NamedNodeMaps it is part of. Note that removing an Entity
  # or Notation will generally fail as these maps are by default readonly.
  #
  if source.parentNode is not None:
    source.parentNode.removeChild(source)
  elif source._containerNode is not None:
    nodeMap= getattr(source._containerNode, {
      Node.ATTRIBUTE_NODE: 'attributes', Node.ENTITY_NODE: 'entities',
      Node.NOTATION_NODE: 'notations', Node. ATTRIBUTE_LIST_NODE: 'attlists',
      Node.ATTRIBUTE_DECLARATION_NODE: 'declarations',
      Node.ELEMENT_DECLARATION_NODE: 'elements'
    }[source.nodeType])
    nodeMap._writeItem(source, None)

  if source.nodeType==Node.ATTRIBUTE_NODE:
    source._specified= True
  dest= source._recurse(True, ownerDocument= self)
  dest._normalize(ents= True)
  return dest


def _Document__importNode(self, importedNode, deep):
  """ Make a copy of a node from another pxdom document, optionally
      including all descendants.
  """
  if importedNode.nodeType in (Node.DOCUMENT_NODE, Node.DOCUMENT_TYPE_NODE):
    raise NotSupportedErr(importedNode, 'importNode')
  return importedNode._recurse(deep, clone= True, ownerDocument= self)


def _Node___recurse(self,
  deep, clone= False, ownerDocument= None, readonly= None
):
  """ Perform operations on a node and, if 'deep', all its descendants
      recursively.
  """
  if clone:
    node= self.__class__()
    self._cloneTo(node)
  else:
    node= self

  if ownerDocument is not None:
    node._ownerDocument= ownerDocument
  self._recurseTo(node, clone, ownerDocument, readonly)

  if deep:
    node._childNodes.readonly= False
    for child in self._childNodes:
      r= child._recurse(deep, clone, ownerDocument, readonly)
      if clone:
        node._childNodes._append(r)
        r._containerNode= node
    node._childNodes.readonly= True

  if readonly is not None:
    node.readonly= readonly
    if node._attributes is not None:
      node._attributes.readonly= readonly

  if clone:
    if ownerDocument is not None:
      self._callUserDataHandlers(UserDataHandler.NODE_IMPORTED, self, node)
    else:
      self._callUserDataHandlers(UserDataHandler.NODE_CLONED, self, node)
  elif ownerDocument is not None:
    self._callUserDataHandlers(UserDataHandler.NODE_ADOPTED, self, None)
  return node

def _Attr___recurse(self,
  deep, clone= False, ownerDocument= None, readonly= None
):
  """ Recursive operations on attributes are always 'deep'.
  """
  return Node._recurse(self, True, clone, ownerDocument, readonly)


def _Node___recurseTo(self, node, clone, ownerDocument, readonly):
  """ Fire off recursive operations to child nodes and attributes. May be
      extended by specific node types to send the ops to other nodes they
      contain (not in child lists).
  """
  pass

def _Element___recurseTo(self, node, clone, ownerDocument, readonly):
  """ Elements pass recursive operations to their attributes. Non-specified
      attributes may be ignored (import), removed (adopt) or made specified
      (clone).
  """
  for attr in list(self._attributes._list):
    if not attr.specified:
      if (ownerDocument is not None and not clone):
        self.removeAttributeNode(attr)
      if (ownerDocument is not None):
        continue
    r= attr._recurse(True, clone, ownerDocument, readonly)
    if clone:
      node._attributes._append(r)
      r._containerNode= node
  node._setDefaultAttributes()

def _DocumentType___recurseTo(self, node, clone, ownerDocument, readonly):
  """ Distribute recursive operations to the nodes in a doctype's extra
      NamedNodeMaps.
  """
  for nodeMap in ('_entities', '_notations', '_elements', '_attlists'):
    for namedNode in getattr(self, nodeMap)._list:
      r= namedNode._recurse(True, clone, ownerDocument, readonly)
      if clone:
        getattr(node, nodeMap)._append(r)

def _AttributeListDeclaration____recurseTo(
  self, node, clone, ownerDocument, readonly
):
  """ Distribute recursive operations to attribute declaration nodes.
  """
  for declaration in self._declarations:
    r= declaration._recurse(True, clone, ownerDocument, readonly)
    if clone:
      node._declarations._append(r)


# DOM 3 namespace inspection
# ============================================================================

# Recursive namespace lookup backend. For non-Element nodes, just bubble the
# request up through ancestors.  In prefix lookups, a list of prefixes to
# ignore (because they are overridden in a descendant element) is passed up.
#
def _Node___lookupNamespaceURI(self, prefix):
  if self._containerNode is not None:
    return self._containerNode._lookupNamespaceURI(prefix)
  return None

def _Node___lookupPrefix(self, namespaceURI, exclude):
  if self._containerNode is not None:
    return self._containerNode._lookupPrefix(namespaceURI, exclude)
  return None


# Elements may return a value if their attributes match or their own
# namespaces/prefixes match what's being looked for. The latter behaviour can
# be turned off for internal purposes, during namespace fixup.
#
def _Element___lookupNamespaceURI(self, prefix, ignoreSelf= False):
  if not ignoreSelf and self.namespaceURI is not None and self.prefix==prefix:
    return self.namespaceURI
  localName= prefix
  if prefix is None:
    localName= 'xmlns'
  xmlns= self.attributes.getNamedItemNS(NSNS, localName)
  if xmlns is not None:
    return xmlns.value or None
  return NamedNodeNS._lookupNamespaceURI(self, prefix)

def _Element___lookupPrefix(self, namespaceURI, exclude, ignoreSelf= False):
  if not ignoreSelf and (
    self.prefix is not None and self.namespaceURI==namespaceURI
  ):
    return self.prefix
  for attr in self._attributes._list:
    if attr.prefix=='xmlns' and attr.localName not in exclude:
      if attr.value==namespaceURI:
        return attr.localName
      else:
        exclude.append(attr.localName)
  return NamedNodeNS._lookupPrefix(self, namespaceURI, exclude)


# If the search goes up to a DocumentType ancestor node, namespaceURI lookup
# fails, but we have to distinguish this case from going up to a Document and
# failing because in the case of isDefaultNamespace a different value is (for
# some reason) returned. Use the NONS singleton as a hack special value.
#
def _DocumentType___lookupNamespaceURI(self, prefix):
  return NONS


# Public lookup interface, weeding out the known results we don't need to
# search for, and dealing with the NONS hack.
#
def _Node__lookupNamespaceURI(self, prefix):
  if prefix=='xmlns':
    return NSNS
  if prefix=='xml':
    return XMNS
  localName= prefix
  namespaceURI= self._lookupNamespaceURI(localName)
  if namespaceURI==NONS:
    return None
  return namespaceURI

def _Node__lookupPrefix(self, namespaceURI):
  if namespaceURI in (None, ''):
    return None
  if namespaceURI==NSNS:
    return 'xmlns'
  if namespaceURI==XMNS:
    return 'xml'
  return self._lookupPrefix(namespaceURI, [])

def _Node__isDefaultNamespace(self, namespaceURI):
  if namespaceURI=='':
    namespaceURI= None
  return self._lookupNamespaceURI(None)==namespaceURI


# Public lookup on document node redirects to document root element.
#
def _Document__lookupNamespaceURI(self, prefix):
  root= self.documentElement
  if root is not None:
    return root.lookupNamespaceURI(prefix)
  return None

def _Document__lookupPrefix(self, namespaceURI):
  root= self.documentElement
  if root is not None:
    return root.lookupPrefix(namespaceURI)
  return None

def _Document__isDefaultNamespace(self, namespaceURI):
  root= self.documentElement
  if root is not None:
    return root.isDefaultNamespace(namespaceURI)
  return False


# DOM 3 node comparison
# ============================================================================

def _Node__isSameNode(self, other):
  return self is other


def _Node__isEqualNode(self, other):
  """ Check two nodes have the same properties and content.
  """
  ps=('nodeType','nodeName','localName','namespaceURI','prefix','nodeValue')
  for property in ps:
    if getattr(self, property)!=getattr(other, property):
      return False
  if (self.attributes is None)!=(other.attributes is None):
    return False
  if self.attributes is not None:
    if not self.attributes._isEqualMap(other.attributes):
      return False
  if self.childNodes.length!=other.childNodes.length:
    return False
  for index in range(self.childNodes.length):
    if not self.childNodes.item(index).isEqualNode(
      other.childNodes.item(index)
    ):
      return False
  return True

def _DocumentType__isEqualNode(self, other):
  """ Doctype nodes have additional properties that must match to be equal.
  """
  if not NamedNode.isEqualNode(self, other):
    return False
  ps= ('publicId', 'systemId', 'internalSubset')
  for property in ps:
    if getattr(self, property)!=getattr(other, property):
      return False
  if not self._entities._isEqualMap(other._entities):
    return False
  if not self._notations._isEqualMap(other._notations):
    return False
  return True


def _NamedNodeMap___isEqualMap(self, other):
  """ Test whether two maps have equal contents, though possibly in a
      different order.
  """
  if other is None:
    return False
  if len(self._list)!=len(other._list):
    return False
  for selfItem in self._list:
    for otherItem in other._list:
      if selfItem.isEqualNode(otherItem):
        break
    else:
      return False
  return True


def _canonicalAttrSort(self, other):
  """ Compare Attrs in terms of xmlnsness, namespaceURI and localName, for
      canonical-form ordering purposes.
  """
  if (self.namespaceURI==NSNS) and (other.namespaceURI==NSNS):
    if (self.prefix is None) != (other.prefix is None):
      return 1-(self.prefix is None)*2
    return cmp(self.localName, other.localName)
  if (self.namespaceURI==NSNS) != (other.namespaceURI==NSNS):
    return 1-(self.namespaceURI==NSNS)*2
  return cmp(
    (self.namespaceURI, self.localName),
    (other.namespaceURI, other.localName)
  )


def _Node__compareDocumentPosition(self, other):
  """ Get flags describing the document position of one node relative to
      another.
  """
  if other is self:
    return 0
  containers= []
  container= self
  while container is not None:
    containers.append(container)
    container= container._containerNode
  container= other
  other_determining= other
  while container is not None:
    if container in containers:
      index= containers.index(container)
      if index<1:
        index= 1
      self_determining= containers[index-1]
      break
    other_determining= container
    container= container._containerNode
  else:
    if id(other)>id(self):
      return (
        Node.DOCUMENT_POSITION_DISCONNECTED +
        Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
        Node.DOCUMENT_POSITION_FOLLOWING
      )
    return (
      Node.DOCUMENT_POSITION_DISCONNECTED +
      Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
      Node.DOCUMENT_POSITION_PRECEDING
    )
  if container is other:
    return (
      Node.DOCUMENT_POSITION_CONTAINS + Node.DOCUMENT_POSITION_PRECEDING
    )
  if container is self:
    return (
      Node.DOCUMENT_POSITION_CONTAINED_BY + Node.DOCUMENT_POSITION_FOLLOWING
    )
  if (other_determining in container._childNodes):
    if (self_determining in container._childNodes):
      if (
        container._childNodes._index(other_determining) >
        container._childNodes._index(self_determining)
      ):
        return Node.DOCUMENT_POSITION_FOLLOWING
      return Node.DOCUMENT_POSITION_PRECEDING
    return Node.DOCUMENT_POSITION_FOLLOWING
  if (self_determining in container._childNodes):
    return Node.DOCUMENT_POSITION_PRECEDING
  if other_determining.nodeType!=self_determining.nodeType:
    if other_determining.nodeType>self_determining.nodeType:
      return Node.DOCUMENT_POSITION_FOLLOWING
    return Node.DOCUMENT_POSITION_PRECEDING
  if self_determining.nodeType==Node.ATTRIBUTE_NODE:
    attrs= container.attributes
    if attrs._index(other_determining)>attrs._index(other_determining):
      return (
        Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
        Node.DOCUMENT_POSITION_FOLLOWING
      )
    return (
      Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
      Node.DOCUMENT_POSITION_PRECEDING
    )
  if id(other_determining)>id(self_determining):
    return (
      Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
      Node.DOCUMENT_POSITION_FOLLOWING
    )
  return (
    Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC +
    Node.DOCUMENT_POSITION_PRECEDING
  )


# DOM 3 textual content access
# ============================================================================

def _Node___set_textContent(self, value):
  if self.readonly:
    raise NoModificationAllowedErr(self, 'textContent')
  if (Node.TEXT_NODE not in self._childTypes):
    raise HierarchyRequestErr(self, Text())
  while self._childNodes.length>0:
    self.removeChild(self.firstChild)
  text= Text(self._ownerDocument)
  text.data= value
  self.appendChild(text)

def _CharacterData___set_textContent(self, value):
  if self.readonly:
    raise NoModificationAllowedErr(self, 'textContent')
  self.data= value
def _ProcessingInstruction___set_textContent(self, value):
  if self.readonly:
    raise NoModificationAllowedErr(self, 'textContent')
  self.data= value

def _Document___set_textContent(self, value):
  return
def _DocumentType___set_textContent(self, value):
  return
def _Notation___set_textContent(self, value):
  return


def _Node___get_textContent(self):
  value= ''
  for index in range(self._childNodes.length):
    child= self._childNodes.item(index)
    if child.nodeType not in [
      Node.COMMENT_NODE, Node.PROCESSING_INSTRUCTION_NODE
    ]:
      value= value+child.textContent
  return value

def _Attr___get_textContent(self):
  value= ''
  for index in range(self._childNodes.length):
    child= self._childNodes.item(index)
    if child.nodeType==Node.TEXT_NODE:
      value= value+child.textContent
    elif child.nodeType==Node.ENTITY_REFERENCE_NODE:
      value= value+r(r(r(child.textContent, '\n',' '), '\t',' '),'\r',' ')
  return value

def _CharacterData___get_textContent(self):
  return self.data

def _ProcessingInstruction___get_textContent(self):
  return self.data

def _Text___get_textContent(self):
  if self.isElementContentWhitespace:
    return ''
  return CharacterData._get_textContent(self)

def _Document___get_textContent(self):
  return None
def _DocumentType___get_textContent(self):
  return None
def _Notation___get_textContent(self):
  return None


def _Text___get_wholeText(self):
  value= ''
  for node in self._getLogicallyAdjacentTextNodes():
    value= value+node.data
  return value

def _Text__replaceWholeText(self, value):
  replacement= None
  haveReplaced= False
  if self._readonly and value!='':
    replacement= self._ownerDocument.createTextNode(value)
  nodes= self._getLogicallyAdjacentTextNodes()
  removables= []
  for node in nodes:
    if node is self and not (value=='' or self._readonly):
      continue
    while node.parentNode is not None:
      if not node.parentNode.readonly:
        if node not in removables:
          removables.append(node)
        break
      node= node.parentNode
  for removable in removables:
    descendants= []
    removable._getDescendants(descendants)
    for node in descendants:
      if node.nodeType!=Node.ENTITY_REFERENCE_NODE and node not in nodes:
        raise NoModificationAllowedErr(node.parentNode, 'removeChild')
    if replacement is not None and not haveReplaced:
      removable.parentNode.replaceChild(replacement, removable)
    else:
      removable.parentNode.removeChild(removable)
  if replacement is not None:
    return replacement
  if value=='':
    return None
  self._data= value
  return self

def _Text___getLogicallyAdjacentTextNodes(self):
  ok= (Node.TEXT_NODE, Node.CDATA_SECTION_NODE, Node.ENTITY_REFERENCE_NODE)
  node= self
  goin= False
  while True:
    previous= None
    if goin:
      previous= node.lastChild
    if previous is None:
      previous= node.previousSibling
      goin= True
    if previous is None:
      previous= node.parentNode
      goin= False
      if previous is None or previous.nodeType!=Node.ENTITY_REFERENCE_NODE:
        break
    if previous.nodeType not in ok:
      break
    node= previous
  nodes= []
  goin= True
  while True:
    if node.nodeType!=Node.ENTITY_REFERENCE_NODE:
      nodes.append(node)
    next= None
    if goin:
      next= node.firstChild
    if next is None:
      next= node.nextSibling
      goin= True
    if next is None:
      next= node.parentNode
      goin= False
      if next is None or next.nodeType!=Node.ENTITY_REFERENCE_NODE:
        break
    if next.nodeType not in ok:
      break
    node= next
  return nodes


# Normalization and canonicalization
# ============================================================================

def _Node__normalize(self):
  """ Perform text node concatenation and, if enabled in the domConfig,
      character normalisation.
  """
  if self._readonly:
    raise NoModificationAllowedErr(self, 'normalize')
  self._normalize(
    True, False, False, False, False, False, False, False, False, False,
    False, False, False, self._ownerDocument.domConfig._cnorm
  )
  self._changed()


def _Document__normalizeDocument(self):
  """ Perform all normalisations specified by the domConfig across the whole
      document.
  """
  # normalizeDocument doesn't return exceptions, even NO_MOD. Although there
  # is no reason a Document should ever be readonly anyway.
  #
  if self._readonly:
    return

  # Read normalisation-relevant parameters from the configuration.
  #
  unws= not self._domConfig.getParameter('element-content-whitespace')
  uncdata= not self._domConfig.getParameter('cdata-sections')
  uncomment= not self._domConfig.getParameter('comments')
  unent= not self._domConfig.getParameter('entities')
  unns= not self._domConfig.getParameter('namespaces')
  unnsattr= not self._domConfig.getParameter('namespace-declarations')
  wf= self._domConfig.getParameter('well-formed')
  cf= self._domConfig.getParameter('canonical-form')

  # In canonical-form mode, try to put exactly one newline character between
  # each root-level node, removing other whitespace.
  #
  if cf:
    needws= self._domConfig.getParameter('xml-declaration')
    for child in self.childNodes._list[:]:
      if child.nodeType in (Node.TEXT_NODE, Node.DOCUMENT_TYPE_NODE):
        self.removeChild(child)
        continue
      if needws:
        self.insertBefore(self.createTextNode('\n'), child)

  # Recursively normalise the document. Throw away DOMErrors, this method does
  # not return them other than to the error-handler.
  #
  try:
    self._normalize(
      True, True, True, True, True, unws, unnsattr, unns, uncdata,
      uncomment, unent, wf, cf, self.domConfig._cnorm
    )
  except DOMErrorException:
    pass
  self._changed()


def _Node___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisation back-end. Perform a number of different normalisations on
      child nodes, in the appropriate order.
  """

  # If necessary, replace entities with their contents before doing the rest.
  #
  if unent:
    for child in self._childNodes._list[:]:
      if child.nodeType==Node.ENTITY_REFERENCE_NODE:
        for grandchild in child.childNodes:
          grandchild= grandchild._recurse(True, clone= True, readonly= False)
          self.insertBefore(grandchild, child)
        self.removeChild(child)

  # Next pass, normalise children.
  #
  for child in self._childNodes._list[:]:
    child._normalize(
      text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
      uncomment, unent, wf, cf, cnorm
    )

    # Remove comments if unwanted
    #
    if uncomment and child.nodeType==Node.COMMENT_NODE:
      self.removeChild(child)
      continue

    # If unwanted, change CDATA sections to text nodes
    #
    if uncdata and child.nodeType==Node.CDATA_SECTION_NODE:
      newChild= self.ownerDocument.createTextNode(child.data)
      self.replaceChild(newChild, child)
      child= newChild

    # Concatenate adjacent text nodes, remove ignorable whitespace
    #
    if child.nodeType==Node.TEXT_NODE:
      if (text and child.data=='' or
        (unws and child.isElementContentWhitespace)
      ):
        self.removeChild(child)
        continue
      elif text:
        previous= child.previousSibling
        if previous is not None and previous.nodeType==Node.TEXT_NODE:
          previous.data= cnorm(previous.data+child.data, child)
          self.removeChild(child)

    # Split CDATA sections including string ']]>'
    #
    if child.nodeType==Node.CDATA_SECTION_NODE:
      if string.find(child.data, ']]>')!=-1:
        config= self._ownerDocument.domConfig
        if not config.getParameter('split-cdata-sections'):
          config._handleError(DOMErrorInvalidChar(child))
        else:
          datas= string.split(child.data, ']]>')
          child.data= datas[0]
          refChild= child.nextSibling
          for data in datas[1:]:
            newChild= self._ownerDocument.createTextNode(']]>')
            self.insertBefore(newChild, refChild)
            newChild=self._ownerDocument.createCDATASection(cnorm(data,child))
            self.insertBefore(newChild, refChild)
          config._handleError(DOMErrorCdataSectionSplitted(child))

  # Some forms of normalisation might require NodeListByTagNames recalculated.
  # Don't bother bounce up to parents as with the normal _changed() method, as
  # they will already know.
  #
  self._sequence= self._sequence+1


def _NamedNode___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations required by namespace-aware nodes. Additionally to
      general node normalisations, character-normalise the node name. This
      could theoretically lead to two nodes of the same name in a
      NamedNodeMap; the DOM spec doesn't seem to say what to do in this
      situation, so for the moment we let it be.
  """
  self._nodeName= cnorm(self._nodeName, self)
  Node._normalize(
    self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )


def _NamedNodeNS___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations required by namespace-aware nodes. Additionally to
      general node normalisations, try to fix up our namespace if it is
      possibly unbound in an entity but bound in the entity reference,
      and character-normalise name parts.
  """
  if ents:
    if self._prefix is not None and self._namespaceURI is None:
      self._namespaceURI= self._lookupNamespaceURI(self._prefix)
  self._localName= cnorm(self._localName, self)
  if self._prefix is not None:
    self._prefix= cnorm(self._prefix, self)
  Node._normalize(
    self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )


def _Element___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations required by elements. Additionally to general named node
      normalisations, may need to add namespace declarations make it
      namespace-well-formed, and normalise or remove some attributes.
  """
  NamedNodeNS._normalize(
    self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )

  # Fixup element namespace
  #
  if ns and self._namespaceURI!=NONS:
    if self._lookupNamespaceURI(self._prefix, True)!=self._namespaceURI:
      if self._prefix is None:
        if self._namespaceURI is None:
          self.setAttributeNS(NSNS, 'xmlns', '')
        else:
          self.setAttributeNS(NSNS, 'xmlns', self._namespaceURI)
      elif self._namespaceURI is not None:
        self.setAttributeNS(NSNS, 'xmlns:'+self._prefix, self._namespaceURI)

  # Normalise each attribute, reordered if in canonical-form mode.
  #
  for attr in list(self._attributes._list):
    attr._normalize(
      text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
      uncomment, unent, wf, cf, cnorm
    )
  if cf:
    self._attributes._list.sort(_canonicalAttrSort)
  for attr in list(self._attributes._list):

    # Work out whether to remove it. An attribute may be removed if it is
    # a namespace declaration and is redundant in canonical-form mode or
    # declarations are disabled entirely.
    #
    u= False
    if attr.namespaceURI==NSNS:
      u= unnsattr
      if cf and not u:
        prefix= [attr.localName, None][attr.prefix is None]
        value= None
        if self.parentNode is not None:
          value= self.parentNode._lookupNamespaceURI(prefix)
        if attr.value==(value or ''):
          u= True
    if u:
      self.removeAttributeNode(attr, None)


def _Attr___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations required by attribute nodes. In addition to general named
      node normalisations, may add namespace declarations for fixup.
  """
  NamedNodeNS._normalize(
    self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )

  # Fixup attribute namespace, adding new declarations to the parent if
  # we need to add a new namespace to do so
  #
  if ns and self._containerNode is not None and (
    self._namespaceURI not in (NONS, NSNS, XMNS)
  ):
    if self._prefix is None:
      prefixNamespace= None
    else:
      prefixNamespace=self._containerNode._lookupNamespaceURI(self._prefix,True)
    if prefixNamespace!=self._namespaceURI:
      if not self._specified:
        self._namespaceURI= prefixNamespace
      elif self._namespaceURI is None:
        self._prefix= None
      else:
        prefix= self._containerNode._lookupPrefix(self._namespaceURI,[], True)
        if prefix is None:
          if self._prefix is not None and prefixNamespace is None:
            prefix= self._prefix
          else:
            nsSuffix= 1
            while True:
              prefix= 'NS'+str(nsSuffix)
              if self._containerNode._lookupNamespaceURI(prefix,True) is None:
                break
              nsSuffix= nsSuffix+1
          self._containerNode.setAttributeNS(
            NSNS, 'xmlns:'+prefix, self._namespaceURI
          )
        self._prefix= prefix


def _CharacterData___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations for text-based nodes. Only need to normalise characters.
  """
  Node._normalize(self,
    atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )
  self._data= cnorm(self._data, self)


def _Comment___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations for comment nodes. Only need to check well-formedness.
  """
  CharacterData._normalize(self,
    atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )
  if wf and (self._data[-1:]=='-' or string.find(self._data, '--'))!=-1:
    self.ownerDocument.domConfig._handleError(DOMErrorInvalidChar(self))


def _ProcessingInstruction___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations for PI nodes. Only need to check well-formedness.
  """
  NamedNode._normalize(self,
    atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )
  if wf and string.find(self._data, '?>')!=-1:
    self.ownerDocument.domConfig._handleError(DOMErrorInvalidChar(self))


def _EntityReference___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Normalisations for entity references. Remove any child nodes and replace
      them with up-to-date replacement nodes from the doctype's entity list.
  """
  if ents:
    self.readonly= False
    while self._childNodes.length>0:
      self.removeChild(self._childNodes.item(0))
    if self._ownerDocument.doctype:
      entity=self._ownerDocument.doctype.entities.getNamedItem(self.nodeName)
      if entity is not None:
        for child in entity.childNodes:
          clone= child._recurse(True, clone= True)
          self.appendChild(clone)
    NamedNode._normalize(
      self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
      uncomment, unent, wf, cf, cnorm
    )
    for child in self._childNodes:
      child._recurse(True, readonly= True)
    self.readonly= True


def _DocumentType___normalize(self, text= False,
  atts= False, ents= False, ns= False, cdata= False, unws= False,
  unnsattr= False, unns= False, uncdata= False, uncomment= False,
  unent= False, wf= False, cf= False, cnorm= _identity
):
  """ Document type node normalisations: just remove the entities collection
      if no entity references were wanted.
  """
  NamedNode._normalize(
    self, text, atts, ents, ns, cdata, unws, unnsattr, unns, uncdata,
    uncomment, unent, wf, cf, cnorm
  )
  if unent:
    while self._entities.length>0:
      self._entities._writeItem(self._entities.item(0), None)


# DOM 3 LS Load features
# ============================================================================

def _DOMImplementation__createLSParser(
  self, mode= DOMImplementation.MODE_SYNCHRONOUS, schemaType= None
):
  if mode!=DOMImplementation.MODE_SYNCHRONOUS:
    raise NotSupportedErr(self, 'createLSParser.mode')
  if schemaType is not None and schemaType!=DTNS:
    raise NotSupportedErr(self, 'createLSParser.schemaType')
  return LSParser()

def _DOMImplementation__createLSInput(self):
  return LSInput()


class LSInput(DOMObject):
  """ Abstraction of possible source of serialised XML data. Can have
      character or byte stream objects attached (in Python terms, objects
      having a read() method that returns Unicode or narrow strings,
      respectively), plain string input (either type) or a resolvable Id/URI
      to get data from.
  """
  def __init__(self):
    DOMObject.__init__(self)
    self._characterStream= None
    self._byteStream= None
    self._stringData= None
    self._systemId= None
    self._publicId= None
    self._baseURI= None
    self._encoding= None
    self._certifiedText= False

  def _get_characterStream(self): return self._characterStream
  def _get_byteStream(self): return self._byteStream
  def _get_stringData(self): return self._stringData
  def _get_systemId(self): return self._systemId
  def _get_publicId(self): return self._publicId
  def _get_baseURI(self): return self._baseURI
  def _get_encoding(self): return self._encoding
  def _get_certifiedText(self): return self._certifiedText

  def _set_characterStream(self, value):
    self._characterStream= value
  def _set_byteStream(self, value):
    self._byteStream= value
  def _set_stringData(self, value):
    self._stringData= value
  def _set_systemId(self, value):
    self._systemId= value
  def _set_publicId(self, value):
    self._publicId= value
  def _set_baseURI(self, value):
    self._baseURI= value
  def _set_encoding(self, value):
    self._encoding= value
  def _set_certifiedText(self, value):
    self._certifiedText= value


class InputBuffer:
  """ Utility wrapper for an object implementing the LSInput interface (which
      could be a user-created object which is why we can't just put this in
      the LSInput class. For byteStream and systemId inputs, read the raw
      content from the stream and store it so it can be read more than once if
      encodings change.
  """
  _xmlTypes= [
    'text/xml', 'application/xml', 'application/xml-dtd', 'text/xsl'
    'text/xml-external-parsed-entity','application/xml-external-parsed-entity'
  ]

  def __init__(self, input, config):
    self._bytes= None
    self._characters= None
    self._encoding= None
    self._fixed= False
    self.inputEncoding= None
    self.uri= input.baseURI

    if input.characterStream is not None:
      self._characters= input.characterStream.read()
    elif input.byteStream is not None:
      self._bytes= input.byteStream.read()
      if input.encoding is not None:
        self._encoding= input.encoding
        self._fixed= True
    elif input.stringData not in (None, ''):
      self._characters= input.stringData

    elif input.systemId is not None:
      self.uri= input.systemId
      if input.baseURI is not None:
        self.uri= urlparse.urljoin(input.baseURI, self.uri)
      try:
        stream= urllib.urlopen(self.uri)
      except IOError, e:
        config._handleError(DOMErrorIOError(e))
      if config.getParameter('supported-media-types-only'):
        contentType= stream.info().type
        if contentType not in self._xmlTypes and contentType[-4:]!='+xml':
          config._handleError(DOMErrorUnsupportedType(None))
      if input.encoding is not None:
        self._encoding= input.encoding
        self._fixed= True
      else:
        self._encoding= stream.info().getparam('charset')
        if self._encoding is not None:
          self._fixed= config.getParameter('charset-overrides-xml-encoding')
      self._bytes= stream.read()
      stream.close()

    else:
      config._handleError(DOMErrorNoInput(None))

  def read(self, xmlEncoding= None):
    """ Return the stored data as a decoded stream of characters. Use the
        xmlEncoding, if given, if an encoding is needed but at this point
        still not certain. Store the encoding we actually ended up using in
        inputEncoding so LSParser can read it back.
    """
    if self._characters is not None:
      if unicode and isinstance(self._characters, type(unicode(''))):
        self.inputEncoding= nativeEncoding
      return self._characters
    if self._bytes is None:
      return ''

    encoding= self._encoding
    if xmlEncoding is not None and not self._fixed:
      encoding= xmlEncoding
    if encoding is None or string.lower(encoding)=='utf-16':
      if self._bytes[:2] in ('\xff\xfe', '\xfe\xff'):
        encoding= 'utf-16'+['be', 'le'][self._bytes[:2]=='\xff\xfe']
    self.inputEncoding= encoding or 'utf-8'
    if unicode is None:
      return r(r(r(self._bytes, EBCLS, '\n'), '\r\n', '\n'), '\r', '\n')
    else:
      try:
        data= unicode(self._bytes, self.inputEncoding)
      except LookupError:
        raise DOMErrorUnsupportedEncoding(None)
      if data[:1]==unichr(0xFEFF):
        data= data[1:]
      return r(r(r(r(data,EBCLS,'\n'),'\r\n','\n'),'\r','\n'),UNILS,'\n')


class NodeFilter(DOMObject):
  [SHOW_ELEMENT,SHOW_ATTRIBUTE,SHOW_TEXT,SHOW_CDATA_SECTION,
  SHOW_ENTITY_REFERENCE,SHOW_ENTITY,SHOW_PROCESSING_INSTRUCTION,SHOW_COMMENT,
  SHOW_DOCUMENT,SHOW_DOCUMENT_TYPE,SHOW_DOCUMENT_FRAGMENT,SHOW_NOTATION
  ]= map(lambda n: 2**n, range(1, 13))
  SHOW_ALL= 2**13-1;
  [FILTER_ACCEPT,FILTER_REJECT,FILTER_SKIP,FILTER_INTERRUPT
  ]= range(1, 5)
  def __init__(whatToShow):
    DOMObject.__init__()
    self._whatToShow= whatToShow
  def _get_whatToShow(self):
    return self._whatToShow
  def _set_whatToShow(self, value):
    self._whatToShow= value
  def acceptNode(self, n):
    return NodeFilter.FILTER_ACCEPT

class LSParserFilter(NodeFilter):
  def acceptNode(self, nodeArg): # different argument name - spec wart
    return NodeFilter.FILTER_ACCEPT
  def startElement(self, elementArg):
    return NodeFilter.FILTER_ACCEPT
class LSSerializerFilter(NodeFilter):
  pass


def _acceptNode(filter, node, startElement= False):
  """ Convenience function to pass a node to a filter, if it exists and wants
      to see it, and return the result or the right default. 
  """
  if filter is None:
    return NodeFilter.FILTER_ACCEPT
  if node.nodeType>=32 or (filter.whatToShow & (1<<(node.nodeType-1)) == 0):
    return NodeFilter.FILTER_ACCEPT
  if startElement:
    accepted= filter.startElement(node)
  else:
    accepted= filter.acceptNode(node)
  if accepted==NodeFilter.FILTER_INTERRUPT:
    raise LSFilterInterrupt()
  return accepted

class LSFilterInterrupt(Exception):
  """ Exception raised when an LSFilter has returned a FILTER_INTERRUPT, 
      causing the process to stop and return to the caller.
  """
  pass


class LSParser(DOMObject):
  """ DOM Level 3 LS  XML parser.
  """
  [ACTION_APPEND_AS_CHILDREN,ACTION_REPLACE_CHILDREN,ACTION_INSERT_BEFORE,
  ACTION_INSERT_AFTER,ACTION_REPLACE
  ]= range(1, 6)
  _CHARCHUNK= 1024
  def __init__(self, config= None):
    DOMObject.__init__(self)
    if config is None:
      config= ParserConfiguration()
      config.setParameter('entities', False)
      config.setParameter('cdata-sections', False)
    self._domConfig= config
    self._filter= None
    self._data= ''
    self._index= 0
  def _get_domConfig(self):
    return self._domConfig
  def _get_filter(self):
    return self._filter
  def _set_filter(self, value):
    self._filter= value
  def _get_async(self):
    return False
  def _get_busy(self):
    return False
  def abort(self):
    pass
  def _e(self, message):
    self._domConfig._handleError(ParseError(self, message))
  def parseURI(self, uri):
    input= LSInput()
    input.systemId= uri
    return self.parse(input)

  def parse(self, input):
    # Create document and load serialised form for parsing
    #
    document= Document()
    try:
      self._buffer= InputBuffer(input, self._domConfig)
      self._data= self._buffer.read()
      self._index= 0
      self._parseEntity(document, None)
    except DOMErrorException, e:
      raise ParseErr(e)
    self._buffer= None

   # Not all DOM 3 LS normalizations can be done at the parse phase. See if
   # there is anything we will have to do in a subsequent normalisation step.
   # This includes whitespace removal, namespace declaration removal, and, if
   # the input is not XML 1.1 certified, Unicode character normalisation.
   #
    if not self._domConfig.getParameter('entities'):
      if document.doctype is not None:
        document.doctype._entities= NamedNodeMap(
          document.doctype, Node.ENTITY_NODE
        )
    unnsattr= not self._domConfig.getParameter('namespace-declarations')
    unws= not self._domConfig.getParameter('element-content-whitespace')
    cnorm= ( (
      self._domConfig.getParameter('normalize-characters') or
      self._domConfig.getParameter('check-character-normalization')
    ) and not input.certifiedText )
    if unnsattr or unws or cnorm:

      # Call the normalisation step. The 'assume' parameter has to be hacked
      # in to the document's domConfig as it gets used directly during the
      # normalisation process (because of an isElementContentWhitespace call).
      #
      if unws:
        assume=document.domConfig.getParameter('pxdom-assume-element-content')
        document.domConfig.setParameter('pxdom-assume-element-content',
          self._domConfig.getParameter('pxdom-assume-element-content')
        )
      try:
        document._normalize(
          unnsattr= unnsattr, unws= unws, cnorm= self._domConfig._cnorm
        )
      except DOMErrorException, e:
        raise ParseErr(e)
      if unws:
        document.domConfig.setParameter('pxdom-assume-element-content',assume)
    return document


  def parseWithContext(self, input, contextArg, action):
    # Find the node that will contain the new content, either the contextArg
    # or, for certain actions, its parent. Check it can receive content.
    #
    pnode= [contextArg.parentNode, contextArg][action in (
      LSParser.ACTION_APPEND_AS_CHILDREN, LSParser.ACTION_REPLACE_CHILDREN
    )]
    if pnode is None or pnode.nodeType not in (
      Node.DOCUMENT_NODE, Node.ELEMENT_NODE, Node.DOCUMENT_FRAGMENT_NODE
    ):
      raise NotSupportedErr([pnode,contextArg][pnode is None], 'context')

    self._buffer= InputBuffer(input, self._domConfig)
    self._data= self._buffer.read()
    self._index= 0

    try:
      if action==LSParser.ACTION_REPLACE_CHILDREN:
        while contextArg.childNodes.length>0:
          contextArg.removeChild(contextArg.childNodes.item(0))
        self._parseEntity(contextArg, None)
        results= contextArg.childNodes._list

      elif action==LSParser.ACTION_APPEND_AS_CHILDREN:
        index= contextArg.childNodes.length
        self._parseEntity(contextArg, None)
        results= contextArg.childNodes._list[index:]
   
      elif action==LSParser.ACTION_INSERT_BEFORE:
        previousSibling= contextArg.previousSibling
        self._parseEntity(contextArg.parentNode, contextArg)
        results= []
        while True:
          previousSibling= previousSibling.nextSibling
          if previousSibling is contextArg:
            break
          results.append(previousSibling)
   
      elif action==LSParser.ACTION_INSERT_AFTER:
        nextSibling= contextArg.nextSibling
        self._parseEntity(contextArg.parentNode, nextSibling)
        results= []
        node= contextArg
        while True:
          node= node.nextSibling
          if node is nextSibling:
            break
          results.append(node)
   
      elif action==LSParser.ACTION_REPLACE:
        previousSibling= contextArg.previousSibling
        nextSibling= contextArg.nextSibling
        parentNode= contextArg.parentNode
        parentNode.removeChild(contextArg)
        self._parseEntity(parentNode, nextSibling)
        results= []
        while True:
          previousSibling= previousSibling.nextSibling
          if previousSibling is nextSibling:
            break
          results.append(previousSibling)

      if self._index<len(self._data):
        self._e('Expected end of input')
      self._buffer= None
    except DOMErrorException, e:
      raise ParseErr(e)

    # Post-parsing normalisation for with-context parsing. Note for some
    # reason, according to spec, element-content-whitespace normalisation is
    # not done in parseWithContext at all.
    #
    unnsattr= not self._domConfig.getParameter('namespace-declarations')
    cnorm= not input.certifiedText and (
      self._domConfig.getParameter('normalize-characters') or
      self._domConfig.getParameter('check-character-normalization')
    )
    if unnsattr or cnorm:
      cnorm= [_identity, self._domConfig._cnorm][cnorm]
      try:
        for result in results:
          result._normalize(unnsattr= unnsattr, cnorm= cnorm)
      except DOMErrorException, e:
        raise ParseErr(e)

    if len(results)==0:
      return None
    return results[0]


  def _parseEntity(self, parentNode, refChild):
    """ Parse a document entity or external parsed entity. Check for an XML/
        text declaration, then get on with parsing content.
    """
    xmlVersion= None
    xmlEncoding= None
    xmlStandalone= None
    if self._next('<?xml'):
      self._p_s()
      if not self._next('version'):
        self._e('Expected \'version="..."\'')
      self._p_eq()
      xmlVersion= self._p_lit()
      if not self._next('?>', False):
        self._p_s()
      if self._next('encoding'):
        self._p_eq()
        xmlEncoding= self._p_lit()
        if not self._next('?>', False):
          self._p_s()
      if self._next('standalone'):
        self._p_eq()
        standalone= self._p_lit()
        if standalone not in ('no', 'yes'):
          self._e('Expected \'no\' or \'yes\'')
        xmlStandalone= (standalone=='yes')
        self._p_s(False)
      if not self._next('?>', True):
        self._e('Expected \'?>\'')

    # If a new encoding was specified in the declaration, switch to it and
    # re-get the input with the new encoding.
    #
    if xmlEncoding not in (None, self._buffer.inputEncoding):
      self._data= self._buffer.read(xmlEncoding)

    # If the parentNode is a document or external parsed entity, can record
    # some of these details.
    #
    if parentNode.nodeType in (Node.DOCUMENT_NODE, Node.ENTITY_NODE):
      parentNode._xmlVersion= xmlVersion or '1.0'
      parentNode._xmlEncoding= xmlEncoding
      parentNode._inputEncoding= self._buffer.inputEncoding
    if parentNode.nodeType==Node.DOCUMENT_NODE:
      parentNode._xmlStandalone= xmlStandalone
      if self._buffer.uri is not None:
        parentNode._documentURI= self._buffer.uri


    # Enter the main, recursive content-parsing loop for root-level children.
    #
    self._textQueue= ''
    try:
      self._parseContent(parentNode, refChild)
    except LSFilterInterrupt:
      pass


  # Low-level input reading
  #
  def _next(self, data, skip= True):
    isNext= self._data[self._index:self._index+len(data)]==data
    if skip and isNext:
      self._index= self._index+len(data)
    return isNext
  def _find(self, chars):
    finds= []
    for char in chars:
      ix= string.find(self._data, char, self._index)
      if ix!=-1:
        finds.append(ix)
    if len(finds)==0:
      return len(self._data)
    return min(finds)
  def _p_s(self, required= True):
    start= self._index
    l= len(self._data)
    while self._index<l and self._data[self._index] in ' \t\n':
      self._index= self._index+1
    if required and self._index==start:
      self._e('Expected whitespace')
    return self._data[start:self._index]
  def _p_q(self):
    if self._index<len(self._data):
      quote= self._data[self._index]
      if quote in '"\'':
        self._index= self._index+1
        return quote
    self._e('Expected open-quote \'"\' or \'\'\'')
  def _p_eq(self):
    start= self._index
    self._p_s(False)
    if not self._next('='):
      self._e('Expected \'=\'')
    self._p_s(False)
    return self._data[start:self._index]
  def _p_lit(self):
    start= self._index
    quote= self._p_q()
    index= string.find(self._data, quote, self._index+1)
    if index==-1:
      self._e('Unclosed literal, no folowing \'%s\'' % quote)
    self._index= index+1
    return self._data[start+1: self._index-1]
  def _p_name(self):
    start= self._index
    l= len(self._data)
    if self._index<l and self._data[self._index] not in _NOTFIRST:
      self._index= self._index+1
      while self._index<l and self._data[self._index] not in _NOTNAME:
        self._index= self._index+1
    if self._index==start:
      self._e('Expected name')
    return self._data[start:self._index]
  _HEX= '0123456789abcdefABDCDEF'
  def _p_hex(self):
    start= self._index
    l= len(self._data)
    while self._index<l and self._data[self._index] in self._HEX:
      self._index= self._index+1
    if self._index==start:
      self._e('Expected hex value')
    return eval('0x'+str(self._data[start:self._index]))
  _DEC= '0123456789'
  def _p_dec(self):
    start= self._index
    l= len(self._data)
    while self._index<l and self._data[self._index] in self._DEC:
      self._index= self._index+1
    if self._index==start:
      self._e('Expected hex value')
    return int(self._data[start:self._index])
  def _p_enum(self):
    if not self._next('('):
      self._e('Expected \'(\' to begin enum list')
    self._p_s(False)
    names= []
    while True:
      names.append(self._p_name())
      self._p_s(False)
      if not self._next('|'):
        break
      self._p_s(False)
    if not self._next(')'):
      self._e('Expected \')\' to end enum list')
    return names

  def _p_cdecl(self, isMixed= False, isRoot= True):
    elements= ContentDeclaration()
    elements.isSequence= None
    while True:
      self._p_s(False)
      if isMixed:
        element= self._p_name()
      else:
        if self._next('('):
          element= self._p_cdecl(False, False)
        else:
          element= ContentDeclaration()
          element._append(self._p_name())
        self._p_cdecl_checkSuffix(element)
      elements._append(element)
      self._p_s(False)
      if self._next(')'):
        break
      if self._next('|'):
        sequence= False
      elif self._next(','):
        sequence= True
      else:
        self._e('Expected \'|\' or \',\' to continue declaration list')
      if elements.isSequence not in (None, sequence):
        self._e('Content declaration cannot be both choice and sequence')
      elements.isSequence= sequence
    if isRoot:
      self._p_cdecl_checkSuffix(elements)
    return elements
  def _p_cdecl_checkSuffix(self, cdecl):
    if self._next('*'):
      cdecl.isOptional= True
      cdecl.isMultiple= True
    elif self._next('+'):
      cdecl.isMultiple= True
    elif self._next('?'):
      cdecl.isOptional= True

  def _flushText(self, parentNode, refChild):
    if self._textQueue=='':
      return
    text= parentNode._ownerDocument.createTextNode(self._textQueue)
    self._textQueue= ''
    text._setLocation(self._getLocation())
    self._insertFiltered(text, parentNode, refChild)

  def _insertFiltered(self, newNode, parentNode, refChild, norm= False):
    """ Utility method to insert a node into a specific place in the document
        (normalised it if it's an entref) and then find out the filter's point
        of view if any, possibly removing or skipping it afterwards.
    """
    parentNode.insertBefore(newNode, refChild)
    if norm:
      newNode._normalize(ents= True)
    accepted= _acceptNode(self._filter, newNode)
    if accepted==LSParserFilter.FILTER_REJECT:
      parentNode.removeChild(newNode)
    elif accepted==LSParserFilter.FILTER_SKIP:
      while newNode.firstChild is not None:
        parentNode.insertBefore(newNode.firstChild, newNode)
      parentNode.removeChild(newNode)

  # High-level parsing
  #
  def _parseContent(self, parentNode, refChild):
    while True:
      index= self._find('<&')
      if index>self._index:
        self._textQueue= self._textQueue+ self._data[self._index:index]
        self._index= index
      if self._next('<'): 
        if self._next('?'):
          self._parseProcessingInstruction(parentNode, refChild)
        elif self._next('!'):
          if self._next('['):
            if self._next('CDATA['):
              self._parseCDATASection(parentNode, refChild)
            else:
              self._e('Expected \'CDATA[...]\'')
          elif self._next('DOCTYPE'):
            if (parentNode.nodeType!=Node.DOCUMENT_NODE or
              parentNode.documentElement is not None
            ):
              self._e('Doctype must come before root element')
            if parentNode._ownerDocument.doctype is not None:
              self._e('Only one doctype is allowed')
            if self._domConfig.getParameter('disallow-doctype'):
              self._domConfig._handleError(DOMErrorDoctypeNotAllowed(None))
            self._flushText(parentNode, refChild)
            self._parseDoctype(parentNode, refChild)
          elif self._next('--'):
            self._parseComment(parentNode, refChild)
          else:
            self._e('Expected \'--\' \'DOCTYPE\' or \'[...]\'')
        else:
          if self._next('/'):
            break
          else:
            if (parentNode.nodeType==Node.DOCUMENT_NODE and
              parentNode.documentElement is not None
            ):
              self._e('Only one root element is allowed')
            self._parseElement(parentNode, refChild)
      elif self._next('&'):
        if self._next('#'):
          self._parseCharacterReference(parentNode, refChild)
        else:
          self._parseEntityReference(parentNode, refChild)
      else:
        break
    self._flushText(parentNode, refChild)

  def _parseElement(self, parentNode, refChild):
    self._flushText(parentNode, refChild)
    nons= not self._domConfig.getParameter('namespaces')
    qualifiedName= self._p_name()
    try:
      element= parentNode._ownerDocument.createElementNS(
        None, qualifiedName, _strict= False, _default= False
      )
    except NamespaceErr:
      element= parentNode._ownerDocument.createElement(qualifiedName)
    element._setLocation(self._getLocation())
    fixups= []
    empty= False

    # Loop over attributes
    #
    while True:
      ws= self._p_s(False)
      if self._next('>'):
        break
      if self._next('/>'):
        empty= True
        break
      if not ws:
        self._e('Expected whitespace')

      # Parse attribute and add Attr node
      #
      qualifiedName= self._p_name()
      (prefix, localName)= _splitName(qualifiedName)
      try:
        if prefix=='xmlns' or prefix is None and localName=='xmlns':
          attr= parentNode._ownerDocument.createAttributeNS(
            NSNS, qualifiedName, _strict= False
          )
        elif prefix=='xml':
          attr= parentNode._ownerDocument.createAttributeNS(
            XMNS, qualifiedName, _strict= False
          )
        else:
          attr= parentNode._ownerDocument.createAttributeNS(
            None, qualifiedName, _strict= False
          )
      except NamespaceErr:
        attr= parentNode._ownerDocument.createAttribute(qualifiedName)
      self._p_eq()
      self._index= self._index+1
      attr._setLocation(self._getLocation())
      self._index= self._index-1
      filter= self._filter
      self._filter= None
      try:
        self._parseAttributeValue(attr, None)
      finally:
        self._filter= filter
      if element.setAttributeNode(attr) is not None:
        self._e('Attribute \'%s\' given more than once' % qualifiedName)
      if attr.schemaTypeInfo.typeName=='ID':
        element.setIdAttributeNode(attr, True)
      if attr.namespaceURI is None:
        fixups.append(attr)

    # Put the element into the document, then fix up namespace values for the
    # element and any non-xmlns attributes, dependent on the new position.
    #
    parentNode.insertBefore(element, refChild)
    if element.localName is not None:
      element._namespaceURI= element.lookupNamespaceURI(element.prefix)
    for attr in fixups:
      if attr.namespaceURI is None and attr.prefix is not None:
        attr._namespaceURI= element.lookupNamespaceURI(attr.prefix)
    element._setDefaultAttributes()

    # Check that filter allows the element to be added. If not, we will still
    # have to parse all the following stuff without telling the filter we're
    # doing so, and throw the results away.
    #
    if parentNode.nodeType==Node.DOCUMENT_NODE:
      accepted= LSParserFilter.FILTER_ACCEPT
    else:
      accepted= _acceptNode(self._filter, element, startElement= True)

    if accepted==LSParserFilter.FILTER_REJECT:
      if not empty:
        filter= self._filter
        self._filter= None
        self._parseContent(element, None)
        self._filter= filter
      parentNode.removeChild(element)

    elif accepted==LSParserFilter.FILTER_SKIP:
      parentNode.removeChild(element)
      if not empty:
        self._parseContent(parentNode, refChild)

    elif not empty:
      self._parseContent(element, None)

    # After parsing all the content into the element, ask the filter again
    # what to do with it. insertFiltered is used; it doesn't matter that the
    # node is already inserted as the second insert will have no effect.
    #
    if accepted==LSParserFilter.FILTER_ACCEPT:
      if parentNode.nodeType==Node.DOCUMENT_NODE:
        parentNode.insertBefore(element, refChild)
      else:
        self._insertFiltered(element, parentNode, refChild)

    # Parse remainder of end-tag (the ETAGO is eaten by _parseContent)
    #
    if not empty:
      if not self._next(element.tagName):
        self._e('Expected \'%s\' end-tag' % element.tagName)
      self._p_s(False)
      if not self._next('>'):
        self._e('Expected \'>\'')


  def _parseAttributeValue(self, parentNode, refChild):
    quote= self._p_q()
    while True:
      index= self._find(quote+'&<')
      if index>self._index:
        self._textQueue= self._textQueue+r(r(self._data[self._index:index],
          '\t', ' '), '\n', ' '
        )
        self._index= index
      if self._next('&'):
        if self._next('#'):
          self._parseCharacterReference(parentNode, refChild)
        else:
          self._parseEntityReference(parentNode, refChild, replaceWhite= True)
      elif self._next('<'):
        self._e('Attribute value may not contain \'<\'')
      else:
        break
    if not self._next(quote):
      self._e('Expected close-quote \'%s\'' % quote)
    self._flushText(parentNode, refChild)

  def _parseCharacterReference(self, parentNode, refChild):
    if self._next('x'):
      value= self._p_hex()
    else:
      value= self._p_dec()
    if not self._next(';'):
      self._e('Expected \';\' to end entity reference')
    if unicode is None and value>=0x100:
      self._flushText(parentNode, refChild)
      ent= parentNode._ownerDocument.createEntityReference(
        '#'+str(value), _strict= False
      )
      parentNode.insertBefore(ent, refChild)
    else:
      if unicode is None:
        char= chr(value)
      else:
        char= unichr(value)
      self._textQueue= self._textQueue+char

  _ENTITIES= { 'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'" }
  def _parseEntityReference(self, parentNode, refChild, replaceWhite= False):
    name= self._p_name()
    if not self._next(';'):
      self._e('Expected \';\' to end entity reference')
    if LSParser._ENTITIES.has_key(name):
      char= LSParser._ENTITIES[name]
      self._textQueue= self._textQueue+char
    else:
      ent= None
      if not self._domConfig.getParameter('entities'):
        doctype= parentNode._ownerDocument.doctype
        if doctype is not None:
          ent= doctype.entities.getNamedItem(name)
      if ent is None:
        self._flushText(parentNode, refChild)
        ent= parentNode._ownerDocument.createEntityReference(name)
        ent._setLocation(self._getLocation())
        self._insertFiltered(ent, parentNode, refChild, norm= True)
      else:
        for index in range(ent.childNodes.length):
          child= ent.childNodes.item(index)
          if child.nodeType==Node.TEXT_NODE:
            value= child.data
            if replaceWhite:
              value= r(r(child.data, '\t', ' '), '\n', ' ')
            self._textQueue= self._textQueue+value
          else:
            self._flushText(parentNode, refChild)
            parentNode.insertBefore(child.cloneNode(True), refChild)

  def _parseComment(self, parentNode, refChild):
    index= string.find(self._data, '-->', self._index)
    if index==-1:
      self._e('Unclosed comment, no following \'-->\'')
    if self._domConfig.getParameter('comments'):
      self._flushText(parentNode, refChild)
      comment= parentNode._ownerDocument.createComment(
        self._data[self._index:index]
      )
      comment._setLocation(self._getLocation())
      self._insertFiltered(comment, parentNode, refChild)
    else:
      self._textQueue= self._textQueue+self._data[self._index:index]
    self._index= index+3

  def _parseProcessingInstruction(self, parentNode, refChild):
    self._flushText(parentNode, refChild)
    target= self._p_name()
    index= self._index
    if self._p_s(False)!='':
      index= string.find(self._data, '?>', self._index)
      if index==-1:
        self._e('Unclosed PI, no following \'?>\'')
    elif not self._next('?>'):
      self._e('Expected whitespace or end of PI')
    pi= parentNode._ownerDocument.createProcessingInstruction(
      target, self._data[self._index:index]
    )
    pi._setLocation(self._getLocation())
    self._insertFiltered(pi, parentNode, refChild)
    self._index= index+2

  def _parseCDATASection(self, parentNode, refChild):
    index= string.find(self._data, ']]>', self._index)
    if index==-1:
      self._e('Unclosed CDATA section, no following \']]>\'')
    if self._domConfig.getParameter('cdata-sections'):
      self._flushText(parentNode, refChild)
      cdata= parentNode._ownerDocument.createCDATASection(
        self._data[self._index:index]
      )
      cdata._setLocation(self._getLocation())
      self._insertFiltered(cdata, parentNode, refChild)
    else:
      self._textQueue= self._textQueue+self._data[self._index:index]
    self._index= index+3

  def _parseDoctype(self, parentNode, refChild):
    self._p_s()
    qualifiedName= self._p_name()
    self._p_s()
    publicId= None
    systemId= None
    if self._next('SYSTEM'):
      self._p_s()
      systemId= self._p_lit()
      self._p_s(False)
    if self._next('PUBLIC'):
      self._p_s()
      publicId= self._p_lit()
      self._p_s(False)
      if self._index>=len(self._data) or self._data[self._index] not in '[>':
        systemId= self._p_lit()
        self._p_s(False)
    doctype= parentNode._ownerDocument.implementation.createDocumentType(
      qualifiedName, publicId, systemId
    )
    parentNode.insertBefore(doctype, refChild)
    if self._next('['):
      doctype.entities.readonly= False
      doctype.notations.readonly= False
      doctype.internalSubset= self._parseInternalSubset(doctype)
      for node in doctype.entities._list:
        node._recurse(True, readonly= True)
      doctype.entities.readonly= True
      for node in doctype.notations._list:
        node._recurse(True, readonly= True)
      doctype.notations.readonly= True
      if not self._next(']'):
        self._e('Expected \']\' to close internal subset')
      self._p_s(False)
    if not self._next('>'):
      self._e('Expected \'>\' to close doctype')

  def _parseInternalSubset(self, doctype):
    self._pes= {}
    self._processInternalSubset= True
    filter= self._filter
    self._filter= None
    try:
      start= self._index
      while self._index<len(self._data):
        self._p_s(False)
        if self._next(']', skip= False):
          break
        elif self._next('%'):
          self._parseParameterEntityReference(doctype)
        elif self._next('<'):
          if self._next('?'):
            index= string.find(self._data, '?>', self._index)
            if index==-1:
              self._e('Unclosed PI, no following \'?>\'')
            self._index= index+2
          elif self._next('!'):
            if self._next('--'):
              index= string.find(self._data, '-->', self._index)
              if index==-1:
                self._e('Unclosed comment, no following \'-->\'')
              self._index= index+3
            elif self._next('ENTITY'):
              self._parseEntityDeclaration(doctype)
            elif self._next('NOTATION'):
              self._parseNotation(doctype)
            elif self._next('ELEMENT'):
              self._parseElementDeclaration(doctype)
            elif self._next('ATTLIST'):
              self._parseAttributeListDeclaration(doctype)
            else:
              self._e('Expected markup declaration')
          else:
            self._e('Expected markup declaration')
        else:
          self._e('Expected markup declaration')
      if start==self._index:
        return None
      return self._data[start:self._index]
    finally:
      self._filter= filter

  def _parseParameterEntityReference(self, doctype):
    start= self._index-1
    name= self._p_name()
    if not self._next(';'):
      self._e('Expected \';\' to end PE reference')
    if self._processInternalSubset:
      if not self._pes.has_key(name):
        self._e('Unbound parameter entity \'%s\'' % name)
      if self._pes[name] is None:
        if not doctype._ownerDocument.standalone:
          self._processInternalSubset= False
      else:
        self._data=self._data[:start]+self._pes[name]+self._data[self._index:]
        self._index= start

  def _parseEntityDeclaration(self, doctype):
    pe= False
    peValue= None
    publicId= None
    systemId= None
    notationName= None
    entity= None
    self._p_s()
    if self._next('%'):
      pe= True
      self._p_s()
    name= self._p_name()
    self._p_s()
    if self._next('SYSTEM'):
      self._p_s()
      systemId= self._p_lit()
      self._p_s(False)
      if self._next('NDATA'):
        self._p_s()
        notationName= self._p_name()
    elif self._next('PUBLIC'):
      self._p_s()
      publicId= self._p_lit()
      self._p_s()
      systemId= self._p_lit()
      self._p_s(False)
      if self._next('NDATA'):
        self._p_s()
        notationName= self._p_name()
    else:
      if pe:
        peValue= self._p_lit()
      else:
        entity= doctype.createEntity(name, None, None, None)
        quote= self._p_q()
        index= string.find(self._data, quote, self._index)
        if index==-1:
          self._e('Unclosed entity value, no \'%s\'' % quote)
        tail= self._data[index:]
        self._data= self._data[:index]
        queue= self._textQueue
        self._textQueue= ''
        self._parseContent(entity, None)
        self._textQueue= queue
        self._data= self._data+tail
        self._index= self._index+1
    self._p_s(False)
    if not self._next('>'):
      self._e('Expected \'>\' to end entity declaration')
    if self._processInternalSubset:
      if pe:
        if not self._pes.has_key(name):
          self._pes[name]= peValue
      else:
        if entity is None:
          entity= doctype.createEntity(name, publicId, systemId, notationName)
          entity._available= False
        if doctype.entities.getNamedItem(name) is None:
          if entity._containsUnboundPrefix():
            self._domConfig._handleError(DOMErrorUnboundNamespaceInEntity(entity))
          doctype.entities.setNamedItem(entity)
  def _parseNotation(self, doctype):
    self._p_s()
    name= self._p_name()
    self._p_s()
    publicId= None
    systemId= None
    if self._next('SYSTEM'):
      self._p_s()
      systemId= self._p_lit()
    elif self._next('PUBLIC'):
      self._p_s()
      publicId= self._p_lit()
      self._p_s(False)
      if not self._next('>', skip= False):
        systemId= self._p_lit()
        self._p_s(False)
    else:
      self._e('Expected \'PUBLIC\' or \'SYSTEM\'')
    if not self._next('>'):
      self._e('Expected \'>\' to close notation declaration')
    if self._processInternalSubset:
      if doctype.notations.getNamedItem(name) is None:
        notation= doctype.createNotation(name, publicId, systemId)
        doctype.notations.setNamedItem(notation)
  def _parseElementDeclaration(self, doctype):
    self._p_s()
    name= self._p_name()
    self._p_s()
    if self._next('EMPTY'):
      contentType= ElementDeclaration.EMPTY_CONTENT
      elements= None
    elif self._next('ANY'):
      contentType= ElementDeclaration.ANY_CONTENT
      elements= None
    elif self._next('('):
      self._p_s(False)
      if self._next('#PCDATA'):
        contentType= ElementDeclaration.MIXED_CONTENT
        self._p_s(False)
        if self._next('|'):
          elements= self._p_cdecl(True)
          if not elements.isMultiple or not elements.isOptional:
            self._e('Mixed content group must end with \'*\'')
        elif self._next(')'):
          elements= ContentDeclaration()
        else:
          self._e('Expected \'|\' or end of list')
      else:
        contentType= ElementDeclaration.ELEMENT_CONTENT
        elements= self._p_cdecl(False)
    else:
      self._e('Expected content declaration')
    self._p_s(False)
    if not self._next('>'):
      self._e('Expected declaration-ending \'>\'')
    if self._processInternalSubset:
      if doctype._elements.getNamedItem(name) is None:
        element= doctype.createElementDeclaration(name, contentType, elements)
        doctype._elements.setNamedItem(element)
  def _parseAttributeListDeclaration(self, doctype):
    self._p_s()
    name= self._p_name()
    self._p_s()
    if self._processInternalSubset:
      attlist= doctype._attlists.getNamedItem(name)
      if attlist is None:
        attlist= doctype.createAttributeListDeclaration(name)
        doctype._attlists.setNamedItem(attlist)
    else:
      attlist= doctype.createAttributeListDeclaration(name)
    while not self._next('>'):
      name= self._p_name()
      self._p_s()
      typeValues= None

      for ix in range(1, len(AttributeDeclaration.ATTR_NAMES)-1):
        if self._next(AttributeDeclaration.ATTR_NAMES[ix]):
          attributeType= ix
          if attributeType==AttributeDeclaration.NOTATION_ATTR:
            self._p_s()
            typeValues= self._p_enum()
          break
      else:
        if self._next('(', skip= False):
          attributeType= AttributeDeclaration.ENUMERATION_ATTR
          typeValues= self._p_enum()
        else:
          self._e('Expected AttType')

      self._p_s()
      if self._next('#REQUIRED'):
        defaultType= AttributeDeclaration.REQUIRED_VALUE
      elif self._next('#IMPLIED'):
        defaultType= AttributeDeclaration.IMPLIED_VALUE
      elif self._next('#FIXED'):
        defaultType= AttributeDeclaration.FIXED_VALUE
        self._p_s()
      else:
        defaultType= AttributeDeclaration.DEFAULT_VALUE
      if attlist.declarations.getNamedItem(name) is None:
        attdef= doctype.createAttributeDeclaration(
          name, attributeType, typeValues, defaultType
        )
        attlist.declarations.setNamedItem(attdef)
      if defaultType in (
        AttributeDeclaration.FIXED_VALUE, AttributeDeclaration.DEFAULT_VALUE
      ):
        self._parseAttributeValue(attdef, None)
      if not self._next('>', skip= False):
        self._p_s()

  def _getLocation(self):
    return (
      string.count(self._data, '\n', 0, self._index) +1,
      self._index-(string.rfind(self._data, '\n', 0, self._index)+1) +1
    )

# Convenience parsing functions. The default parameters for these functions
# are slightly different than those of a standard LSParser, to emulate the
# minidom functions of the same name. Other DOMConfiguration parameters may be
# passed in an optional mapping.
#
def parse(fileorpath, parameters= {}):
  """ Get a Document object from a file.
  """
  parser= LSParser()
  parser.domConfig.setParameter('cdata-sections', True)
  parser.domConfig.setParameter('pxdom-resolve-resources', False)
  for (key, value) in parameters.items():
    parser.domConfig.setParameter(key, value)
  src= _implementation.createLSInput()
  if hasattr(fileorpath, 'read'):
    src.byteStream= fileorpath
  else:
    src.systemId= 'file:'+urllib.pathname2url(fileorpath)
  doc= parser.parse(src)
  return doc

def parseString(content, parameters= {}):
  """ Get a Document object from a string.
  """
  parser= LSParser()
  parser.domConfig.setParameter('cdata-sections', True)
  parser.domConfig.setParameter('pxdom-resolve-resources', False)
  for (key, value) in parameters.items():
    parser.domConfig.setParameter(key, value)
  src= _implementation.createLSInput()
  src.stringData= content
  return parser.parse(src)


class LSResourceResolver:
  """ Resource resolvers are not currently used by pxdom.
  """
  pass


# DOM 3 LS Save features
# ============================================================================

def _DOMImplementation__createLSOutput(self):
  return LSOutput()
def _DOMImplementation__createLSSerializer(self):
  return LSSerializer()

# Markup content as a property, a convenience interface that was in the June
# WD as ElementLS.markupContent. It is no longer in the standard, but is
# included in pxdom for its convenience, extended to appear on all node types
# (though it is not always writable).
#
def _Node___get_pxdomContent(self):
  return LSSerializer(self._ownerDocument.domConfig).writeToString(self)

def _Node___set_pxdomContent(self, value):
  input= LSInput()
  input.stringData= value
  parser= LSParser(self._ownerDocument.domConfig)
  parser.parseWithContext(input, self, LSParser.ACTION_REPLACE_CHILDREN)


class LSOutput(DOMObject):
  """ Abstraction for the output destination of an LSSerializer. As well as
      the standard-defined options, we use characterStream= True internally to
      mean 'return data as string'.
  """
  def __init__(self):
    DOMObject.__init__(self)
    self._characterStream= None
    self._byteStream= None
    self._systemId= None
    self._encoding= None

  def _get_characterStream(self): return self._characterStream
  def _get_byteStream(self): return self._byteStream
  def _get_systemId(self): return self._systemId
  def _get_encoding(self): return self._encoding

  def _set_characterStream(self, value): self._characterStream= value
  def _set_byteStream(self, value): self._byteStream= value
  def _set_systemId(self, value): self._systemId= value
  def _set_encoding(self, value): self._encoding= value


class OutputBuffer:
  def __init__(self, output, document):
    self._output= output
    self._buffer= StringIO.StringIO()
    self._separator= None
    if (
      output.characterStream is None and output.byteStream is None
      and output.systemId is None
    ):
        raise DOMErrorNoOutput(None)

    # Work out which charsets to use (a) for detecting unencodable characters
    # and escaping them (and also putting in the XML declaration if there is
    # one) and (b) encoding the final output.
    #
    self.encoding= output.encoding
    self.outputEncoding= None
    if self.encoding is None and output.characterStream is None:
      self.encoding= document.inputEncoding or document.xmlEncoding
    if self.encoding is None:
      self.encoding= nativeEncoding
    elif output.characterStream is None:
      self.outputEncoding= self.encoding

    # Ignore endianness in the declared version of the encoding, and check it
    # actually exists.
    #
    if (
      string.lower(self.encoding)[:6] in ('utf-16', 'utf-32') and
      self.encoding[6:-2] in ('', '-', '_') and
      string.lower(self.encoding)[-2:] in ('le', 'be')
    ):
      self.encoding= self.encoding[:6]
    if unicode is not None:
      try:
        unicode('').encode(self.encoding)
      except LookupError:
        raise DOMErrorUnsupportedEncoding(None)

  def flush(self):
    """ Finish output, sending buffer contents to the nominated destination
        (optionally encoding it). In the special case where characterStream
        was 'True' return the buffer as a string, else return a success flag,
        which is always True since we throw an exception when there is an
        fatal error and don't attempt to carry on.
    """
    data= self._buffer.getvalue()
    self._buffer= None
    try:

      if self._output.characterStream is True:
        return data
      elif self._output.characterStream is not None:
        self._output.characterStream.write(data)
        return True

      if self.outputEncoding is not None and unicode is not None:
        data= unicode(data).encode(self.outputEncoding)

      if self._output.byteStream is True:
        return data
      if self._output.byteStream is not None:
        self._output.byteStream.write(data)
        return True

      if self._output.systemId is not None:
        urlparts= urlparse.urlparse(self._output.systemId, 'file')
        scheme= string.lower(urlparts[0])
        if scheme=='file':
          stream= open(urllib.url2pathname(urlparts[2]), 'wb')
          stream.write(data)
          stream.close()
          return True
        elif scheme in ('http', 'https'):
          if scheme=='https':
            conn= httplib.HTTPSConnection(urlparts[1])
          else:
            conn= httplib.HTTPConnection(urlparts[1])
          conn.request('PUT', urlparts[2], data, {
            'Content-Type': 'text/xml', 'Content-Length': str(len(data))
          })
          status, message, headers= conn.getreply()
          conn.close()
          if not (status>=200 and status<300):
            raise DOMErrorIOError(IOError(
              'HTTP response %d %s' % (status, message)
            ))
          return True
        else:
          raise DOMErrorIOError(
            ValueError('Can\'t write to URI type %s' % urlparts[0])
          )
    except IOError, e:
      raise DOMErrorIOError(e)

  def setSeparator(self, separator):
    """ A separator can be set (or cleared by passing None) on the output,
        causing that string to be written the next time write() is called with
        a non-empty string. This is useful for eg. attributes, where the
        serializer won't know if a whitespace character is needed until the
        attribute markup arrives.
    """
    self._separator= separator

  def write(self, data, escaper= None):
    """ Accumulate string parts, calling an escaper function back for any
        characters that cannot be output in the desired encoding. Note that
        even though we do an encode step here, it is only to detect tricky
        characters - it is the plain, unencoded versions that are sent to the
        output buffer, they will be encoded in the final output encoding in
        the flush() step.
    """
    if self._separator is not None:
      self._buffer.write(self._separator)
      self._separator= None

    # Try to unicode-encode if we will need to and the result isn't going to
    # be a UTF encoding - by definition, all possible characters are encodable
    # in a UTF form.
    #
    if unicode is None or string.lower(self.encoding[:3])=='utf':
      self._buffer.write(data)
    else:
      chars= unicode(data)
      try:
        chars.encode(self.encoding, 'strict')

      # One or more characters cannot be encoded. Try each of them one by one
      # and pass any that can't to the escaper, which will either return a
      # plain string escaped version (eg. '&#1234;'), or raise an exception.
      #
      except UnicodeError:
        for char in chars:
          try:
            char.encode(self.encoding, 'strict')
            self._buffer.write(char)
          except UnicodeError:
            if escaper is not None:
              self._buffer.write(escaper.escape(char))
      else:
        self._buffer.write(data)


# OuputBuffer escapers
#
class _Complainer:
  """ Holds an escaper method for OutputBuffer that just raises a given kind
      of DOMErrorException when called back.
  """
  def __init__(self, config, node, isName= False):
    if isName:
      self._exn= DOMErrorInvalidCharSerialized
    else:
      self._exn= DOMErrorInvalidNameSerialized
    self._node= node
    self._domConfig= config
  def escape(self, char):
    self._domConfig._handleError(self._exn(self._node))

class _Charreffer:
  """ Holds an escaper method that outputs a character reference, optionally
      in hex for canonical-form.
  """
  def __init__(self, hexref= False):
    self._hexref= hexref
  def escape(self, char):
    if self._hexref:
      return '&#x%s;' % hex(ord(char))
    else:
      return '&#%d;' % ord(char)

class _CdataSplitter:
  """ Holds an escaper method that outputs a CDATA-end-section then a charref,
      then re-opens CDATA, as long as the DOMConfiguration allows it. Config
      is only called back once per node, after that we null the reference. No
      hex option, as canonical-form allows no CDATASections.
  """
  def __init__(self, config, node):
    self._domConfig= config
    self._node= node
  def escape(self, char):
    config= self._domConfig
    if config is not None:
      if config.getParameter('split-cdata-sections'):
        config._handleError(DOMErrorCdataSectionSplitted(self._node))
      else:
        config._handleError(DOMErrorInvalidCharSerialized(self._node))
      self._domConfig= None
    return ']]>&#%d;<![CDATA[' % ord(char)


class LSSerializer(DOMObject):
  def __init__(self, config= None):
    DOMObject.__init__(self)
    if config is None:
      config= DOMConfiguration()
      if CNORM:
        config.setParameter('normalize-characters', True)
    self._domConfig= config
    self._newLine= os.linesep
    self._filter= None

  def _get_domConfig(self): return self._domConfig
  def _get_filter(self): return self._filter
  def _get_newLine(self): return self._newLine

  def _set_filter(self, value): self._filter= value
  def _set_newLine(self, value):
    if value is None:
      self._newLine= os.linesep
    else:
      self._newLine= value

  def write(self, node, destination):
    # Namespace fixup cannot (currently) be done on the fly during the
    # serialisation process. So if this is needed, normalise a clone and
    # output that instead of writing the original directly. 
    #
    try:
      if self._domConfig.getParameter('namespaces'):
        node= node.cloneNode(True)
        node._normalize(ns= True)

      try:
        buffer= OutputBuffer(destination, node._ownerDocument)
      except DOMErrorException, e:
        self._domConfig._handleError(e)
      node._writeTo(buffer, self._domConfig, self._filter, self._newLine)

      return buffer.flush()
    except DOMErrorException, e:
      raise SerializeErr(e)

  def writeToString(self, node):
    destination= LSOutput()
    destination.characterStream= True
    return self.write(node, destination)

  def writeToURI(self, node, uri):
    destination= LSOutput()
    destination.systemId= uri
    return self.write(node, destination)


def _Node___writeTo(self, destination, config, filter, newLine):
  """ Markup production, for various node types. The default node behaviour is
      just to recurse to all children.
  """
  for child in self._childNodes:
    child._writeTo(destination, config, filter, newLine)


def _Document___writeTo(self, destination, config, filter, newLine):
  # Output XML prolog
  #
  if config.getParameter('xml-declaration'):
    destination.write('<?xml version="')
    destination.write(self._xmlVersion or '1.0', _Complainer(config, self))
    if destination.encoding is not None:
      destination.write('" encoding="')
      destination.write(destination.encoding)
    if self._xmlStandalone:
      destination.write('" standalone="yes')
    destination.write('"?>')
    if config.getParameter('canonical-form'):
      destination.setSeparator(newLine)
  elif (self._xmlVersion not in ('1.0', None, '') or self._xmlStandalone):
    config._handleError(DOMErrorXmlDeclarationNeeded(self))

  # If in canonical form, have to put exactly one \n between each root-level
  # node rather than writing the same amount of whitespace as was in the
  # original document. Also ignore doctype in this case.
  #
  if not config.getParameter('canonical-form'):
    Node._writeTo(self, destination, config, filter, newLine)
  else:
    for child in self._childNodes:
      if child.nodeType not in (Node.TEXT_NODE, Node.DOCUMENT_TYPE_NODE):
        child._writeTo(destination, config, filter, newLine)
        destination.setSeparator(newLine)


def _Element___writeTo(self, destination, config, filter, newLine):
  accepted= _acceptNode(filter, self)
  if accepted==NodeFilter.FILTER_SKIP:
    NamedNodeNS._writeTo(self, destination, config, filter, newLine)
  if accepted!=NodeFilter.FILTER_ACCEPT:
    return

  escaper= _Complainer(config, self, True)
  destination.write('<')
  destination.write(config._cnorm(self.tagName, self), escaper)
  destination.setSeparator(' ')

  attrs= self._attributes
  if config.getParameter('canonical-form'):
    attrs= attrs._list[:]
    attrs.sort()
  for attr in attrs:
    attr._writeTo(destination, config, filter, newLine)
    destination.setSeparator(' ')
  destination.setSeparator(None)

  empty= self._childNodes.length==0
  if empty and not config.getParameter('canonical-form'):
    destination.write('/>')
  else:
    destination.write('>')

    if not empty:
      if not config.getParameter('format-pretty-print') or (
        self._childNodes.length==1 and
        self._childNodes[0].nodeType==Node.TEXT_NODE and
        '\n' not in self._childNodes[0].data
      ):
        NamedNodeNS._writeTo(self, destination, config, filter, newLine)
      else:
        destination.write(newLine+'  ')
        NamedNodeNS._writeTo(self, destination, config, filter, newLine+'  ')
        destination.write(newLine)

    destination.write('</')
    destination.write(self.tagName, escaper)
    destination.write('>')


def _Attr___writeTo(self, destination, config, filter, newLine):
  # Apply LSSerializerFiltering to non-namespace-declaring attributes only
  #
  isNsDecl= self.namespaceURI==NSNS and config.getParameter('namespaces')
  if (isNsDecl and not config.getParameter('namespace-declarations')):
    return
  if not isNsDecl and _acceptNode(filter, self)!=NodeFilter.FILTER_ACCEPT:
    return

  # Possibly discard default and redundant attributes depending on config
  #
  if not self._specified and config.getParameter('discard-default-content'):
    return
  if self.namespaceURI==NSNS and config.getParameter('canonical-form'):
    prefix= [self.localName, None][self.prefix is None]
    value= None
    if self._containerNode is not None:
      if self._containerNode.parentNode is not None:
        value= self._containerNode.parentNode._lookupNamespaceURI(prefix)
    if self.value==(value or ''):
      return

  # In canonical form mode, output actual attribute value (suitably encoded)
  #
  destination.write(config._cnorm(self.name, self),
    _Complainer(config, self, True)
  )
  destination.write('="')
  if config.getParameter('canonical-form'):
    destination.write( r(r(r(r(r(r(self.value, '&', '&amp;'),
      '<','&lt;'),'"','&quot;'),'\x0D','&#xD;'),'\n','&#xA'),'\t','&#x9;'),
      _Charreffer(True)
    )

  # Otherwise, iterate into children, but replacing " marks
  #
  else:
    for child in self._childNodes:
      child._writeTo(destination, config, filter, '&#10;', attr= True)
  destination.write('"')


def _Comment___writeTo(self, destination, config, filter, newLine):
  if (not config.getParameter('comments') or
    _acceptNode(filter, self)!=NodeFilter.FILTER_ACCEPT
  ):
    return
  if self.data[-1:]=='-' or string.find(self.data, '--')!=-1:
    config._handleError(DOMErrorInvalidCharSerialized(self))
  destination.write('<!--')
  pretty= config.getParameter('format-pretty-print')
  if pretty and '\n' in string.strip(self.data):
    for line in string.split(self.data, '\n'):
      line= string.strip(line)
      if line!='':
        destination.write(newLine+'  ')
        destination.write(line, _Complainer(config, self))
    destination.write(newLine)
  else:
    destination.write(r(self.data, '\n', newLine), _Complainer(config, self))
  destination.write('-->')

def _Text___writeTo(self, destination, config, filter, newLine, attr= False):
  if (
    not config.getParameter('element-content-whitespace')
    and self.isElementContentWhitespace(config)
  ) or _acceptNode(filter, self)!=NodeFilter.FILTER_ACCEPT:
    return

  m= r(r(config._cnorm(self.data, self), '&', '&amp;'), '<', '&lt;')
  if config.getParameter('canonical-form'):
    destination.write(r(r(r(r(m,
      '>', '&gt;'), '\r', '&#xD;'), '\t', '&#x9'), '\n', newLine),
      _Charreffer(True)
    )
  else:
    if attr:
      m= r(m, '"', '&quot;')
    m= r(r(r(m, ']]>', ']]&gt;'), '\r', '&#13;'), '\t', '&#9;')
    if config.getParameter('format-pretty-print'):
      m= string.join(map(string.strip, string.split(m, '\n')), newLine)
    destination.write(m, _Charreffer())

def _CDATASection___writeTo(self, destination, config, filter, newLine):
  if not config.getParameter('cdata-sections'):
    return Text._writeTo(self, destination, config, filter, newLine)
  if (
    not config.getParameter('element-content-whitespace')
    and self.isElementContentWhitespace(config)
  ) or _acceptNode(filter, self)!=NodeFilter.FILTER_ACCEPT:
    return

  m= config._cnorm(self.data, self)
  escaper= _CdataSplitter(config, self)
  destination.write('<![CDATA[')
  if string.find(m, ']]>')!=-1 or string.find(m, '\r')!=-1:
    escaper.escape(' ')
    destination.write(r(r(r(m,
      ']]>',']]>]]&gt;<![CDATA['), '\r',']]>&#13;<![CDATA['), '\n', newLine),
      escaper
    )
  else:
    destination.write(r(m, '\n', newLine), escaper)
  destination.write(']]>')

def _ProcessingInstruction___writeTo(self,destination,config,filter,newLine):
  if _acceptNode(filter, self)!=NodeFilter.FILTER_ACCEPT:
    return
  destination.write('<?')
  destination.write(self._nodeName, _Complainer(config, self, True))
  if self._data!='':
    destination.write(' ')
    if string.find(self._data, '?>')!=-1 or string.find(self._data, '\r')!=-1:
      config._handleError(DOMErrorInvalidCharSerialized(self))
    destination.write(r(config._cnorm(self._data, self), '\n', newLine),
      _Complainer(config, self)
    )
  destination.write('?>')

def _EntityReference___writeTo(self,
  destination, config, filter, newLine, attr= False
):
  if not config.getParameter('entities'):
    accepted= NodeFilter.FILTER_SKIP
  else:
    accepted= _acceptNode(filter, self)

  if accepted==NodeFilter.FILTER_ACCEPT:
    destination.write('&')
    destination.write(config._cnorm(self._nodeName, self),
      _Complainer(config, self, True)
    )
    destination.write(';')
  elif accepted==NodeFilter.FILTER_SKIP:
    if attr:
      for child in self._childNodes:
        if child.nodeType not in (Node.ENTITY_REFERENCE_NODE, Node.TEXT_NODE):
          config._handleError(DOMErrorInvalidCharSerialized(self))
        child._writeTo(destination, config, filter, newLine, True)
    else:
      NamedNode._writeTo(self, destination, config, filter, newLine)

def _DocumentType___writeTo(self, destination, config, filter, newLine):
  destination.write('<!DOCTYPE ')
  destination.write(
    config._cnorm(self._nodeName, self),
    _Complainer(config, self, True)
  )
  escaper= _Complainer(config, self)
  if self._publicId is not None:
    destination.write(' PUBLIC "')
    destination.write(config._cnorm(self._publicId, self), escaper)
    destination.write('"')
    if self._systemId is not None:
      destination.write(' "')
      destination.write(config._cnorm(self._systemId, self), escaper)
      destination.write('"')
  elif self._systemId is not None:
    destination.write(' SYSTEM "')
    destination.write(config._cnorm(self._systemId, self), escaper)
    destination.write('"')
  if self._internalSubset is not None:
    destination.write(' [')
    destination.write(config._cnorm(self._internalSubset, self), escaper)
    destination.write(']')
  destination.write('>')


# Exceptions
# ============================================================================

class DOMException(Exception):
  [INDEX_SIZE_ERR,DOMSTRING_SIZE_ERR,HIERARCHY_REQUEST_ERR,WRONG_DOCUMENT_ERR,
  INVALID_CHARACTER_ERR,NO_DATA_ALLOWED_ERR,NO_MODIFICATION_ALLOWED_ERR,
  NOT_FOUND_ERR,NOT_SUPPORTED_ERR,INUSE_ATTRIBUTE_ERR,INVALID_STATE_ERR,
  SYNTAX_ERR,INVALID_MODIFICATION_ERR,NAMESPACE_ERR,INVALID_ACCESS_ERR,
  VALIDATION_ERR, TYPE_MISMATCH_ERR
  ]= range(1, 18)
  def _get_code(self):
    return self.code

class IndexSizeErr(DOMException):
  def __init__(self, data, index):
    DOMException.__init__(self)
    self._data= data
    self._index= index
  def __str__(self):
    return 'index %s into data of length %s' % (self._index, len(self._data))
  code= DOMException.INDEX_SIZE_ERR

class HierarchyRequestErr(DOMException):
  def __init__(self, child, parent):
    DOMException.__init__(self)
    self._child= child
    self._parent= parent
  def __str__(self):
    if self._child.nodeType not in self._parent._childTypes:
      return 'putting %s inside %s' % (
        self._child.__class__.__name__, self._parent.__class__.__name__
      )
    elif self._parent.nodeType==Node.DOCUMENT_NODE:
      return 'putting extra %s in Document' % self._child.__class__.__name__
    else:
      return 'putting %s inside itself' % self._parent.__class__.__name__
  code= DOMException.HIERARCHY_REQUEST_ERR

class WrongDocumentErr(DOMException):
  def __init__(self, child, document):
    DOMException.__init__(self)
    self._child= child
    self._document= document
  def __str__(self):
    return 'putting %s into foreign Document' % self._child.__class__.__name__
  code= DOMException.WRONG_DOCUMENT_ERR

class InvalidCharacterErr(DOMException):
  def __init__(self, name, char):
    DOMException.__init__(self)
    self._name= name
    self._char= char
  def __str__(self):
    return '\'%s\' in \'%s\'' % (self._char, self._name)
  code= DOMException.INVALID_CHARACTER_ERR

class NoModificationAllowedErr(DOMException):
  def __init__(self, object, key):
    DOMException.__init__(self)
    self._object= object
    self._key= key
  def __str__(self):
    return '%s.%s read-only' % (self._object.__class__.__name__, self._key)
  code= DOMException.NO_MODIFICATION_ALLOWED_ERR

class NamespaceErr(DOMException):
  def __init__(self, qualifiedName, namespaceURI):
    DOMException.__init__(self)
    self._qualifiedName= qualifiedName
    self._namespaceURI= namespaceURI
  def __str__(self):
    if _splitName(self._qualifiedName)[1] is None:
      return '\'%s\' is not a qualifiedName' % self._qualifiedName
    return '\'%s\' can\'t be in namespace %s' % (
      self._qualifiedName, str(self._namespaceURI)
    )
  code= DOMException.NAMESPACE_ERR

class NotFoundErr(DOMException):
  def __init__(self, object, namespaceURI, localName):
    DOMException.__init__(self)
    self._object= object
    self._namespaceURI= namespaceURI
    self._localName= localName
  def __str__(self):
    if self._namespaceURI not in (None, NONS):
      return '%s in %s' % (self._localName, self._object.__class__.__name__)
    else:
      return '%s (ns: %s) in %s' % (
        self._localName, self._namespaceURI, self._object.__class__.__name__
      )
  code= DOMException.NOT_FOUND_ERR

class NotSupportedErr(DOMException):
  def __init__(self, object, name):
    DOMException.__init__(self)
    self._object= object
    self._name= name
  def __str__(self):
    return '%s.%s' % (self._object.__class__.__name__, self._name)
  code= DOMException.NOT_SUPPORTED_ERR

class InuseAttributeErr(DOMException):
  def __init__(self, attr):
    DOMException.__init__(self)
    self._attr= attr
  def __str__(self):
    return 'attr %s in use' % self._attr.name
  code= DOMException.INUSE_ATTRIBUTE_ERR


class DOMError(DOMObject):
  [SEVERITY_WARNING,SEVERITY_ERROR,SEVERITY_FATAL_ERROR
  ]= range(1, 4)
  def __init__(self, severity, message, type, node):
    DOMObject.__init__(self)
    self._severity= severity
    self._message= message
    self._type= type
    self._relatedData= node
  def _get_severity(self):
    return self._severity
  def _get_message(self):
    return self._message
  def _get_type(self):
    return self._type
  def _get_relatedException(self):
    return None
  def _get_relatedData(self):
    return self._relatedData
  def _get_location(self):
    if self._relatedData is None:
      return DOMLocator()
    return self._relatedData.pxdomLocation

class DOMErrorException(Exception):
  def __init__(self, node):
    Exception.__init__(self)
    self.node= node
  def __str__(self):
    return '%s \'%s\'' % (
      ['', 'Warning', 'Error', 'Fatal error'][self.severity], self.type
    )
  def __repr__(self):
    return str(self)

class DOMErrorWarning(DOMErrorException):
  severity= DOMError.SEVERITY_WARNING
  def allowContinue(self, cont):
    return [cont, True][cont is None]
class DOMErrorError(DOMErrorException):
  severity= DOMError.SEVERITY_ERROR
  def allowContinue(self, cont):
    return [cont, False][cont is None]
class DOMErrorFatal(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  def allowContinue(self, cont):
    return False

class DOMErrorNoOutput(DOMErrorFatal):
  type= 'no-output-specified'
class DOMErrorUnsupportedType(DOMErrorFatal):
  type= 'unsupported-media-type'
class DOMErrorUnsupportedEncoding(DOMErrorFatal):
  type= 'unsupported-encoding'
class DOMErrorUnboundNamespaceInEntity(DOMErrorWarning):
  type= 'unbound-namespace-in-entity'
class DOMErrorXmlDeclarationNeeded(DOMErrorWarning):
  type= 'xml-declaration-needed'
class DOMErrorDoctypeNotAllowed(DOMErrorFatal):
  type= 'doctype-not-allowed'
class DOMErrorCdataSectionSplitted(DOMErrorWarning):
  type= 'cdata-section-splitted'
class DOMErrorInvalidChar(DOMErrorError):
  type= 'wf-invalid-character'
class DOMErrorInvalidCharSerialized(DOMErrorFatal):
  type= 'wf-invalid-character'
class DOMErrorInvalidNameSerialized(DOMErrorFatal):
  type= 'wf-invalid-character-in-node-name'
class DOMErrorNoInput(DOMErrorFatal):
  type= 'no-input-specified'
class DOMErrorCheckCharacterNormalizationFailure(DOMError):
  type= 'check-character-normalization-failure'

class DOMErrorIOError(DOMErrorFatal):
  type= 'pxdom-uri-unreadable'
  def __init__(self, e):
    DOMErrorFatal.__init__(self, None)
    self.desc= str(e)
  def __str__(self):
    return '%s DOMError due to %s' % (self.type, self.desc)

class ParseError(DOMErrorFatal):
  type= 'pxdom-parse-error'
  def __init__(self, parser, message):
    DOMErrorFatal.__init__(self, None) 
    self._message= message
    self._parser= parser
    line, column= parser._getLocation()
    self.location= DOMLocator(None, line, column, parser._buffer.uri)

  def __str__(self):
    index= self._parser._index
    if index<30:
      pre= self._parser._data[:index]
    else:
      pre= self._parser._data[index-30:index]
    post= self._parser._data[index:index+30]
    pre= string.split(pre, '\n')[-1]
    post= string.split(post, '\n')[0]
    pre= string.join(map(lambda c: (c, '?')[ord(c)>=128], pre), '')
    post= string.join(map(lambda c: (c, '?')[ord(c)>=128], post), '')
    line, column= self.location.lineNumber, self.location.columnNumber
    return 'XML parsing error: %s, around line %s, char %s:\n%s%s\n%s^' % (
      self._message, line, column, pre, post, ' '*len(pre)
    )

# LSExceptions wrap a DOMErrorException when returned from parse and serialise
# methods.
#
class LSException(Exception):
  [PARSE_ERR, SERIALIZE_ERR
  ]= range(81, 83)
  def __init__(self, e):
    self.e= e
  def __str__(self):
    return str(self.e)
class ParseErr(LSException):
  code= LSException.PARSE_ERR
class SerializeErr(LSException):
  code= LSException.SERIALIZE_ERR


# END. Fix up classes.
#
_insertMethods()
