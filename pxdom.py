""" pxdom - standalone pure-Python DOM implementation and non-validating
    parser conforming to DOM Level 3 Core/XML and Load/Save (based on the
    June 2003 Working Drafts) with Python and OMG (_get/_set) bindings.
"""

import string, urlparse, urllib

__version__= 0,8
__author__ = 'Andrew Clover <and@doxdesk.com>'
__date__   = '18 October 2003'
__all__    = [
  'getDOMImplementation', 'getDOMImplementations', 'parse', 'parseString'
]


# Unicode, XML 1.1 extra line separators
#
try:
  EBCLS= unichr(0x85)
  UNILS= unichr(0x2028)
except NameError:
  globals()['unicode']= None
  EBCLS= chr(0x85)
  UNILS= ''

# Backwards-compatibility boolean type
#
try:
  True
except NameError:
  globals()['True']= None is None
  globals()['False']= None is not None

# Special namespace URIs
#
XMNS= 'http://www.w3.org/XML/1998/namespace'
NSNS= 'http://www.w3.org/2000/xmlns/'


class _NONS:
  """ Singleton class used internally as a value for namespaceURI signifying
      that a non-namespace version of a node or method is in use; the
      accompanying localName is then the entire name. This is different to
      None, which is a null namespace value.
  """
  pass
NONS= _NONS()


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
_NOTNAME= ' \t\n!"#$%&\'()*+,/;<=>?@[\\]^`{|}~'


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
    if self._readonly and key not in ('readonly', 'nodeValue'):
      raise NoModificationAllowedErr(self, key)
    try:
      setter= getattr(self, '_set_'+key)
    except AttributeError:
      if hasattr(self, '_get_'+key):
        raise NoModificationAllowedErr(self, key)
      raise AttributeError, key
    setter(value)


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
    'ls-elementls':       ['3.0'],
    'ls-documentls':      ['3.0']
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
  def createDOMParser(self, mode= MODE_SYNCHRONOUS, schemaType= None):
    if mode==DOMImplementation.MODE_ASYNCHRONOUS:
      raise NotSupportedErr(self, 'createDOMParser.mode')
    if schemaType is not None and schemaType!='http://www.w3.org/TR/REC-xml':
      raise NotSupportedErr(self, 'createDOMParser.schemaType')
    return DOMParser()
  def createDOMSerializer(self):
    return DOMSerializer()
  def createDOMInput(self):
    return DOMInput()
  def createDOMOutput(self):
    return DOMOutput()
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


# DOM structure objects
#
class DOMList(DOMObject):
  """ A list structure that can be accessed either using the DOM IDL methods
      or Python list accessor constructs.
  """
  def __init__(self):
    DOMObject.__init__(self)
    self._list= []

  # DOM-style methods
  #
  def _get_length(self):
    return len(self._list)

  def item(self, index):
    if index<0 or index>=len(self._list):
      return None
    return self._list[index]

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


class DOMImplementationList(DOMList):
  """ List of DOMImplementation classes; no special features over DOMList.
  """
  pass


class NodeList(DOMList):
  """ Abstract list of nodes dependent on an owner node.
  """
  def __init__(self, ownerNode= None):
    DOMList.__init__(self)
    self._ownerNode= ownerNode


class ChildNodeList(NodeList):
  """ A NodeList of children of the owner node. Alterations to the list result
      in calls to the parent's DOM methods (this seems to be required by the
      Python DOM bindings, although not in used in practice).
  """
  def __setitem__(self, index, value):
    self._ownerNode.replaceChild(value, self._list[index])

  def __delitem__(self, index):
    self._ownerNode.removeChild(self._list[index])


