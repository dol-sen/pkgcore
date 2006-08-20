# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
value restrictions

works hand in hand with L{pkgcore.restrictions.packages}, these classes match against a value handed in,
package restrictions pull the attr from a package instance and hand it to their wrapped restriction (which is
a value restriction).
"""

import re
from pkgcore.restrictions import restriction, boolean
from pkgcore.util.currying import pre_curry, pretty_docs

value_type = "values"

class base(restriction.base):
	"""
	base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *should* be __slot__ based (lot of instances in memory potentially)
	"""

	__slots__ = ()

	type = value_type

	def force_True(self, pkg, attr, val):
		if self.match(val) ^ self.negate:
			return True
		elif self.negate:
			return pkg.request_disable(attr, val)
		return pkg.request_enable(attr, val)

	def force_False(self, pkg, attr, val):
		if self.match(val) ^ self.negate:
			return True
		elif self.negate:
			return pkg.request_enable(attr, val)
		return pkg.request_disable(attr, val)


class VersionRestriction(base):
	"""use this as base for version restrictions, gives a clue to what the restriction does"""
	__slots__ = ()


class StrMatch(base):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	__slots__ = ("flags",)


class StrRegexMatch(StrMatch):
	
	"""
	regex based matching
	"""
	
	__slots__ = ("regex", "compiled_re")

	__inst_caching__ = True

	def __init__(self, regex, CaseSensitive=True, **kwds):

		"""
		@param regex: regex pattern to match
		@param CaseSensitive: should the match be case sensitive?
		@keyword negate: should the match results be negated?
		"""

		super(StrRegexMatch, self).__init__(**kwds)
		self.regex = regex
		flags = 0
		if not CaseSensitive:
			flags = re.I
		self.flags = flags
		self.compiled_re = re.compile(regex, flags)

	def match(self, value):
		return (self.compiled_re.match(str(value)) is not None) ^ self.negate

	def intersect(self, other):
		if self.regex == other.regex and self.negate == other.negate and self.flags == other.flags:
			return self
		return None

	def __eq__(self, other):
		return self.regex == other.regex and self.negate == other.negate and self.flags == other.flags

	def __hash__(self):
		return hash((self.regex, self.negate, self.flags))

	def __repr__(self):
		if self.negate:
			string = '<%s %r negated @%#8x>'
		else:
			string = '<%s %r @%#8x>'
		return string % (self.__class__.__name__, self.regex, id(self))

	def __str__(self):
		if self.negate:	return "not like %s" % self.regex
		return "like %s" % self.regex


class StrExactMatch(StrMatch):

	"""
	exact string comparison match
	"""

	__slots__ = ("exact", "flags")

	__inst_caching__ = True

	def __init__(self, exact, CaseSensitive=True, **kwds):

		"""
		@param exact: exact string to match
		@param CaseSensitive: should the match be case sensitive?
		@keyword negate: should the match results be negated?
		"""

		super(StrExactMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.exact = str(exact).lower()
		else:
			self.flags = 0
			self.exact = str(exact)

	def match(self, value):
		if self.flags == re.I:
			return (self.exact == value.lower()) != self.negate
		else:	
			return (self.exact == value) != self.negate

	def intersect(self, other):
		s1, s2 = self.exact, other.exact
		if other.flags and not self.flags:
			s1 = s1.lower()
		elif self.flags and not other.flags:
			s2 = s2.lower()
		if s1 == s2 and self.negate == other.negate:
			if other.flags:
				return other
			return self
		return None

	def __eq__(self, other):
		return self.exact == other.exact and self.negate == other.negate and self.flags == other.flags

	def __hash__(self):
		return hash((self.exact, self.negate, self.flags))

	def __repr__(self):
		if self.negate:
			string = '<%s %r negated @%#8x>'
		else:
			string = '<%s %r @%#8x>'
		return string % (self.__class__.__name__, self.exact, id(self))

	def __str__(self):
		if self.negate:
			return "!= "+self.exact
		return "== "+self.exact


class StrGlobMatch(StrMatch):

	"""
	globbing matches; essentially startswith and endswith matches
	"""

	__slots__ = ("glob", "prefix")

	__inst_caching__ = True

	def __init__(self, glob, CaseSensitive=True, prefix=True, **kwds):

		"""
		@param glob: string chunk that must be matched
		@param CaseSensitive: should the match be case sensitive?
		@param prefix: should the glob be a prefix check for matching, or postfix matching
		@keyword negate: should the match results be negated?
		"""

		super(StrGlobMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.glob = str(glob).lower()
		else:
			self.flags = 0
			self.glob = str(glob)
		self.prefix = prefix

	def match(self, value):
		value = str(value)
		if self.flags == re.I:
			value = value.lower()
		if self.prefix:
			f = value.startswith
		else:
			f = value.endswith
		return f(self.glob) ^ self.negate

	def intersect(self, other):
		if self.match(other.glob):
			if self.negate == other.negate:
				return other
		elif other.match(self.glob):
			if self.negate == other.negate:
				return self
		return None

	def __eq__(self, other):
		try:
			return self.glob == other.glob and self.negate == other.negate and self.flags == other.flags and self.prefix == other.prefix
		except AttributeError:
			return False

	def __hash__(self):
		return hash((self.glob, self.negate, self.flags, self.prefix))

	def __repr__(self):
		if self.negate:
			string = '<%s %r negated @%#8x>'
		else:
			string = '<%s %r @%#8x>'
		return string % (self.__class__.__name__, self.glob, id(self))

	def __str__(self):
		s = ''
		if self.negate:
			s = 'not '
		if self.prefix:
			return "%s%s*" % (s, self.glob)
		return "%s*%s" % (s, self.glob)


def EqualityMatch(val, negate=False):
	"""
	equality test wrapping L{ComparisonMatch}
	"""
	return ComparisonMatch(cmp, val, [0], negate=negate)

def _mangle_cmp_val(val):
	if val < 0:
		return -1
	elif val > 0:
		return 1
	return 0


class ComparisonMatch(base):
	"""comparison restriction- match if the comparison funcs return value is what's required"""

	_op_converter = {"=": (0,)}
	_rev_op_converter = {(0,): "="}

	for k, v in (("<", (-1,)), (">", (1,))):
		_op_converter[k] = v
		_op_converter[k+"="] = tuple(sorted(v + (0,)))
		_rev_op_converter[v] = k
		_rev_op_converter[tuple(sorted(v+(0,)))] = k+"="
	_op_converter["!="] = _op_converter["<>"] = (-1, 1)
	_rev_op_converter[(-1,1)] = "!="
	del k,v

	__slots__ = ("data", "cmp_func", "matching_vals")
	negate = False

	@classmethod
	def convert_str_op(cls, op_str):
		return cls._op_converter[op_str]
	
	@classmethod
	def convert_op_str(cls, op):
		return cls._rev_op_converter[tuple(sorted(op))]
	
	def __init__(self, cmp_func, data, matching_vals, negate=False):

		"""
		@param cmp_func: comparison function that compares data against what is passed in during match
		@param data: data to base comparison against
		@param matching_vals: sequence, composed of [-1 (less then), 0 (equal), and 1 (greater then)].
		If you specify [-1,0], you're saying "result must be less then or equal to".
		@param negate: should the results be negated?
		"""
			
		self.cmp_func = cmp_func
	
		if not isinstance(matching_vals, (tuple, list)):
			if isinstance(matching_vals, basestring):
				matching_vals = self.convert_str_op(matching_vals)
			elif isinstance(matching_vals, int):
				matching_vals = [matching_vals]
			else:
				raise TypeError("matching_vals must be a list/tuple")
			
		self.data = data
		if negate:
			self.matching_vals = tuple(set([-1, 0, 1]).difference(_mangle_cmp_val(x) for x in matching_vals))
		else:
			self.matching_vals = tuple(_mangle_cmp_val(x) for x in matching_vals)

	def match(self, actual_val):
		return _mangle_cmp_val(self.cmp_func(actual_val, self.data)) in self.matching_vals

	def __hash__(self):
		return hash((self.cmp_func, self.matching_vals, self.data))

	def __eq__(self, other):
		try:
			return self.cmp_func == other.cmp_func and self.matching_vals == other.matching_vals and \
				self.data == other.data
		except AttributeError:
			return False

	def __repr__(self):
		return '<%s %s %r @%#8x>' % (
			self.__class__.__name__, self.convert_op_str(self.matching_vals),
			self.data, id(self))

	def __str__(self):
		return "%s %s" % (self.convert_op_str(self.matching_vals), self.data)


