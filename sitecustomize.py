# pyOpenSSL compatibility shim
def _agent_designer_pyopenssl_compat():
    try:
        from OpenSSL import SSL
    except Exception:
        return
    if getattr(SSL.Context, "_agent_designer_compat_applied", False):
        return

    class _AlwaysFalseUsed:
        def __get__(self, obj, objtype=None):
            return False
        def __set__(self, obj, value):
            return

    SSL.Context._used = _AlwaysFalseUsed()
    SSL.Context._agent_designer_compat_applied = True

_agent_designer_pyopenssl_compat()