class NodeListByTagName(NodeList):
  """ A NodeList returned by an Element.getElementsByTagName[NS] method. This
      is still live - the internal _list acts only as a cache, and is
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
  """ Dictionary-style object used for mappings. Abstract class - subclass must
      set _childTypes to specify what sort of nodes it wants.
  """
  _childTypes= []

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
    if self._readonly:
      raise NoModificationAllowedErr(self, 'namedItem')
    if newItem is not None:
      if newItem.nodeType not in self._childTypes:
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

  def _isEqualMap(self, other):
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


# Various lightweight DOM value types
#
class TypeInfo(DOMObject):
  """ Value type belonging to an Element or Attribute supplying information
      about its schema type. Since only DTDs are supported, this returns nulls
      except for Attribute typeNames, which might be grabbable from the
      internal subset's attlists.
  """
  def __init__(self, ownerNode):
    DOMObject.__init__(self, False)
    self._ownerNode= ownerNode
  def _get_typeName(self):
    if (
      self._ownerNode.nodeType==Node.ATTRIBUTE_NODE and
      self._ownerNode.ownerElement is not None and
      self._ownerNode.ownerDocument is not None and
      self._ownerNode.ownerDocument.doctype is not None
    ):
      tagName= self._ownerNode.ownerElement.tagName
      attlist= self._ownerNode.ownerDocument.doctype.attlists.getNamedItem(
        tagName
      )
      if attlist is not None:
        attdecl= attlist.declarations.getNamedItem(self._ownerNode.name)
        if attdecl is not None:
          return AttributeDeclaration.ATTR_NAMES[attdecl.attributeType]
    return None
  def _get_typeNamespace(self):
    return None


class DOMLocator(DOMObject):
  """ Value type used to return information on the source document and position
      of a node. Used in the standard DOM to locate DOMErrors; pxdom also
      allows any Node to be located this way.
  """
  def __init__(self, node= None, lineNumber= -1, columnNumber= -1):
    self._relatedNode= node
    self._lineNumber= lineNumber
    self._columnNumber= columnNumber
    if node is None:
      self._uri= ''
    else:
      self._uri= node._ownerDocument.documentURI
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


# DOM base classes
#
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
  DOCUMENT_POSITION_IS_CONTAINED,DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC
  ]= map(lambda n: 2**n, range(6))

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

  # Recursive object operations: clone, adopt, import (=clone+adopt), readonly
  #
  def _recurse(self, deep, clone= False, ownerDocument= None, readonly= None):
    if clone:
      node= self.__class__()
      self._cloneTo(node)
    else:
      node= self

    self._recurseTo(node, clone, ownerDocument, readonly)
    if deep:
      node._childNodes.readonly= False
      for child in self._childNodes:
        r= child._recurse(deep, clone, ownerDocument, readonly)
        if clone:
          node._childNodes._append(r)
          r._containerNode= node
      node._childNodes.readonly= True

    if ownerDocument is not None:
      node._ownerDocument= ownerDocument
    if ownerDocument is not None or clone:
      node._cloneDone()

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

  def _recurseTo(self, node, clone, ownerDocument, readonly):
    if self._attributes is not None:
      toRemove= []
      for attr in self._attributes:
        if not attr.specified:
          if (ownerDocument is not None and not clone):
            toRemove.append(attr)
          if (ownerDocument is not None and clone):
            continue
        r= attr._recurse(True, clone, ownerDocument, readonly)
        if clone:
          node._attributes._append(r)
          r._containerNode= node
      for attr in toRemove:
        self.removeAttributeNode(attr)

  def _cloneTo(self, node):
    node._ownerDocument= self._ownerDocument
    node._namespaceURI= self._namespaceURI
    node._localName= self._localName
    node._prefix= self._prefix
    node._row= self._row
    node._col= self._col

  def _cloneDone(self):
    pass

  def cloneNode(self, deep):
    return self._recurse(deep, clone= True)

  def _getDescendants(self, descendants):
    for child in self._childNodes:
      descendants.append(child)
      child._getDescendants(descendants)

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
      newNodes= newChild._getInsertable()
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

  # DOM 3 Node comparisons
  #
  def isSameNode(self, other):
    return self is other

  def isEqualNode(self, other):
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

  def compareDocumentPosition(self, other):
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
        Node.DOCUMENT_POSITION_IS_CONTAINED + Node.DOCUMENT_POSITION_FOLLOWING
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
      if other_determining.nodeType<self_determining.nodeType:
        return Node.DOCUMENT_POSITION_FOLLOWING
      return Node.DOCUMENT_POSITION_PRECEDING
    if self_determining._nodeType==Node.ATTRIBUTE_NODE:
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

  # DOM 3 UserData
  #
  def getUserData(self, key):
    return self._userData.get(key, (None, None))[0]

  def setUserData(self, key, data, handler):
    oldData= self.getUserData(key)
    self._userData[key]= (data, handler)
    return oldData

  def _callUserDataHandlers(self, operation, src, dst):
    for (key, (data, handler)) in self._userData.items():
      if handler is not None:
        handler.handle(operation, key, data, src, dst)

  # DOM 3 Namespace inspection
  #
  def isDefaultNamespace(self, namespaceURI):
    return None

  def lookupNamespaceURI(self, prefix):
    return None

  def lookupPrefix(self, namespaceURI):
    return None

  def _lookupNamespaceURI(self, localName):
    if self.attributes is not None:
      if localName is None:
        xmlns= self.attributes.getNamedItemNS(NSNS, 'xmlns')
      else:
        xmlns= self.attributes.getNamedItemNS(NSNS, localName)
      if xmlns is not None:
        value= xmlns.value
        if value!='':
          return value
        return None
    if self._containerNode is not None:
      return self._containerNode._lookupNamespaceURI(localName)
    return None

  def _lookupPrefix(self, namespaceURI, exclude):
    if self._attributes is not None:
      for index in range(self._attributes.length):
        attr= self._attributes.item(index)
        if attr.prefix=='xmlns' and attr.localName not in exclude:
          if attr.value==namespaceURI:
            return attr.localName
          else:
            exclude.append(attr.localName)
    if self._containerNode is not None:
      return self._containerNode._lookupPrefix(namespaceURI, exclude)
    return None

  # DOM 3 textual content access
  #
  def _get_textContent(self):
    value= ''
    for index in range(self._childNodes.length):
      child= self._childNodes.item(index)
      if child.nodeType not in [
        Node.COMMENT_NODE, Node.PROCESSING_INSTRUCTION_NODE
      ]:
        value= value+child.textContent
    return value

  def _set_textContent(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'textContent')
    while self._childNodes.length>0:
      self.removeChild(self.firstChild)
    text= Text(self._ownerDocument)
    text.data= value
    self.appendChild(text)

  # Misc
  #
  def isSupported(self, feature, version):
    return _implementation.hasFeature(feature, version)

  def getFeature(self, feature, version):
    if implementation.hasFeature(feature, version):
      return self
    return None

  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'normalize')

    # Normalise attributes
    #
    if self._attributes is not None:
      for index in range(self._attributes.length):
        self._attributes.item(index).normalize(
          text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
        )

    # Replace entities with their contents before doing other processing in a
    # separate pass
    #
    if unent:
      for child in self._childNodes._list[:]:
        if child.nodeType==Node.ENTITY_REFERENCE_NODE:
          for grandchild in child.childNodes:
            grandchild= grandchild._recurse(True, clone= True, readonly= False)
            self.insertBefore(grandchild, child)
          self.removeChild(child)
    for child in self._childNodes._list[:]:

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
            previous.data= previous.data+child.data
            self.removeChild(child)
            continue

      # Convert CDATA to text, concatenating if possible
      #
      if child.nodeType==Node.CDATA_SECTION_NODE:
        if uncdata:
          previous= child.previousSibling
          if child.data=='':
            self.removeChild(child)
          elif previous is not None and previous.nodeType==Node.TEXT_NODE:
            previous.data= previous.data+child.data
            self.removeChild(child)
          else:
            text= self._ownerDocument.createTextNode(self.data)
            self.replaceChild(text, child)
          continue
        else:

          # Split CDATA sections including string ']]>'
          #
          if string.find(child.data, ']]>')!=-1:
            config= self._ownerDocument.config
            if config.getParameter('split-cdata-sections'):
              datas= string.split(child.data, ']]>')
              child.data= datas[0]
              refChild= child.nextSibling
              for data in datas[1:]:
                newChild= self._ownerDocument.createTextNode(']]>')
                self.insertBefore(newChild, refChild)
                newChild= self._ownerDocument.createCDATASection(data)
                self.insertBefore(newChild, refChild)
              config._handleError(DOMErrorCdataSectionSplitted(child))
              continue
            else:
              config._handleError(DOMErrorInvalidDataInCdataSection(child))

      # Remove comments. If node remains, recurse into it.
      #
      if uncomment and child.nodeType==Node.COMMENT_NODE:
        self.removeChild(child)
        continue
      child.normalize(
        text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
      )

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
    return self._containerNode.baseURI

  def _get_location(self):
    return DOMLocator(self, self._row, self._col)
  def _setLocation(self, (row, col)):
    self._row= row
    self._col= col

  # Support functions
  #
  def _getInsertable(self):
    return [self]
  def _getMarkup(self, config, filter, newLine):
    markup= ''
    for child in self._childNodes:
      markup= markup+child._getMarkup(config, filter, newLine)
    return markup

  def _renameNode(self, namespaceURI, qualifiedName):
    raise NotSupportedErr(self, 'renameNode')

  def _changed(self):
    self._sequence= self._sequence+1
    if self._containerNode is not None:
      self._containerNode._changed()


class EntityMap(NamedNodeMap):
  _childTypes= [Node.ENTITY_NODE]
class NotationMap(NamedNodeMap):
  _childTypes= [Node.NOTATION_NODE]
class ElementDeclarationMap(NamedNodeMap):
  _childTypes= [Node.ELEMENT_DECLARATION_NODE]
class AttributeDeclarationMap(NamedNodeMap):
  _childTypes= [Node.ATTRIBUTE_DECLARATION_NODE]
class AttributeListMap(NamedNodeMap):
  _childTypes= [Node.ATTRIBUTE_LIST_NODE]
class AttrMap(NamedNodeMap):
  """ A node map used for storing the attributes of an element, and updating
      the defaulted attributes automatically on changes.
  """
  _childTypes= [Node.ATTRIBUTE_NODE]
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
            declarationList= doctype.attlists.getNamedItem(
              self._ownerNode.nodeName
            )
            if declarationList is not None:
              declaration= declarationList.declarations.getNamedItem(
                oldItem.nodeName
              )
              if (
                declaration is not None and
                declaration.defaultType==AttributeDeclaration.DEFAULT_VALUE
              ):
                declaration._createAttribute(self._ownerNode)


class NamedNode(Node):
  """ Base class for nodes who have specific names but no namespace
      capability (entity references and so on).
  """
  def __init__(self, ownerDocument= None, nodeName= None, _strict= True):
    Node.__init__(self, ownerDocument, None, None, None)
    if _strict and nodeName is not None:
      for char in nodeName:
        if char in _NOTNAME:
          raise InvalidCharacterErr(nodeName, char)
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
    if localName is not None:
      for char in localName:
        if char in _NOTNAME:
          raise InvalidCharacterErr(localName, char)
    if prefix is not None:
      for char in prefix:
        if char in _NOTNAME:
          raise InvalidCharacterErr(prefix, char)
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
  def _set_prefix(self, value):
    if value=='':
      value= None
    if (
      self._namespaceURI in (None, NONS) or ':' in value or
      (value=='xml' and self._namespaceURI!=XMNS) or
      (value=='xmlns' and self._namespaceURI!=NSNS) or
      (value not in ('xml', 'xmlns') and self._namespaceURI in (XMNS, NSNS))
    ):
      if self._namespaceURI==NONS:
        raise NamespaceErr(value+':', None)
      else:
        raise NamespaceErr(value+':'+self._localName, self._namespaceURI)
    for char in value:
      if char in _NOTNAME:
        raise InvalidCharacterErr(value, char)
    self._prefix= value
    self._changed()
  def _renameNode(self, namespaceURI, qualifiedName):
    for char in qualifiedName:
      if char in _NOTNAME:
        raise InvalidCharacterErr(nodeName, char)
    prefix, localName= _splitName(qualifiedName)
    if localName is None:
      self._namespaceURI= NONS
      self._prefix= None
      self._localName= qualifiedName
    else:
      if (
        (namespaceURI is None and prefix is not None) or
        (namespaceURI==XMNS)!=(prefix=='xml') or
        (namespaceURI==NSNS)!=('xmlns' in (prefix, qualifiedName)) or
        (prefix=='xmlns' and localName in ('xml', 'xmlns')) or
        (self.nodeType==Node.ELEMENT_NODE and (
          namespaceURI in (XMNS, NSNS) or prefix in ('xml', 'xmlns')
        ))
      ):
        raise NamespaceErr(qualifiedName, namespaceURI)
      self._namespaceURI= namespaceURI
      self._prefix= prefix
      self._localName= localName
  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
    Node.normalize(
      self,text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
    )
    if ents:
      if self._prefix is not None and self._namespaceURI is None:
        self._namespaceURI= self._lookupNamespaceURI(self._prefix)

  def isDefaultNamespace(self, namespaceURI):
    if namespaceURI=='':
      namespaceURI= None
    return self.lookupNamespaceURI(None)==namespaceURI
  def lookupNamespaceURI(self, prefix):
    if prefix=='xmlns':
      return NSNS
    if prefix=='xml':
      return XMNS
    localName= prefix
    if prefix is None:
      localName= 'xmlns'
    return self._lookupNamespaceURI(localName)
  def lookupPrefix(self, namespaceURI):
    if namespaceURI=='':
      namespaceURI= None
    if namespaceURI is None:
      return None
    if namespaceURI==NSNS:
      return 'xmlns'
    if namespaceURI==XMNS:
      return 'xml'
    return self._lookupPrefix(namespaceURI, [])
  def _get_schemaTypeInfo(self):
    return TypeInfo(self)


class Document(Node):
  """ Implementation of DOM 3 Document and DocumentLS interfaces.
  """
  def __init__(self):
    Node.__init__(self, self, None, None, None)
    self._xmlStandalone= False
    self._xmlVersion= None
    self._xmlEncoding= None
    self._actualEncoding= None
    self._documentURI= None
    self._strictErrorChecking= True
    self._config= DOMConfiguration()

  def _cloneTo(self, node):
    Node._cloneTo(self, node)
    node._xmlStandalone= self._xmlStandalone
    node._xmlVersion= self._xmlVersion
    node._xmlEncoding= self._xmlEncoding
    node._actualEncoding= self._actualEncoding
    node._documentURI= self._documentURI
    node._strictErrorChecking= self._strictErrorChecking

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
  def _get_config(self):
    return self._config

  def _get_xmlStandalone(self):
    return self._xmlStandalone
  def _set_xmlStandalone(self, value):
    self._xmlStandalone= value
  def _get_xmlVersion(self):
    return self._xmlVersion
  def _set_xmlVersion(self, value):
    self._xmlVersion= value
  def _get_xmlEncoding(self):
    return self._xmlEncoding
  def _set_xmlEncoding(self, value):
    self._xmlEncoding= value
  def _get_actualEncoding(self):
    return self._actualEncoding
  def _get_documentURI(self):
    return self._documentURI
  def _set_documentURI(self, value):
    self._documentURI= value
  def _get_strictErrorChecking(self):
    return self._strictErrorChecking
  def _set_strictErrorChecking(self, value):
    self._strictErrorChecking= value

  def isDefaultNamespace(self, namespaceURI):
    root= self.documentElement
    if root is not None:
      return root.isDefaultNamespace(namespaceURI)
    return False
  def lookupNamespaceURI(self, prefix):
    root= self.documentElement
    if root is not None:
      return root.lookupNamespaceURI(prefix)
    return None
  def lookupPrefix(self, namespaceURI):
    root= self.documentElement
    if root is not None:
      return root.lookupPrefix(namespaceURI)
    return None

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
    node.normalize(text= False, ents= True)
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

  def importNode(self, importedNode, deep):
    if importedNode.nodeType in (Node.DOCUMENT_NODE, Node.DOCUMENT_TYPE_NODE):
      raise NotSupportedErr(importedNode, 'importNode')
    return importedNode._recurse(deep, clone= True, ownerDocument= self)
  def adoptNode(self, source):
    if source._containerNode!=None:
      if source.nodeType==Node.ATTRIBUTE_NODE:
        source._containerNode.removeAttributeNode(source)
      else:
        source._containerNode.removeChild(source)
      source._containerNode= None
    if source.nodeType==Node.ATTRIBUTE_NODE:
      source._specified= True
    dest= source._recurse(True, ownerDocument= self)
    dest.normalize(False, ents= True)
    return dest
  def renameNode(self, n, namespaceURI, qualifiedName):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'renameNode')
    if n.ownerDocument is not self:
      raise WrongDocumentErr(n, self)
    if namespaceURI=='':
      namespaceURI= None
    n._renameNode(namespaceURI, qualifiedName)
    n._changed()
    n._callUserDataHandlers(UserDataHandler.NODE_RENAMED, self, None)
    return self
      
  def normalizeDocument(self):
    unws= not self._config.getParameter('element-content-whitespace')
    uncdata= not self._config.getParameter('cdata-sections')
    uncomment= not self._config.getParameter('comments')
    unent= not self._config.getParameter('entities')
    unns= not self._config.getParameter('namespaces')
    unnsattr= not self._config.getParameter('namespace-declarations')
    self.normalize(
      True,True,True,True,True,unws,unnsattr,unns,uncdata,uncomment,unent
    )

  def _get_async(self):
    return False
  def _set_async(self, value):
    if value:
      raise NotSupportedErr(self, 'async')
  def abort(self):
    pass
  def load(self, uri):
    parser= DOMParser()
    parser.parseURI(uri, document= self)
  def loadXML(self, source):
    input= DOMInput()
    input.stringData= source
    parser= DOMParser(self._config)
    parser.parse(input, document= self)
  def saveXML(self, snode= None):
    if snode is None:
      snode= self
    serializer= DOMSerializer(self._config, '\n')
    return serializer.writeToString(snode)
  def _getMarkup(self, config, filter, newLine):
    markup= ''
    if (config.getParameter('xml-declaration') and (
      self._xmlVersion is not None or self._xmlEncoding is not None
      or self._xmlStandalone
    )):
      markup= markup+'<?xml '
      if self._xmlVersion is not None:
        markup= markup+'version="%s"' % self._xmlVersion
      else:
        markup= markup+'version="1.0"'
      if self._xmlEncoding is not None:
        markup= markup+' encoding="%s"' % self._xmlEncoding
      if self._xmlStandalone:
        markup= markup=' standalone="yes"'
      markup= markup+'?>'
    return markup+Node._getMarkup(self, config, filter, newLine)

class DocumentFragment(Node):
  def __init__(self, ownerDocument= None):
    Node.__init__(self, ownerDocument, None, None, None)
  def _get_nodeType(self):
    return Node.DOCUMENT_FRAGMENT_NODE
  def _get_nodeName(self):
    return '#document-fragment'
  def _getInsertable(self):
    return self._childNodes._list[:]


class Element(NamedNodeNS):
  """ Implementation of DOM 3 Element and ElementNS interfaces.
  """
  def __init__(self,
    ownerDocument= None, namespaceURI= None, localName= None, prefix= None
  ):
    NamedNodeNS.__init__(self, ownerDocument, namespaceURI, localName, prefix)
    self._attributes= AttrMap(self)
  def _cloneDone(self):
    self._setDefaultAttributes()
  def _renameNode(self, namespaceURI, qualifiedName):
    NamedNodeNS._renameNode(self, namespaceURI, qualifiedName)
    self._setDefaultAttributes()
    self._changed()
  def _get_nodeType(self):
    return Node.ELEMENT_NODE
  def _get_tagName(self):
    return self.nodeName

  def lookupNamespaceURI(self, prefix):
    if self.namespaceURI is not None and self.prefix==prefix:
      return self.namespaceURI
    return NamedNodeNS.lookupNamespaceURI(self, prefix)
  def lookupPrefix(self, namespaceURI):
    if namespaceURI=='':
      namespaceURI= None
    if self.prefix is not None and self.namespaceURI is not None:
      if self.namespaceURI==namespaceURI:
        return self.prefix
    return NamedNodeNS.lookupPrefix(self, namespaceURI)

  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
    NamedNodeNS.normalize(
      self,text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
    )
    if ns and self._namespaceURI!=NONS:
      if self._lookupNamespaceURI(self._prefix)!=self._namespaceURI:
        if self._prefix is None:
          if self._namespaceURI is None:
            self.setAttributeNS(NSNS, 'xmlns', '')
          else:
            self.setAttributeNS(NSNS, 'xmlns', self._namespaceURI)
        elif self._namespaceURI is not None:
          self.setAttributeNS(NSNS, 'xmlns:'+self._prefix, self._namespaceURI)
    for index in range(self._attributes.length):
      attr= self._attributes.item(index)
      attr.normalize(
        text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
      )
      if unnsattr:
        if attr.namespaceURI==NSNS:
          self._attributes._writeItem(attr, None)
          index= index-1

  def hasAttribute(self, name):
    return self._attributes.getNamedItem(name) is not None
  def getAttribute(self, name):
    attr= self._attributes.getNamedItem(name)
    if attr is None:
      return ''
    return attr.value
  def setAttribute(self, name, value):
    attr= self._attributes.getNamedItem(name)
    if attr is None:
      attr= Attr(self._ownerDocument, NONS, name, None, True)
      self._attributes.setNamedItem(attr)
    else:
      attr._specified= True
    attr.value= value
  def removeAttribute(self, name):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'renameNode')
    try:
      self._attributes.removeNamedItem(name)
    except NotFoundErr:
      pass
  def getAttributeNode(self, name):
    return self._attributes.getNamedItem(name)
  def setAttributeNode(self, node):
    return self._attributes.setNamedItem(node)
  def removeAttributeNode(self, node):
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
    attr= self._attributes.getNamedItemNS(namespaceURI, qualifiedName)
    if attr is None:
      attr= self._ownerDocument.createAttributeNS(namespaceURI, qualifiedName)
      self._attributes.setNamedItemNS(attr)
    else:
      attr._specified= True
    attr.value= value
  def removeAttributeNS(self, namespaceURI, localName):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'renameNode')
    try:
      self._attributes.removeNamedItemNS(namespaceURI, localName)
    except NotFoundErr:
      pass
  def getAttributeNodeNS(self, namespaceURI, localName):
    return self._attributes.getNamedItemNS(namespaceURI, localName)
  def setAttributeNodeNS(self, node):
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
  def setIdAttributeNode(self, node, isId):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setIdAttribute')
    node._isId= isId

  def _renameNode(self, namespaceURI, qualifiedName):
    if namespaceURI=='':
      namespaceURI= None
    NamedNodeNS._renameNode(self, namespaceURI, qualifiedName)
    self._setDefaultAttributes()

  def _setDefaultAttributes(self):
    if self._ownerDocument is None or self._ownerDocument.doctype is None:
      return
    declarationList= self._ownerDocument.doctype.attlists.getNamedItem(
      self.tagName
    )
    if declarationList is None:
      return
    for attr in self._attributes._list[:]:
      if not attr.specified:
        self.removeAttributeNode(attr)
    for declaration in declarationList.declarations:
      if (
        declaration.defaultType==AttributeDeclaration.DEFAULT_VALUE and
        not self.hasAttribute(declaration.nodeName)
      ):
        declaration._createAttribute(self)

  def _get_markupContent(self):
    return Node._getMarkup(self, self._ownerDocument.config, None, '\n')
  def _set_markupContent(self, value):
    input= DOMInput()
    input.stringData= value
    parser= DOMParser(self._ownerDocument._config)
    parser.parseWithContext(input, self, DOMParser.ACTION_REPLACE_CHILDREN)
  def _getMarkup(self, config, filter, newLine):
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (filter.whatToShow & NodeFilter.SHOW_ELEMENT)>0:
      accepted= filter.acceptNode(self)
    if accepted==NodeFilter.FILTER_REJECT:
      return ''
    if accepted==NodeFilter.FILTER_SKIP:
      return NamedNodeNS._getMarkup(self, config, filter, newLine)
    markup= '<'+self.tagName
    for attr in self._attributes:
      attrMarkup= attr._getMarkup(config, None, newLine)
      if attrMarkup!='':
        markup= markup+' '+attrMarkup
    if self._childNodes.length==0:
      markup= markup+'/>'
    else:
      markup= markup+'>%s</%s>' % (
        NamedNodeNS._getMarkup(self, config, filter, newLine), self.tagName
      )
    return markup


class Attr(NamedNodeNS):
  def __init__(self,
    ownerDocument= None,
    namespaceURI= None, localName= None, prefix= None, specified= True
  ):
    NamedNodeNS.__init__(self, ownerDocument, namespaceURI, localName, prefix)
    self._specified= specified
    self._isId= False
  def cloneNode(self, deep):
    node= NamedNodeNS.cloneNode(self, True)
    node._specified= True
    return node
  def _recurse(self, deep, clone= False, ownerDocument= None, readonly= None):
    return NamedNodeNS._recurse(self, True, clone, ownerDocument, readonly)
  def _cloneTo(self, node):
    NamedNodeNS._cloneTo(self, node)
    node._isId= self._isId

  def _get_nodeType(self):
    return Node.ATTRIBUTE_NODE
  def _get_nodeValue(self):
    return self.textContent
  def _get_name(self):
    return self.nodeName
  def _get_value(self):
    return self.textContent
  def _set_nodeValue(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setIdAttribute')
    self.value= value

  def _set_value(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'value')
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
    if namespaceURI=='':
      namespaceURI= None
    owner= self._containerNode
    if owner is not None:
      owner.removeAttributeNode(self)
    NamedNodeNS._renameNode(self, namespaceURI, qualifiedName)
    if owner is not None:
      owner.setAttributeNodeNS(self)

  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
    NamedNodeNS.normalize(
      self,text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
    )
    if ns and self._namespaceURI not in (NONS, NSNS, XMNS):
      prefixNamespace= self._lookupNamespaceURI(self._prefix)
      if prefixNamespace!=self._namespaceURI:
        if not self._specified:
          self._namespaceURI= prefixNamespace
        elif self._namespaceURI is None:
          self._prefix= None
        else:
          prefix= self._lookupPrefix(self._namespaceURI, [])
          if prefix is None:
            arbitraryNumber= 0
            while True:
              prefix= 'NS'+str(arbitraryNumber)
              if not self._containerNode.hasAttributeNS(NSNS, prefix):
                break
              arbitraryNumber= arbitraryNumber+1
            self._containerNode.setAttributeNS(
              NSNS, 'xmlns:'+prefix, self._namespaceURI
            )
          self._prefix= prefix
    if atts:
      r= string.replace
      value= r(r(self.textContent, '\t', ' '), '\n', '')
      if self.schemaTypeInfo.typeName not in ('CDATA', None):
        value= string.join(
          filter(lambda s: s!='', string.split(value, ' ')), ' '
        )
      while self.firstChild is not None:
        self.removeChild(self.firstChild)
      if value!='':
        self.appendChild(self._ownerDocument.createTextNode(value))
  def _getMarkup(self, config, filter, newLine):
    if not self._specified and config.getParameter('discard-default-content'):
      return ''
    markup= NamedNodeNS._getMarkup(self, config, filter, '\n')
    markup= string.replace(string.replace(markup, '\n', '&#10;'), '\t','&#9;')
    if '"' in markup:
      if "'" in markup:
        return '%s="%s"' % (self.name, string.replace(markup, '"', '&quot;'))
      else:
        return "%s='%s'" % (self.name, markup)
    else:
      return '%s="%s"' % (self.name, markup)


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
  def _get_textContent(self):
    return self.data
  def _set_nodeValue(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setIdAttribute')
    self.data= value

  def _get_data(self):
    return self._data
  def _get_length(self):
    return len(self._data)
  def _set_data(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'data')
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

  def _getMarkup(self, config, filter, newLine):
    return string.replace(self._data, '\n', newLine)

class Comment(CharacterData):
  def _get_nodeType(self):
    return Node.COMMENT_NODE
  def _get_nodeName(self):
    return '#comment'
  def _getMarkup(self, config, filter, newLine):
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (filter.whatToShow & NodeFilter.SHOW_COMMENT)>0:
      accepted= filter.acceptNode(self)
    if accepted!=NodeFilter.FILTER_ACCEPT:
      return ''
    if not config.getParameter('comments'):
      return ''
    markup= CharacterData._getMarkup(self, config, filter, newLine)
    if markup[-1:]=='-':
      markup= markup+' '
    return '<!--'+string.replace(markup, '--', '-_')+'-->'

class Text(CharacterData):
  def _get_nodeType(self):
    return Node.TEXT_NODE
  def _get_nodeName(self):
    return '#text'

  def _get_isElementContentWhitespace(self):
    pn= self._containerNode
    if pn is None or pn.nodeType!=Node.ELEMENT_NODE:
      return False
    contentType= ElementDeclaration.MIXED_CONTENT
    if self._ownerDocument.config.getParameter('pxdom-assume-element-content'):
      contentType= ElementDeclaration.ELEMENT_CONTENT
    if self._ownerDocument.doctype is not None:
      eldec= self._ownerDocument.doctype.elements.getNamedItem(pn.nodeName)
      if eldec is not None:
        contentType= eldec.contentType
    if contentType!=ElementDeclaration.ELEMENT_CONTENT:
      return False
    for c in self._data:
      if c not in ' \t\n':
        return False
    return True

  def splitText(self, offset):
    count= len(self._data)-offset
    newData= self.substringData(offset, count)
    self.deleteData(offset, count)
    newNode= self._ownerDocument.createTextNode(newData)
    if self.parentNode is not None:
      self.parentNode.insertBefore(newNode, self.nextSibling)
    return newNode

  # DOM 3 adjacent text node stuff.
  #
  def _get_wholeText(self):
    value= ''
    for node in self._getLogicallyAdjacentTextNodes():
      value= value+node.data
    return value

  def replaceWholeText(self, value):
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

  def _getLogicallyAdjacentTextNodes(self):
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

  def _getMarkup(self, config, filter, newLine):
    if not config.getParameter('element-content-whitespace'):
      if self.isElementContentWhitespace:
        return ''
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (filter.whatToShow & NodeFilter.SHOW_TEXT)>0:
      accepted= filter.acceptNode(self)
    if accepted!=NodeFilter.FILTER_ACCEPT:
      return ''
    markup= CharacterData._getMarkup(self, config, filter, newLine)
    r= string.replace
    return r(r(r(markup, '&', '&amp;'), '<', '&lt;'), ']]>', ']]&gt;')

class CDATASection(Text):
  def _get_nodeType(self):
    return Node.CDATA_SECTION_NODE
  def _get_nodeName(self):
    return '#cdata-section'
  def _getMarkup(self, config, filter, newLine):
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (
      filter.whatToShow & NodeFilter.SHOW_CDATA_SECTION
    )>0:
      accepted= filter.acceptNode(self)
    if accepted!=NodeFilter.FILTER_ACCEPT:
      return ''
    markup= CharacterData._getMarkup(self, config, filter, newLine)
    if config.getParameter('cdata-sections'):
      if string.find(markup, ']]>')!=-1:
        if config.getParameter('split-cdata-sections'):
          config._handleError(DOMErrorCdataSectionSplitted(self))
          return '<![CDATA[%s]]>' % string.replace(
            markup, ']]>', ']]>]]&gt;<![CDATA['
          )
        else:
          config._handleError(DOMErrorInvalidDataInCdataSection(self))
      else:
        return '<![CDATA[%s]]>' % markup
    else:
      r= string.replace
      return r(r(r(markup, '&', '&amp;'), '<', '&lt;'), ']]>', ']]&gt;')

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
  def _get_textContent(self):
    return self.data
  def _set_nodeValue(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'setIdAttribute')
    self.data= value

  def _get_target(self):
    return self.nodeName
  def _get_data(self):
    return self._data
  def _set_data(self, value):
    if self._readonly:
      raise NoModificationAllowedErr(self, 'data')
    self._data= value
  def _getMarkup(self, config, filter, newLine):
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (
      filter.whatToShow & NodeFilter.SHOW_PROCESSING_INSTRUCTION
    )>0:
      accepted= filter.acceptNode(self)
    if accepted!=NodeFilter.FILTER_ACCEPT:
      return ''
    markup= string.replace(string.replace(self._data, '\n', newLine), '?>','')
    return '<?%s %s?>' % (self.nodeName, markup)

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
  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
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
            clone.normalize(
              False,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
            )
            clone._recurse(True, readonly= True)
      self.readonly= True
  def _getMarkup(self, config, filter, newLine):
    accepted= NodeFilter.FILTER_ACCEPT
    if filter is not None and (
      filter.whatToShow & NodeFilter.SHOW_ENTITY_REFERENCE
    )>0:
      accepted= filter.acceptNode(self)
    if accepted==NodeFilter.FILTER_ACCEPT:
      return '&%s;' % self.nodeName
    if accepted==NodeFilter.FILTER_SKIP:
      return NamedNode._getMarkup(self, config, filter, newLine)
      

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
    self._entities= EntityMap(self)
    self._notations= NotationMap(self)
    self._elements= ElementDeclarationMap(self)
    self._attlists= AttributeListMap(self)
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._publicId= self._publicId
    node._systemId= self._systemId
    node._internalSubset= self._internalSubset
  def _recurseTo(self, node, clone, ownerDocument, readonly):
    for entity in self._entities:
      r= entity._recurse(True, clone, ownerDocument, readonly)
      if clone:
        node._entities._append(r)
    for notation in self._notations:
      r= notation._recurse(True, clone, ownerDocument, readonly)
      if clone:
        node._notations._append(r)
    for element in self._elements:
      r= element._recurse(True, clone, ownerDocument, readonly)
      if clone:
        node._elements._append(r)
    for attlist in self._attlists:
      r= attlist._recurse(True, clone, ownerDocument, readonly)
      if clone:
        node._attlists._append(r)
  def isEqualNode(self, other):
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
  def _get_elements(self):
    return self._elements
  def _get_attlists(self):
    return self._attlists
  def _set_internalSubset(self, value):
    self._internalSubset= value

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
  def normalize(self,
    text= True, atts= False, ents= False, ns= False, cdata= False, unws= False,
    unnsattr=False, unns=False, uncdata=False, uncomment=False, unent=False
  ):
    NamedNode.normalize(
      self,text,atts,ents,ns,cdata,unws,unnsattr,unns,uncdata,uncomment,unent
    )
    if unent:
      while self._entities.length>0:
        self._entities._writeItem(self._entities.item(0), None)
  def _getMarkup(self, config, filter, newLine):
    markup= '<!DOCTYPE '+self.name
    if self._publicId is not None:
      markup= markup+' PUBLIC "%s"' % self._publicId
      if self._systemId is not None:
        markup= markup+' "%s"' % self._systemId
    elif self._systemId is not None:
      markup= markup+' SYSTEM "%s"' % self._systemId
    if self._internalSubset is not None:
      markup= markup+' [%s]' % self._internalSubset
    return markup+'>'


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
    self._actualEncoding= None
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
    node._publicId= self._publicId
    node._systemId= self._systemId
    node._notationName= self._notationName
    node._xmlVersion= self._xmlVersion
    node._xmlEncoding= self._xmlEncoding
    node._actualEncoding= self._actualEncoding
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
  def _get_actualEncoding(self):
    return self._actualEncoding

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


# Extended node types for document type modelling - not part of standard DOM
#
class ElementDeclaration(NamedNode):
  """ Node representing an <!ELEMENT> declaration in document type. Prescribed
      content is described by 'contentType' and 'elements', which is null for
      EMPTY and ANY content, or a ContentDeclarationList for Mixed and element
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


