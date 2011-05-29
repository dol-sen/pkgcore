#!/usr/bin/python -O
# Copyright 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

# disable sandbox for any pyc regens
import os
env = os.environ["SANDBOX_ON"] = "0"

from snakeoil.demandload import demandload
demandload(globals(),
    "snakeoil.iterables:caching_iter",
    "pkgcore.config:load_config",
    "pkgcore.ebuild:atom,conditionals",
    "pkgcore.package:errors",
    "pkgcore.restrictions.boolean:AndRestriction",
    "pkgcore.util.packages:get_raw_pkg",
    "sys",
    "os",
)

def str_pkg(pkg):
    pkg = get_raw_pkg(pkg)
    # special casing; old style virtuals come through as the original pkg.
    if pkg.package_is_real:
        return pkg.cpvstr
    if hasattr(pkg, "actual_pkg"):
        return pkg.actual_pkg.cpvstr
    # icky, but works.
    return str(pkg.rdepends).lstrip("=")

def expose_to_commandline(count, **kwds):
    def internal_f(f):
        f.args = count
        f.swallow_root = kwds.pop("swallow_root", False)
        f.command_handler = True
        return f
    return internal_f

def set_arg_count(count):
    def internal_f(f):
        f.args = count
        return f
    return internal_f

default_get = lambda d,k: d.settings.get(k, "")
distdir_get = lambda d,k: d.settings["fetcher"].distdir
envvar_getter = {"DISTDIR":distdir_get}

@expose_to_commandline(-1)
def envvar(domain, *keys):
    """
    return configuration defined variables
    """
    return ["".join("%s\n" % envvar_getter.get(x, default_get)(domain, x)
        for x in keys), 0]

def make_atom(a):
	# use environment limitation if possible;
    a = atom.atom(a, eapi=int(os.environ.get("PORTAGEQ_LIMIT_EAPI", -1)))
    # force expansion.
    a.restrictions
    if isinstance(a, atom.transitive_use_atom):
        # XXX: hack
        a = conditionals.DepSet(a.restrictions, atom.atom, True)
        a = a.evaluate_depset(os.environ.get("PORTAGEQ_LIMIT_USE", "").split())
        a = AndRestriction(*a.restrictions)
    return a

@expose_to_commandline(1, swallow_root=True)
def has_version(domain, arg):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    arg = make_atom(arg)
    if caching_iter(domain.all_livefs_repos.itermatch(arg)):
        return ['', 0]
    return ['', 1]

@expose_to_commandline(-1, swallow_root=True)
def mass_best_version(domain, *args):
    """
    multiple best_version calls
    """
    return ["".join("%s:%s\n" % (x, best_version(domain, x)[0].rstrip())
        for x in args), 0]

@expose_to_commandline(1, swallow_root=True)
def best_version(domain, arg):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    # temp hack, configured pkgs yield "configured(blah) pkg"
    arg = make_atom(arg)
    try:
        p = max(domain.all_livefs_repos.itermatch(arg))
    except ValueError:
        # empty sequence.
        return ['', 1]
    return [str_pkg(get_raw_pkg(p)) + "\n", 0]


@expose_to_commandline(1, swallow_root=True)
def match(domain, arg):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    arg = make_atom(arg)
    # temp hack, configured pkgs yield "configured(blah) pkg"
    l = sorted(get_raw_pkg(x) for x in domain.all_repos.itermatch(arg))
    if not l:
        return ['', 1]
    return ["".join(str_pkg(x) +"\n" for x in l), 0]


def usage():
    print "\nusage: command domain atom"
    print "domain is the string name of the domain to query from; if exempted, will use the default domain"
    print "\n=available commands=\n"
    for k, v in globals().iteritems():
        if not getattr(v, "command_handler", False):
            continue
        print k
        print "\n".join("  "+x for x in [s.strip() for s in v.__doc__.split("\n")] if x)
        print

def main():
    a = sys.argv[1:]
    if "--usage" in a or "--help" in a:
        usage()
        sys.exit(0)
    if not a:
        usage()
        sys.exit(1)

    if "--domain" in a:
        i = a.index("--domain")
        domain = a[i+1]
        del a[i]
        del a[i]
    else:
        domain = None
    try:
        command = globals()[a[0]]
        if not getattr(command, "command_handler", False):
            raise KeyError
    except KeyError:
        print "%s isn't a valid command" % a[0]
        usage()
        sys.exit(2)

    if command.swallow_root:
        try:
            a.pop(0)
        except IndexError:
            print "arg count is wrong"
            usage()
            sys.exit(2)

    bad = False
    if command.args == -1:
        bad = not a
    else:
        bad = len(a) - 1 != command.args
    if bad:
        print "arg count is wrong"
        usage()
        sys.exit(2)

    if domain is None:
        domain = load_config().get_default("domain")
    else:
        domain = load_config().domain.get(domain)

    if domain is None:
        print "no default domain in your configuration, or what was specified manually wasn't found."
        print "known domains- %r" % list(load_config().domain.iterkeys())
        sys.exit(2)

    try:
        s, ret = command(domain, *a[1:])
    except errors.PackageError, e:
        sys.stderr.write(str(e).rstrip("\n") + "\n")
        sys.exit(-2)
    sys.stdout.write(s)
    sys.exit(ret)

if __name__ == "__main__":
    main()