class ContainmentMatch(base):

	"""used for an 'in' style operation, 'x86' in ['x86','~x86'] for example
	note that negation of this *does* not result in a true NAND when all is on.
	"""

	__slots__ = ("vals", "all")

	__inst_caching__ = True

	def __init__(self, *vals, **kwds):

		"""
		@param vals: what values to look for during match
		@keyword all: must all vals be present, or just one for a match to succeed?
		@keyword negate: should the match results be negated?
		"""

		self.all = bool(kwds.pop("all", False))
		super(ContainmentMatch, self).__init__(**kwds)
		# note that we're discarding any specialized __getitem__ on vals here.
		# this isn't optimal, and should be special cased for known types (lists/tuples fex)
		self.vals = frozenset(vals)

	def match(self, val):
		if isinstance(val, basestring):
			for fval in self.vals:
				if fval in val:
					return not self.negate
			return self.negate

		# this can, and should be optimized to do len checks- iterate over the smaller of the two
		# see above about special casing bits.  need the same protection here, on the offchance
		# (as contents sets do), the __getitem__ is non standard.
		try:
			if self.all:
				i = iter(val)
				return bool(self.vals.difference(i)) == self.negate
			for x in self.vals:
				if x in val:
					return not self.negate
			return self.negate
		except TypeError:
			# other way around.  rely on contains.
			if self.all:
				for k in self.vals:
					if k not in val:
						return self.negate
				return not self.negate
			for k in self.vals:
				if k in val:
					return not self.negate
								

	def force_False(self, pkg, attr, val):

		# XXX pretty much positive this isn't working.
		if isinstance(val, (str, unicode)):
			# unchangable
			if self.all:
				if len(self.vals) != 1:
					yield False
				else:
					yield (self.vals[0] in val) ^ self.negate
			else:
				yield (val in self.vals) ^ self.negate
			return

		entry = pkg.changes_count()
		if self.negate:
			if self.all:
				def filter(truths):		return False in truths
				def true(r, pvals):		return pkg.request_enable(attr, r)
				def false(r, pvals):	return pkg.request_disable(attr, r)

				truths = [x in val for x in self.vals]

				for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
					desired_false=false, desired_true=true):
					yield True
			else:
				if pkg.request_disable(attr, *self.vals):
					yield True
			return

		if not self.all:
			if pkg.request_disable(attr, *self.vals):
				yield True
		else:
			l = len(self.vals)
			def filter(truths):		return truths.count(True) < l
			def true(r, pvals):		return pkg.request_enable(attr, r)
			def false(r, pvals):	return pkg.request_disable(attr, r)
			truths = [x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, l, truths, filter,
				desired_false=false, desired_true=true):
				yield True
		return


	def force_True(self, pkg, attr, val):

		# XXX pretty much positive this isn't working.

		if isinstance(val, (str, unicode)):
			# unchangable
			if self.all:
				if len(self.vals) != 1:
					return False
				else:
					return (self.vals[0] in val) ^ self.negate
			else:
				return (val in self.vals) ^ self.negate
			return False

		entry = pkg.changes_count()
		if not self.negate:
			if not self.all:
				def filter(truths):
					return True in truths
				def true(r, pvals):
					return pkg.request_enable(attr, r)
				def false(r, pvals):
					return pkg.request_disable(attr, r)

				truths = [x in val for x in self.vals]

				for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
					desired_false=false, desired_true=true):
					return True
			else:
				if pkg.request_enable(attr, *self.vals):
					return True
			return False

		# negation
		if not self.all:
			if pkg.request_disable(attr, *self.vals):
				return True
		else:
			def filter(truths):		return True not in truths
			def true(r, pvals):		return pkg.request_enable(attr, r)
			def false(r, pvals):	return pkg.request_disable(attr, r)
			truths = [x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
				desired_false=false, desired_true=true):
				return True
		return False


	def __eq__(self, other):
		try:
			return self.all == other.all and self.negate == other.negate and self.vals == other.vals
		except AttributeError:
			return False

	def __hash__(self):
		return hash((self.all, self.negate, self.vals))

	def __repr__(self):
		if self.negate:
			string = '<%s %r all=%s negated @%#8x>'
		else:
			string = '<%s %r all=%s @%#8x>'
		return string % (
			self.__class__.__name__, tuple(self.vals), self.all, id(self))

	def __str__(self):
		if self.negate:
			s = "not contains [%s]"
		else:
			s = "contains [%s]"
		return s % ', '.join(map(str, self.vals))

for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, node_type=value_type)
		if doc is None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(x.lstrip() for x in doc.split("\n")) + "\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