class ContentDeclarationList(DOMList):
  """ A list representing part of the content model given in an <!ELEMENT>
      declaration. Apart from normal DOMList accessors, has flags specifying
      whether the group is optional, can be included more than once (or both),
      and whether it's a sequence or a choice. List items are element name
      strings or, in the case of element content, ContentDeclarationLists. In
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
    self._declarations= AttributeDeclarationMap(self)
  def _cloneTo(self, node):
    NamedNode._cloneTo(self, node)
  def _recurseTo(self, node, clone, ownerDocument, readonly):
    for declaration in self._declarations:
      r= declaration._recurse(True, clone, ownerDocument, readonly)
      if clone:
        node._declarations._append(r)
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
      namespaceURI= element.lookupNamespaceURI(prefix)
      attr= element.ownerDocument.createAttributeNS(
        namespaceURI, self.nodeName, _strict= False
      )
    for child in self._childNodes:
      attr.appendChild(child.cloneNode(True))
    element.setAttributeNodeNS(attr)
    attr._specified= False

# DOM 3 Load/Save
#
class DOMConfiguration(DOMObject):
  _defaults= {
    'error-handler':                             (None,  True ),
    'resource-resolver':                         (None,  True ),
    'schema-location':                           (None,  False),
    'schema-type':                               (None,  False),
    'canonical-form':                            (False, False),
    'cdata-sections':                            (True,  True ),
    'charset-overrides-xml-encoding':            (True,  True ),
    'check-character-normalization':             (False, False),
    'comments':                                  (True,  True ),
    'datatype-normalization':                    (False, True ),
    'discard-default-content':                   (True,  True ),
    'disallow-doctype':                          (False, True ),
    'element-content-whitespace':                (True,  True ),
    'entities':                                  (True,  True ),
    'format-pretty-print':                       (False, False),
    'ignore-unknown-character-denormalizations': (True,  False),
    'namespaces':                                (True,  True ),
    'namespace-declarations':                    (True,  True ),
    'normalize-characters':                      (False, False),
    'split-cdata-sections':                      (True,  True ),
    'supported-media-types-only':                (False, False),
    'validate':                                  (False, False),
    'validate-if-schema':                        (False, False),
    'well-formed':                               (True,  True ),
    'xml-declaration':                           (True,  True ),
    'pxdom-assume-element-content':              (False, True )
  }
  def __init__(self):
    DOMObject.__init__(self)
    self._parameters= {}
    for (name, (value, canSet)) in DOMConfiguration._defaults.items():
      self._parameters[name]= value

  def canSetParameter(self, name, value):
    name= string.lower(name)
    if name=='infoset':
      return True
    if self._parameters[name]==value:
      return True
    return DOMConfiguration._defaults.get(value, (None, False))[1]

  def getParameter(self, name):
    name= string.lower(name)
    if name=='infoset':
      return (
        self._parameters['element-content-whitespace'] and
        self._parameters['comments'] and
        self._parameters['namespaces'] and
        not self._parameters['namespace-declarations'] and
        not self._parameters['validate-if-schema'] and
        not self._parameters['entities'] and
        not self._parameters['datatype-normalization'] and
        not self._parameters['cdata-sections']
      )
    if not self._parameters.has_key(name):
      raise NotFoundErr(self, None, name)
    return self._parameters[name]

  def setParameter(self, name, value):
    name= string.lower(name)
    if name=='infoset':
      if value:
        self._parameters['element-content-whitespace']= True
        self._parameters['comments']= True
        self._parameters['namespaces']= True
        self._parameters['namespace-declarations']= False
        self._parameters['validate-if-schema']= False
        self._parameters['entities']= False
        self._parameters['datatype-normalization']= False
        self._parameters['cdata-sections']= False
    else:
      if not DOMConfiguration._defaults.has_key(name):
        raise NotFoundErr(self, None, name)
      if not DOMConfiguration._defaults[name][1]:
        raise NotSupportedErr(self, name)
      self._parameters[name]= value

  def _get_parameterNameList(self):
    return self._parameters.keys()

  def _handleError(self, exn):
    handler= self._parameters['error-handler']
    if handler is None:
      cont= exn.severity==DOMError.SEVERITY_WARNING
    else:
      error= DOMError(exn.severity, str(exn), exn.type, exn.node)
      cont= handler.handleError(error)
      if exn.severity==DOMError.SEVERITY_FATAL_ERROR:
        cont= False
    if not cont:
      raise exn


class DOMInput(DOMObject):
  def __init__(self):
    DOMObject.__init__(self)
    self._byteStream= None
    self._characterStream= None
    self._stringData= None
    self._encoding= None
    self._publicId= None
    self._systemId= None
    self._baseURI= None
    self._certified= False
    self._actualEncoding= None
    self._actualBytes= None

  def _get_byteStream(self): return self._byteStream
  def _get_characterStream(self): return self._characterStream
  def _get_stringData(self): return self._stringData
  def _get_encoding(self): return self._encoding
  def _get_publicId(self): return self._publicId
  def _get_systemId(self): return self._systemId
  def _get_baseURI(self): return self._baseURI
  def _get_certified(self): return self._certified
  def _get_actualEncoding(self): return self._actualEncoding

  def _set_byteStream(self, value):
    self._byteStream= value
    self._actualBytes= None
  def _set_characterStream(self, value):
    self._characterStream= value
    self._actualBytes= None
  def _set_stringData(self, value):
    self._stringData= value
    self._actualBytes= None
  def _set_encoding(self, value):
    self._encoding= value
    self._actualBytes= None
  def _set_publicId(self, value):
    self._publicId= value
  def _set_systemId(self, value):
    self._systemId= value
    self._actualBytes= None
  def _set_baseURI(self, value):
    self._baseURI= value
  def _set_certified(self, value):
    self._certified= value

  def read(self, internalEncoding= None, charsetOverride= False):
    if self._stringData is not None:
      return self._stringData
    if self._characterStream is not None:
      return self.characterStream.read()
    actualCharset= None
    if self._actualBytes is None:
      self._actualBytes= ''
      stream= None
      if self._byteStream is not None:
        stream= self._byteStream
      elif self._systemId is not None:
        uri= self._systemId
        if self._baseURI is not None:
          uri= urlparse.urljoin(self._baseURI, uri)
        stream= urllib.urlopen(uri)
        actualCharset= stream.info().getparam('charset')
      if stream is not None:
        self._actualBytes= stream.read()
    if self._actualBytes is None:
      raise DOMErrorNoInput(None)
    actualEncoding= internalEncoding
    if (actualEncoding is None or
      charsetOverride and actualCharset is not None
    ):
      actualEncoding= actualCharset
    if self._encoding is not None:
      actualEncoding= self.encoding
    if (actualEncoding is None or
      string.lower(actualEncoding)=='utf-16'
    ):
      if self._actualBytes[:2] in ('\xff\xfe', '\xfe\xff'):
        if self._actualBytes[:2]=='\xff\xfe':
          actualEncoding= 'utf-16-le'
        else:
          actualEncoding= 'utf-16-be'
    self._actualEncoding= actualEncoding
    if actualEncoding is None:
      actualEncoding= 'utf-8'
    r= string.replace
    if unicode is None:
      data= self._actualBytes
      return r(r(r(data,EBCLS,'\n'),'\r\n','\n'),'\r','\n')
    else:
      try:
        data= unicode(self._actualBytes, actualEncoding)
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
  [FILTER_ACCEPT,FILTER_REJECT,FILTER_SKIP
  ]= range(1, 4)
  def acceptNode(self, n):
    return NodeFilter.FILTER_ACCEPT

class DOMParserFilter(NodeFilter):
  FILTER_INTERRUPT= 4
  def __init__(self, whatToShow):
    NodeFilter.__init__(self)
    self._whatToShow= whatToShow
  def _get_whatToShow(self):
    return self._whatToShow
  def _set_whatToShow(self, value):
    self._whatToShow= value
  def acceptNode(self, enode):
    return NodeFilter.FILTER_ACCEPT
  def startElement(self, elt):
    return NodeFilter.FILTER_ACCEPT

class DOMSerializerFilter(NodeFilter):
  pass

class DOMFilterInterrupt:
  pass

class DOMParser(DOMObject):
  [ACTION_APPEND_AS_CHILDREN,ACTION_REPLACE_CHILDREN,ACTION_INSERT_BEFORE,
  ACTION_INSERT_AFTER,ACTION_REPLACE
  ]= range(1, 6)
  _CHARCHUNK= 1024
  def __init__(self, config= None):
    DOMObject.__init__(self)
    if config is None:
      config= DOMConfiguration()
      config.setParameter('entities', False)
      config.setParameter('cdata-sections', False)
    self._config= config
    self._filter= None
    self._data= ''
    self._index= 0
  def _get_config(self):
    return self._config
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
    self._config._handleError(ParseError(self, message))
  def parseURI(self, uri, document= None):
    input= DOMInput()
    input.systemId= uri
    return self.parse(input, None)
  def parse(self, input, document= None):
    if document is None:
      document= Document()
    if document.doctype is not None:
      document.doctype._recurse(ownerDocument= None)
      document.doctype._containerNode= None
      document._doctype= None
    if input.systemId is not None:
      if input.baseURI is not None:
        document.documentURI= urlparse.urljoin(input.baseURI, input.systemId)
      else:
        document.documentURI= input.systemId
    elif input.baseURI is not None:
      document.documentURI= input.baseURI
    try:
      self._data= input.read()
    except DOMErrorException, exn:
      self._config._handleError(exn)
    self._index= 0

    # Preamble
    #
    if self._next('<?xml'):
      self._p_s()
      if not self._next('version'):
        self._e('Expected \'version="..."\'')
      self._p_eq()
      document.xmlVersion= self._p_lit()
      if not self._next('?>', False):
        self._p_s()
      if self._next('encoding'):
        self._p_eq()
        document.xmlEncoding= self._p_lit()
        if not self._next('?>', False):
          self._p_s()
      if self._next('standalone'):
        self._p_eq()
        standalone= self._p_lit()
        if standalone not in ('no', 'yes'):
          self._e('Expected \'no\' or \'yes\'')
        document.xmlStandalone= (standalone=='yes')
        self._p_s(False)
      if not self._next('?>', True):
        self._e('Expected \'?>\'')
    if document.xmlEncoding is not None:
      override= self._config.getParameter('charset-overrides-xml-encoding')
      try:
        self._data= input.read(document.xmlEncoding, override)
      except DOMErrorException, exn:
        self._config._handleError(exn)
    document._actualEncoding= input.actualEncoding
    self._textQueue= ''
    try: self._parseContent(document, None)
    except DOMFilterInterrupt: pass
    if not self._config.getParameter('entities'):
      if document.doctype is not None:
        document.doctype._entities= EntityMap(document.doctype)
    unnsattr= not self._config.getParameter('namespace-declarations')
    unws= not self._config.getParameter('element-content-whitespace')
    if unnsattr or unws:
      if unws:
        assume= document.config.getParameter('pxdom-assume-element-content')
        document.config.setParameter('pxdom-assume-element-content',
          self._config.getParameter('pxdom-assume-element-content')
        )
      document.normalize(text= False, unnsattr= unnsattr, unws= unws)
      if unws:
        document.config.setParameter('pxdom-assume-element-content', assume)
    return document
  def parseWithContext(self, input, cnode, action):
    try:
      self._data= input.read()
    except DOMErrorException, exn:
      self._config._handleError(exn)
    self._index= 0
    self._textQueue= ''
    if action==DOMParser.ACTION_APPEND_AS_CHILDREN:
      index= cnode.childNodes.length
      try: self._parseContent(cnode, None)
      except DOMFilterInterrupt: pass
      results= cnode.childNodes._list[index:]
    elif action==DOMParser.ACTION_REPLACE_CHILDREN:
      while cnode.childNodes.length>0:
        cnode.removeChild(cnode.childNodes.item(0))
      try: self._parseContent(cnode, None)
      except DOMFilterInterrupt: pass
      results= cnode.childNodes._list
    elif action==DOMParser.ACTION_INSERT_BEFORE:
      previousSibling= cnode.previousSibling
      try: self._parseContent(cnode.parentNode, cnode)
      except DOMFilterInterrupt: pass
      results= []
      while True:
        previousSibling= previousSibling.nextSibling
        if previousSibling is cnode:
          break
        results.append(previousSubling)
    elif action==DOMParser.ACTION_INSERT_AFTER:
      nextSibling= cnode.nextSibling
      try: self._parseContent(cnode.parentNode, nextSibling)
      except DOMFilterInterrupt: pass
      results= []
      node= cnode
      while True:
        node= node.nextSibling
        if node is nextSibling:
          break
        results.append(node)
    elif action==DOMParser.ACTION_REPLACE:
      previousSibling= cnode.previousSibling
      nextSibling= cnode.nextSibling
      cnode.parentNode.removeChild(node)
      try: self._parseContent(cnode.parentNode, nextSibling)
      except DOMFilterInterrupt: pass
      results= []
      while True:
        previousSibling= previousSibling.nextSibling
        if previousSibling is nextSibling:
          break
        results.append(previousSubling)
    if self._index<len(self._data):
      self._e('Expected end of input')
    unnsattr= not self._config.getParameter('namespace-declarations')
    unws= not self._config.getParameter('element-content-whitespace')
    if unnsattr or unws:
      if unws:
        document= cnode.ownerDocument
        assume= document.config.getParameter('pxdom-assume-element-content')
        document.config.setParameter('pxdom-assume-element-content',
          self._config.getParameter('pxdom-assume-element-content')
        )
      for result in results:
        result.normalize(text= False, unnsattr= unnsattr, unws= unws)
      if unws:
        document.config.setParameter('pxdom-assume-element-content', assume)
    if len(results)==0:
      return None
    return results[0]

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
      finds.append(string.find(self._data, char, self._index))
    finds= filter(lambda index: index!=-1, finds)
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
  def _p_eldec(self, isMixed):
    elements= ContentDeclarationList()
    elements.isSequence= None
    while True:
      self._p_s(False)
      if self._next('('):
        if isMixed:
          self._e('Mixed content declarations cannot contain nested sections')
        elements._append(self._p_eldec(False))
      else:
        elements._append(self._p_name())
      self._p_s(False)
      if self._next(')'):
        break
      if self._next('|'):
        sequence= False
      elif self._next('|'):
        sequence= True
      else:
        self._e('Expected \'|\' or \',\' to continue declaration list')
      if elements.isSequence not in (None, sequence):
        self._e('Content declaration list cannot be both choice and sequence')
      elements.isSequence= sequence
    if self._next('*'):
      elements.isOptional= True
      elements.isMultiple= True
    elif self._next('+'):
      elements.isMultiple= True
    elif self._next('?'):
      elements.isOptional= True
    return elements

  def _flushText(self, parentNode, refChild):
    if self._textQueue=='':
      return
    text= parentNode._ownerDocument.createTextNode(self._textQueue)
    self._textQueue= ''
    text._setLocation(self._getLocation())
    self._insertFiltered(text, parentNode, refChild)

  def _insertFiltered(self, newNode, parentNode, refChild):
    parentNode.insertBefore(newNode, refChild)
    if self._filter is not None:
      if ((2**newNode.nodeType) & self._filter.whatToShow)!=0:
        accepted= self._filter.acceptNode(newNode)
        if accepted==DOMParserFilter.FILTER_REJECT:
          parentNode.removeChild(newNode)
        elif accepted==DOMParserFilter.FILTER_SKIP:
          while newNode.firstChild is not None:
            parentNode.insertBefore(newNode.firstChild, newNode)
          parentNode.removeChild(newNode)
        elif accepted==DOMParserFilter.FILTER_INTERRUPT:
          raise DOMFilterInterrupt()

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
            if self._config.getParameter('disallow-doctype'):
              self._config._handleError(DOMErrorDoctypeNotAllowed(None))
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
    nons= not self._config.getParameter('namespaces')
    qualifiedName= self._p_name()
    try:
      element= parentNode._ownerDocument.createElementNS(
        None, qualifiedName, _strict= False, _default= False
      )
    except NamespaceErr:
      element= parentNode._ownerDocument.createElement(qualifiedName)
    element._setLocation(self._getLocation())
    attrs= []
    empty= False
    while True:
      self._p_s(False)
      if self._next('>'):
        break
      if self._next('/>'):
        empty= True
        break
      qualifiedName= self._p_name()
      (prefix, localName)= _splitName(qualifiedName)
      try:
        if 'xmlns' in (prefix, localName):
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
      if attr.namespaceURI==NSNS:
        if element.hasAttributeNS(NSNS, localName):
          if prefix is None:
            self._e('Doubly-declared default namespace')
          self._e('Doubly-declared namespace \'%s\''%localName)
        element.setAttributeNodeNS(attr)
      else:
        attrs.append(attr)
    parentNode.insertBefore(element, refChild)
    if element.localName is not None:
      element._namespaceURI= element.lookupNamespaceURI(element.prefix)
    for attr in attrs:
      if attr.namespaceURI is None and attr.prefix is not None:
        attr._namespaceURI= element.lookupNamespaceURI(attr.prefix)
      if attr.localName is None:
        if element.hasAttribute(attr.name):
          self._e('Duplicated attribute \'%s\'' % attr.name)
        element.setAttributeNode(attr)
      else:
        if element.hasAttributeNS(attr.namespaceURI, attr.localName):
          self._e('Duplicated attribute \'%s\'' % attr.name)
        element.setAttributeNodeNS(attr)
      if attr.schemaTypeInfo.typeName=='ID':
        element.setIdAttributeNode(attr, True)
    element._setDefaultAttributes()
    accepted= DOMParserFilter.FILTER_ACCEPT
    if self._filter is not None:
      if (self._filter.whatToShow & NodeFilter.SHOW_ELEMENT)!=0:
        accepted= self._filter.startElement(element)
        if accepted==DOMParserFilter.FILTER_INTERRUPT:
          raise DOMFilterInterrupt()
    if not empty:
      if accepted==DOMParserFilter.FILTER_REJECT:
        parentNode.removeChild(element)
        filter= self._filter
        self._filter= None
      if accepted==DOMParserFilter.FILTER_SKIP:
        self._parseContent(parentNode, refChild)
      else:
        self._parseContent(element, None)
      if accepted==DOMParserFilter.FILTER_REJECT:
        self._filter= filter
      if not self._next(element.tagName):
        self._e('Expected \'%s\' end-tag' % element.tagName)
      self._p_s(False)
      if not self._next('>'):
        self._e('Expected \'>\'')
    if self._filter is not None and accepted==DOMParserFilter.FILTER_ACCEPT:
      if (self._filter.whatToShow & NodeFilter.SHOW_ELEMENT)!=0:
        accepted= self._filter.acceptNode(newNode)
        if accepted==DOMParserFilter.FILTER_REJECT:
          parentNode.removeChild(newNode)
        elif accepted==DOMParserFilter.FILTER_SKIP:
          while newNode.firstChild is not None:
            parentNode.insertBefore(newNode.firstChild, newNode)
          parentNode.removeChild(newNode)
        elif accepted==DOMParserFilter.FILTER_INTERRUPT:
          raise DOMFilterInterrupt()

  def _parseAttributeValue(self, parentNode, refChild):
    quote= self._p_q()
    while True:
      index= self._find(quote+'&<')
      if index>self._index:
        self._textQueue= self._textQueue+string.replace(
          string.replace(self._data[self._index:index], '\t', ' '), '\n', ' '
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
    if not self._config.getParameter('entities'):
      parentNode.normalize(text= True, atts= True)

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
    if DOMParser._ENTITIES.has_key(name):
      char= DOMParser._ENTITIES[name]
      self._textQueue= self._textQueue+char
    else:
      ent= None
      if not self._config.getParameter('entities'):
        doctype= parentNode._ownerDocument.doctype
        if doctype is not None:
          ent= doctype.entities.getNamedItem(name)
      if ent is None:
        self._flushText(parentNode, refChild)
        ent= EntityReference(parentNode._ownerDocument, name)
        ent._setLocation(self._getLocation())
        self._insertFiltered(ent, parentNode, refChild)
        ent.normalize(text= False, ents= True)
        if ent._containsUnboundPrefix():
          self._config._handleError(DOMErrorUnboundNamespaceInEntity(ent))
      else:
        first= True
        for index in range(ent.childNodes.length):
          child= ent.childNodes.item(index)
          if child.nodeType==Node.TEXT_NODE:
            value= child.data
            if replaceWhite:
              r= string.replace
              value= r(r(child.data, '\t', ' '), '\n', ' ')
            self._textQueue= self._textQueue+value
          else:
            self._flushText(parentNode, refChild)
            parentNode.insertBefore(child.cloneNode(True), refChild)

  def _parseComment(self, parentNode, refChild):
    index= string.find(self._data, '-->', self._index)
    if index==-1:
      self._e('Unclosed comment, no following \'-->\'')
    if self._config.getParameter('comments'):
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
    self._p_s()
    index= string.find(self._data, '?>', self._index)
    if index==-1:
      self._e('Unclosed PI, no following \'?>\'')
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
    if self._config.getParameter('cdata-sections'):
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
      doctype.entities.readonly= True
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
              self._parseEntity(doctype)
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

  def _parseEntity(self, doctype):
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
        if entity._containsUnboundPrefix():
          self._config._handleError(DOMErrorUnboundNamespaceInEntity(entity))
        if doctype.entities.getNamedItem(name) is None:
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
        self._p_s()
        if self._next('|'):
          elements= self._p_eldec(True)
          if elements.isOptional or not elements.isMultiple:
            self._e('Mixed content group must end with \'*\'')
        elif self._next(')'):
          elements= ContentDeclarationList()
        else:
          self._e('Expected \'|\' or end of list')
      else:
        contentType= ElementDeclaration.ELEMENT_CONTENT
        elements= self._p_eldec(False)
    else:
      self._e('Expected content declaration')
    self._p_s(False)
    if not self._next('>'):
      self._e('Expected declaration-ending \'>\'')
    if self._processInternalSubset:
      if doctype.elements.getNamedItem(name) is None:
        element= doctype.createElementDeclaration(name, contentType, elements)
        doctype.elements.setNamedItem(element)
  def _parseAttributeListDeclaration(self, doctype):
    self._p_s()
    name= self._p_name()
    self._p_s()
    if self._processInternalSubset:
      attlist= doctype.attlists.getNamedItem(name)
      if attlist is None:
        attlist= doctype.createAttributeListDeclaration(name)
        doctype.attlists.setNamedItem(attlist)
    else:
      attlist= doctype.createAttributeListDeclaration(name)
    while not self._next('>'):
      name= self._p_name()
      self._p_s()
      typeValues= None
      if self._next('CDATA'):
        attributeType= AttributeDeclaration.CDATA_ATTR
      elif self._next('ID'):
        attributeType= AttributeDeclaration.ID_ATTR
      elif self._next('IDREF'):
        attributeType= AttributeDeclaration.IDREF_ATTR
      elif self._next('IDREFS'):
        attributeType= AttributeDeclaration.IDREFS_ATTR
      elif self._next('ENTITY'):
        attributeType= AttributeDeclaration.ENTITY_ATTR
      elif self._next('ENTITIES'):
        attributeType= AttributeDeclaration.ENTITIES_ATTR
      elif self._next('NMTOKEN'):
        attributeType= AttributeDeclaration.NMTOKEN_ATTR
      elif self._next('NMTOKENS'):
        attributeType= AttributeDeclaration.NMTOKENS_ATTR
      elif self._next('NOTATION'):
        attributeType= AttributeDeclaration.NOTATION_ATTR
        self._p_s()
        typeValues= self._p_enum()
      elif self._next('(', skip= False):
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


# DOM Save serialisation
#
class DOMOutput(DOMObject):
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

  def write(self, data, document):
    if self._characterStream is not None:
      self._characterStream.write(data)
    else:
      if self._byteStream is not None:
        stream= self._byteStream
      elif self._systemId is not None and self._systemId[:8]=='file:///':
        stream= open(urllib.url2pathname(self._systemId), 'wb')
      else:
        raise DOMErrorNoOutputSpecified(None)
      if unicode is None:
        stream.write(data)
      else:
        if self._encoding is not None:
          encoding= self._encoding
        elif document.actualEncoding is not None:
          encoding= document.actualEncoding
        elif document.xmlEncoding is not None:
          encoding= document.xmlEncoding
        else:
          encoding= 'utf-8'
        stream.write(data.encode(encoding))
      if self._byteStream is None:
        stream.close()


class DOMSerializer(DOMObject):
  def __init__(self, config= None, newLine= None):
    DOMObject.__init__(self)
    if config is None:
      config= DOMConfiguration()
    self._config= config
    self._newLine= None
    self._filter= None

  def _get_config(self): return self._config
  def _get_newLine(self): return self._newLine
  def _get_filter(self): return self._filter

  def _set_newLine(self, value): self._newLine= value
  def _set_filter(self, value): self._filter= value

  def writeToString(self, node):
    newLine= self._newLine
    if newLine is None:
      newLine= '\n'
    if node.nodeType==Node.DOCUMENT_NODE:
      node= node.cloneNode(True)
      node.normalize(text= False, ns= True)
    return node._getMarkup(self._config, self._filter, newLine)
  def write(self, node, destination):
    output= self.writeToString(node)
    try:
      destination.write(output, node._ownerDocument)
    except DOMErrorException, exn:
      self._config._handleError(exn)
  def writeToURI(self, node, uri):
    destination= DOMOutput()
    destination.systemId= uri
    self.write(destination, node)


# Convenience functions
#
def parse(fileorpath, parameters= {}):
  """ Convenience minidom-style method to return a document from a file parsed
      with default options.
  """
  parser= DOMParser()
  for (key, value) in parameters.items():
    parser.config.setParameter(key, value)
  src= _implementation.createDOMInput()
  if hasattr(fileorpath, 'read'):
    src.byteStream= fileorpath
    doc= parser.parse(src)
  else:
    src.baseURI= fileorpath
    src.byteStream= open(fileorpath, 'rb')
    doc= parser.parse(src)
    src.byteStream.close()
  return doc

def parseString(content, parameters= {}):
  """ Convenience minidom-style method to return a document from a string
      parsed with default options. (BaseURI won't work in this case.)
  """
  parser= DOMParser()
  for (key, value) in parameters.items():
    parser.config.setParameter(key, value)
  src= _implementation.createDOMInput()
  src.stringData= content
  doc= parser.parse(src)
  return doc


# Exceptions
#
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
    if _splitName(qualifiedName)[1] is None:
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
    return 'attr %s in use' % attr.name
  code= DOMException.INUSE_ATTRIBUTE_ERR


class DOMError(DOMObject):
  [SEVERITY_WARNING,SEVERITY_ERROR,SEVERITY_FATAL_ERROR
  ]= range(1, 4)
  def __init__(self,
    severity, message, type, node
  ):
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
    return self._relatedData.location

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
class DOMErrorCdataSectionSplitted(DOMErrorException):
  severity= DOMError.SEVERITY_WARNING
  type= 'cdata-section-splitted'
class DOMErrorInvalidDataInCdataSection(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'invalid-data-in-cdata-section'
class DOMErrorUnsupportedEncoding(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'unsupported-encoding'
class DOMErrorUnboundNamespaceInEntity(DOMErrorException):
  severity= DOMError.SEVERITY_WARNING
  type= 'unbound-namespace-in-entity'
class DOMErrorDoctypeNotAllowed(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'doctype-not-allowed'
class DOMErrorNoOutputSpecified(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'no-output-specified'
class DOMErrorNoInputSpecified(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'pxdom-no-input-specified'
class ParseError(DOMErrorException):
  severity= DOMError.SEVERITY_FATAL_ERROR
  type= 'pxdom-parse-error'
  def __init__(self, parser, message):
    DOMErrorException.__init__(self, None) 
    self._message= message
    self._parser= parser
    line, column= parser._getLocation()
    self.location= DOMLocator(None, line, column)
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
    line, column= self._parser._getLocation()
    return 'XML parsing error: %s, around line %s, char %s:\n%s%s\n%s^' % (
      self._message, line, column, pre, post, ' '*len(pre)
    )
