pxdom module
============

The *pxdom* module
------------------

pxdom is a implementation of the W3C DOM standard for document
manipulation.

Its main features are:

- Complete support for the DOM Level 3 Core and LS Recommendations.  Passes all
  applicable level1-level3 tests in the DOM Test Suite at the time of writing,
  modulo a few suite flaws (see W3 Bugzilla).

- In-built parser for XML 1.0/1.1 (optionally with namespaces), non-validating
  but with full DTD parser and optional external entity/subset support.

- Stand-alone pure-Python module, also embeddable in other packages.  (No
  dependencies other than the standard string and URL library modules.)

- Compatible with Python 1.5.2 and later; tested up to 2.7. (Requires Python
  1.6 or later for proper Unicode support, and Python 2.3 or later for the
  optional character normalisation features.)

When to use pxdom
-----------------

There are of course a number of other Python DOM implementations. You
might want to consider using pxdom if your DOM application:

- wants to use DOM Level 3 methods;
- requires complete standards-compliance;
- needs to work on a range of setups, regardless of Python version and what XML
  tools are installed.

You might want to consider *not* using pxdom if your DOM application:

- must run as quickly as possible: pxdom is written for correctness, not
  efficiency;
- wants to work together with other parts of Python’s XML frameworks, eg. SAX,
  pulldom.
