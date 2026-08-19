"""
Package marker for the Django config package.

MySQL driver fallback (Windows-friendly):
  Django's MySQL backend wants the C driver `mysqlclient`. That one needs a
  compiler on some Windows setups and fails to pip-install. `PyMySQL` is a
  pure-Python drop-in that always installs. The lines below say: use
  mysqlclient if it is there, otherwise let PyMySQL pretend to be it.
  Nothing else in the project has to change either way.
"""
try:  # the fast C driver, if it installed cleanly
    import MySQLdb  # noqa: F401
except ImportError:  # pragma: no cover - depends on the local machine
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:
        # Neither driver present. Fine when USE_SQLITE=1; Django will raise a
        # clear error itself if MySQL is actually being used.
        pass
